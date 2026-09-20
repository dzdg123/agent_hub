from __future__ import annotations

import asyncio
import ipaddress
import socket
from abc import ABC, abstractmethod
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from .documents import content_id
from .models import Source


class UnsafeURLError(ValueError):
    pass


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
        entries = await loop.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
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


class DuckDuckGoHTMLSearch(SearchProvider):
    """Small no-key search adapter suitable for learning and local demos."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    async def search(self, query: str, max_results: int = 5) -> list[Source]:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "AgentLearningLab/0.1"},
            )
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results: list[Source] = []
        seen: set[str] = set()
        for result in soup.select(".result"):
            anchor = result.select_one(".result__a")
            snippet = result.select_one(".result__snippet")
            if not anchor:
                continue
            url = str(anchor.get("href", ""))
            if "uddg=" in url:
                url = unquote(parse_qs(urlparse(url).query).get("uddg", [url])[0])
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            seen.add(url)
            body = snippet.get_text(" ", strip=True) if snippet else ""
            results.append(
                Source(
                    source_id=f"web-{content_id(url)}",
                    title=anchor.get_text(" ", strip=True),
                    content=body,
                    url=url,
                )
            )
            if len(results) >= max_results:
                break
        return results


async def fetch_webpage(url: str, timeout: float = 20.0, max_chars: int = 30_000) -> Source:
    await ensure_public_url(url)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": "AgentLearningLab/0.1"})
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type:
            raise ValueError(f"不支持的网页类型: {content_type}")
    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "nav", "footer", "noscript"]):
        element.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else url
    main = soup.select_one("main, article") or soup.body or soup
    text = "\n".join(line.strip() for line in main.get_text("\n").splitlines() if line.strip())
    if not text:
        raise ValueError("网页没有可用正文")
    return Source(
        source_id=f"web-{content_id(url)}",
        title=title,
        content=text[:max_chars],
        url=url,
        metadata={"truncated": len(text) > max_chars},
    )
