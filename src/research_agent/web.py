from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from abc import ABC, abstractmethod
from urllib.parse import parse_qs, urlparse, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from .documents import content_id
from .models import Source


logger = logging.getLogger(__name__)


_CAPTCHA_MARKERS = (
    "captcha",
    "verify you are human",
    "verification required",
    "unusual traffic",
    "人机验证",
    "验证码",
)
_NO_RESULTS_MARKERS = (
    "no results",
    "no results found",
    "没有找到结果",
    "未找到相关结果",
)
_NO_RESULTS_SELECTORS = (
    ".no-results",
    ".no-results__message",
    "[data-testid='no-results']",
)


class UnsafeURLError(ValueError):
    pass

class RedirectUnsupportedError(ValueError):
    """Automatic redirects are intentionally disabled for arbitrary pages."""


class SearchServiceError(ValueError):
    """The search response is blocked or cannot be interpreted safely."""


class UnsupportedContentTypeError(ValueError):
    """The HTTP response is not a supported HTML document."""


class EmptyContentError(ValueError):
    """The HTML document contains no usable body text."""


async def ensure_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeURLError("只允许完整的 HTTP(S) 地址")
    if parsed.username or parsed.password:
        raise UnsafeURLError("URL 不允许包含用户名或密码")
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise UnsafeURLError("不允许访问本机地址")
    loop = asyncio.get_running_loop()
    try:
        default_port = 443 if parsed.scheme == "https" else 80
        entries = await loop.getaddrinfo(
            host,
            parsed.port or default_port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise UnsafeURLError("域名无法解析") from exc
    for entry in entries:
        ip = ipaddress.ip_address(entry[4][0])
        if not ip.is_global:
            raise UnsafeURLError("不允许访问私网、回环或保留地址")
    return url


class SearchProvider(ABC):
    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> list[Source]: ...

def resolve_search_url(
    raw_url: str,
) -> tuple[str, str] | None:
    candidate = raw_url.strip()
    if not candidate:
        return None

    parsed = urlsplit(candidate)

    if (
        parsed.netloc.lower().endswith("duckduckgo.com")
        and parsed.path.startswith("/l/")
    ):
        targets = parse_qs(parsed.query).get("uddg", [])
        if not targets:
            return None

        # parse_qs 已经完成一次解码
        candidate = targets[0].strip()
        parsed = urlsplit(candidate)

    if parsed.scheme.lower() not in {"http", "https"}:
        return None

    if not parsed.netloc:
        return None

    # 保留 fragment 的真实目标
    original_url = candidate

    # 删除 fragment 后用于去重和生成 source_id
    normalized_url = urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.query,
            "",
        )
    )

    return original_url, normalized_url



def validate_max_results(max_results: int) -> None:
    if (
        isinstance(max_results, bool)
        or not isinstance(max_results, int)
        or not 1 <= max_results <= 10
    ):
        raise ValueError("max_results 必须是 1～10 的整数")


def validate_fetch_arguments(
    url: str,
    timeout: float,
    max_chars: int,
) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url 不能为空")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or timeout <= 0
    ):
        raise ValueError("timeout 必须是正数")
    if (
        isinstance(max_chars, bool)
        or not isinstance(max_chars, int)
        or max_chars <= 0
    ):
        raise ValueError("max_chars 必须是正整数")
    return url.strip()


def _search_page_preview(soup: BeautifulSoup, limit: int = 240) -> str:
    text = " ".join(soup.get_text(" ", strip=True).split())
    if not text:
        text = " ".join(str(soup).split())
    return text[:limit]


def normalize_search_url(raw_url: str) -> str | None:
    resolved = resolve_search_url(raw_url)

    if resolved is None:
        return None

    _, normalized_url = resolved
    return normalized_url


def parse_search_html(
    html: str,
    max_results: int = 5,
) -> list[Source]:
    validate_max_results(max_results)

    soup = BeautifulSoup(html, "html.parser")
    results: list[Source] = []
    seen: set[str] = set()

    for result in soup.select(".result"):
        anchor = result.select_one(".result__a")
        if anchor is None:
            continue

        raw_url = str(anchor.get("href", ""))
        resolved = resolve_search_url(raw_url)

        if resolved is None:
            continue

        original_url, normalized_url = resolved

        if normalized_url in seen:
            continue

        seen.add(normalized_url)
        snippet = result.select_one(".result__snippet")
        content = snippet.get_text(" ", strip=True) if snippet else ""

        results.append(
            Source(
                source_id=f"web-{content_id(normalized_url)}",
                title=anchor.get_text(" ", strip=True),
                content=content,
                url=normalized_url,
                metadata={
                    "content_kind": "search_snippet",
                    "provider": "duckduckgo_html",
                    "original_url": original_url,
                    "truncated": False,
                }
            )
        )

        if len(results) >= max_results:
            break

    if results:
        return results

    page_text = " ".join(soup.get_text(" ", strip=True).split()).casefold()
    preview = _search_page_preview(soup)

    if any(marker in page_text for marker in _CAPTCHA_MARKERS):
        logger.warning("搜索服务疑似返回验证码页；preview=%r", preview)
        raise SearchServiceError(f"搜索服务疑似返回验证码页；页面预览: {preview!r}")

    explicit_no_results = any(soup.select_one(selector) for selector in _NO_RESULTS_SELECTORS)
    explicit_no_results = explicit_no_results or any(
        marker in page_text for marker in _NO_RESULTS_MARKERS
    )
    if explicit_no_results:
        return []

    logger.warning("搜索响应没有可识别结果，原因不确定；preview=%r", preview)
    raise SearchServiceError(f"搜索响应没有可识别结果，原因不确定；页面预览: {preview!r}")


class DuckDuckGoHTMLSearch(SearchProvider):
    """Small no-key search adapter suitable for learning and local demos."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    async def search(self, query: str, max_results: int = 5) -> list[Source]:
        query = query.strip()
        if not query:
            raise ValueError("query 不能为空")
        validate_max_results(max_results)

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "AgentLearningLab/0.1"},
            )
            response.raise_for_status()

        return parse_search_html(response.text, max_results)




def extract_webpage(
    html: str,
    url: str,
    max_chars: int = 30_000,
) -> Source:
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars <= 0:
        raise ValueError("max_chars 必须是正整数")

    soup = BeautifulSoup(html, "html.parser")

    resolved = resolve_search_url(url)
    if resolved is None:
        raise ValueError("url 必须是完整的 HTTP(S) 地址")
    original_url, normalized_url = resolved

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    title = title or url

    for element in soup(["script", "style", "nav", "footer", "noscript"]):
        element.decompose()

    main = soup.select_one("main, article") or soup.body
    if main is None:
        raise EmptyContentError("网页没有可用正文")

    lines = (
        line.strip()
        for line in main.get_text("\n").splitlines()
    )
    text = "\n".join(line for line in lines if line)

    if not text:
        raise EmptyContentError("网页没有可用正文")

    truncated = len(text) > max_chars

    return Source(
        source_id=f"web-{content_id(normalized_url)}",
        title=title,
        content=text[:max_chars],
        url=normalized_url,
        metadata={
            "content_kind": "web_page",
            "original_url": original_url,
            "truncated": truncated,
        },
    )


async def fetch_webpage(
    url: str,
    timeout: float = 20.0,
    max_chars: int = 30_000,
) -> Source:
    url = validate_fetch_arguments(url, timeout, max_chars)
    await ensure_public_url(url)

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
    ) as client:
        response = await client.get(
            url,
            headers={"User-Agent": "AgentLearningLab/0.1"},
        )
        if 300 <= response.status_code < 400:
            location = response.headers.get("location", "")
            raise RedirectUnsupportedError(
                f"暂不支持网页重定向: {response.status_code}, location={location!r}"
            )

        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type.lower():
            raise UnsupportedContentTypeError(f"不支持的网页类型: {content_type}")

    return extract_webpage(response.text, url, max_chars)


async def collect_pages(
    candidates: list[Source],
    concurrency: int = 3,
) -> tuple[list[Source], list[dict]]:
    if (
        isinstance(concurrency, bool)
        or not isinstance(concurrency, int)
        or concurrency <= 0
    ):
        raise ValueError("concurrency 必须是正整数")

    failures: list[dict] = []
    targets: list[tuple[str, str]] = []
    seen_urls: set[str] = set()

    for candidate in candidates:
        if not candidate.url or not candidate.url.strip():
            failures.append(
                {
                    "url": candidate.url,
                    "source_id": candidate.source_id,
                    "error_kind": "missing_url",
                    "status_code": None,
                    "message": "候选来源没有 URL",
                }
            )
            continue

        normalized_url = normalize_search_url(candidate.url)
        if normalized_url is None:
            failures.append(
                {
                    "url": candidate.url,
                    "source_id": candidate.source_id,
                    "error_kind": "unsafe_url",
                    "status_code": None,
                    "message": "候选 URL 不是完整的 HTTP(S) 地址",
                }
            )
            continue

        if normalized_url in seen_urls:
            continue

        seen_urls.add(normalized_url)
        source_id = f"web-{content_id(normalized_url)}"
        targets.append((normalized_url, source_id))

    semaphore = asyncio.Semaphore(concurrency)

    async def worker(
        url: str,
        source_id: str,
    ) -> tuple[Source | None, dict | None]:
        async with semaphore:
            try:
                return await fetch_webpage(url), None
            except asyncio.CancelledError:
                raise
            except httpx.TimeoutException:
                return None, {
                    "url": url,
                    "source_id": source_id,
                    "error_kind": "timeout",
                    "status_code": None,
                    "message": "网页请求超时",
                }
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                return None, {
                    "url": url,
                    "source_id": source_id,
                    "error_kind": "http_error",
                    "status_code": status_code,
                    "message": f"HTTP 请求失败: {status_code}",
                }
            except UnsafeURLError as exc:
                return None, {
                    "url": url,
                    "source_id": source_id,
                    "error_kind": "unsafe_url",
                    "status_code": None,
                    "message": str(exc),
                }
            except RedirectUnsupportedError as exc:
                return None, {
                    "url": url,
                    "source_id": source_id,
                    "error_kind": "redirect_unsupported",
                    "status_code": None,
                    "message": str(exc),
                }
            except UnsupportedContentTypeError as exc:
                return None, {
                    "url": url,
                    "source_id": source_id,
                    "error_kind": "unsupported_type",
                    "status_code": None,
                    "message": str(exc),
                }
            except EmptyContentError as exc:
                return None, {
                    "url": url,
                    "source_id": source_id,
                    "error_kind": "empty_content",
                    "status_code": None,
                    "message": str(exc),
                }
            except httpx.RequestError as exc:
                return None, {
                    "url": url,
                    "source_id": source_id,
                    "error_kind": "network_error",
                    "status_code": None,
                    "message": f"网络请求失败: {type(exc).__name__}",
                }

    outcomes = await asyncio.gather(
        *(worker(url, source_id) for url, source_id in targets)
    )

    unique_pages: dict[str, Source] = {}
    for page, failure in outcomes:
        if page is not None:
            unique_pages.setdefault(page.source_id, page)
        if failure is not None:
            failures.append(failure)

    return list(unique_pages.values()), failures
