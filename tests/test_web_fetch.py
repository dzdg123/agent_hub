import asyncio
from collections import Counter
from pathlib import Path

import httpx
import pytest

import research_agent.web as web_module
from research_agent.documents import content_id
from research_agent.models import Source
from research_agent.web import (
    EmptyContentError,
    RedirectUnsupportedError,
    UnsupportedContentTypeError,
    collect_pages,
    extract_webpage,
    fetch_webpage,
    parse_search_html,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "day06"


def read_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def run_immediate(coroutine):
    """Drive a mocked coroutine that must complete without real I/O."""
    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    else:
        coroutine.close()
        raise AssertionError("离线假客户端不应挂起或执行真实 I/O")


def allow_public_url(monkeypatch) -> None:
    async def fake_public_url(url: str) -> str:
        return url

    monkeypatch.setattr(web_module, "ensure_public_url", fake_public_url)


def install_fake_fetch_client(
    monkeypatch,
    *,
    status_code: int = 200,
    text: str = "",
    response_headers: dict[str, str] | None = None,
    error: Exception | None = None,
):
    class FakeAsyncClient:
        instances: list["FakeAsyncClient"] = []
        calls: list[dict] = []

        def __init__(self, *args, **kwargs):
            self.options = kwargs
            self.__class__.instances.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def get(self, url, *, headers=None):
            self.__class__.calls.append({"url": url, "headers": headers})
            if error is not None:
                raise error
            request = httpx.Request("GET", url, headers=headers)
            return httpx.Response(
                status_code=status_code,
                text=text,
                headers=response_headers or {},
                request=request,
            )

    monkeypatch.setattr(web_module.httpx, "AsyncClient", FakeAsyncClient)
    return FakeAsyncClient


def test_webpage_metadata_marks_full_page_content():
    page = extract_webpage(
        html="<html><body><main>完整正文</main></body></html>",
        url="https://example.org/article",
    )

    assert page.metadata["content_kind"] == "web_page"
    assert page.metadata["original_url"] == "https://example.org/article"
    assert page.metadata["truncated"] is False


def test_article_fixture_preserves_page_fields_and_cleans_content():
    url = "https://example.org/article"

    page = extract_webpage(read_fixture("article.html"), url=url)

    assert page.title == "异步学习笔记"
    assert page.url == url
    assert page.source_id == f"web-{content_id(url)}"
    assert page.content == (
        "异步请求\n"
        "网络请求主要花时间等待远程响应。\n"
        "多个独立请求可以并发推进。"
    )
    assert page.metadata == {
        "content_kind": "web_page",
        "original_url": url,
        "truncated": False,
    }
    for removed_text in ("body { color: black; }", "首页", "console.log", "页脚"):
        assert removed_text not in page.content


def test_webpage_content_is_truncated_at_max_chars():
    page = extract_webpage(
        html="<html><body><main>123456</main></body></html>",
        url="https://example.org/article",
        max_chars=3,
    )

    assert page.content == "123"
    assert page.metadata["truncated"] is True


@pytest.mark.parametrize("max_chars", [0, -1, True, 1.5])
def test_extract_webpage_rejects_invalid_max_chars(max_chars):
    with pytest.raises(ValueError, match="max_chars"):
        extract_webpage(
            html="<html><body><main>正文</main></body></html>",
            url="https://example.org/article",
            max_chars=max_chars,
        )


def test_missing_title_and_article_fall_back_to_url_and_body():
    url = "https://example.org/fallback"

    page = extract_webpage(
        html="<html><body><p>回退后的正文</p></body></html>",
        url=url,
    )

    assert page.title == url
    assert page.content == "回退后的正文"


@pytest.mark.parametrize(
    "html",
    [
        "<html><body></body></html>",
        "<html><head><title>只有标题</title></head><body></body></html>",
    ],
)
def test_extract_webpage_rejects_empty_body_and_title_only_page(html):
    with pytest.raises(EmptyContentError, match="没有可用正文"):
        extract_webpage(html, url="https://example.org/empty")


def test_search_snippet_and_webpage_share_source_id():
    search_result = parse_search_html(read_fixture("search_results.html"))[0]
    page = extract_webpage(
        html="<html><body><main>完整正文</main></body></html>",
        url=search_result.metadata["original_url"],
    )

    assert search_result.source_id == page.source_id
    assert search_result.url == page.url
    assert search_result.metadata["content_kind"] == "search_snippet"
    assert page.metadata["content_kind"] == "web_page"


@pytest.mark.parametrize(
    "content_type",
    ["text/html", "text/html; charset=utf-8"],
)
def test_fetch_webpage_accepts_html(monkeypatch, content_type):
    allow_public_url(monkeypatch)
    install_fake_fetch_client(
        monkeypatch,
        status_code=200,
        text="<html><body><main>完整正文</main></body></html>",
        response_headers={"content-type": content_type},
    )

    page = run_immediate(fetch_webpage("https://example.org/article"))

    assert page.content == "完整正文"
    assert page.metadata["content_kind"] == "web_page"


def test_fetch_webpage_preserves_http_error(monkeypatch):
    allow_public_url(monkeypatch)
    install_fake_fetch_client(
        monkeypatch,
        status_code=404,
        text="<html><body>Not Found</body></html>",
        response_headers={"content-type": "text/html"},
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        run_immediate(fetch_webpage("https://example.org/missing"))

    assert exc_info.value.response.status_code == 404


def test_fetch_webpage_preserves_timeout(monkeypatch):
    allow_public_url(monkeypatch)
    install_fake_fetch_client(
        monkeypatch,
        error=httpx.ReadTimeout("timed out"),
    )

    with pytest.raises(httpx.ReadTimeout):
        run_immediate(fetch_webpage("https://example.org/slow"))


@pytest.mark.parametrize(
    "content_type",
    ["application/json", "application/pdf", "image/png"],
)
def test_fetch_webpage_rejects_non_html(monkeypatch, content_type):
    allow_public_url(monkeypatch)
    install_fake_fetch_client(
        monkeypatch,
        status_code=200,
        text="not html",
        response_headers={"content-type": content_type},
    )

    with pytest.raises(UnsupportedContentTypeError, match="不支持的网页类型"):
        run_immediate(fetch_webpage("https://example.org/file"))


def test_fetch_webpage_rejects_redirect_without_following(monkeypatch):
    allow_public_url(monkeypatch)
    fake_client = install_fake_fetch_client(
        monkeypatch,
        status_code=302,
        response_headers={"location": "http://127.0.0.1/private"},
    )

    with pytest.raises(RedirectUnsupportedError, match="暂不支持网页重定向"):
        run_immediate(fetch_webpage("https://example.org/redirect"))

    assert len(fake_client.calls) == 1
    assert fake_client.instances[0].options["follow_redirects"] is False


def test_fetch_webpage_rejects_empty_html(monkeypatch):
    allow_public_url(monkeypatch)
    install_fake_fetch_client(
        monkeypatch,
        status_code=200,
        text="<html><head><title>只有标题</title></head></html>",
        response_headers={"content-type": "text/html"},
    )

    with pytest.raises(EmptyContentError, match="没有可用正文"):
        run_immediate(fetch_webpage("https://example.org/empty"))


@pytest.mark.parametrize(
    ("url", "timeout", "max_chars"),
    [
        ("", 20.0, 30_000),
        ("   ", 20.0, 30_000),
        ("https://example.org", 0, 30_000),
        ("https://example.org", -1, 30_000),
        ("https://example.org", 20.0, 0),
        ("https://example.org", 20.0, -1),
    ],
)
def test_invalid_fetch_input_fails_before_request(
    monkeypatch,
    url,
    timeout,
    max_chars,
):
    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("无效参数不应创建 HTTP 客户端")

    monkeypatch.setattr(web_module.httpx, "AsyncClient", UnexpectedClient)

    with pytest.raises(ValueError):
        run_immediate(
            fetch_webpage(
                url,
                timeout=timeout,
                max_chars=max_chars,
            )
        )


def test_non_content_tags_are_removed():
    page = extract_webpage(
        html="""
        <html>
          <head><title>测试文章</title></head>
          <body>
            <nav>导航文字</nav>
            <main>
              <p>第一段正文</p>
              <script>危险脚本</script>
              <p>第二段正文</p>
            </main>
            <footer>页脚文字</footer>
          </body>
        </html>
        """,
        url="https://example.org/article",
    )

    assert "第一段正文" in page.content
    assert "第二段正文" in page.content
    assert "导航文字" not in page.content
    assert "危险脚本" not in page.content
    assert "页脚文字" not in page.content

def make_candidate(url: str | None, title: str) -> Source:
    identity = url or title
    return Source(
        source_id=f"web-{content_id(identity)}",
        title=title,
        content=f"{title}的搜索摘要",
        url=url,
        metadata={
            "content_kind": "search_snippet",
            "provider": "duckduckgo_html",
            "original_url": url,
            "truncated": False,
        },
    )


@pytest.mark.asyncio
async def test_collect_pages_isolates_failures_deduplicates_and_limits_concurrency(
    monkeypatch,
):
    candidates = [
        make_candidate("https://example.org/success", "成功页面"),
        make_candidate("https://example.org/missing", "404 页面"),
        make_candidate("https://example.org/slow", "超时页面"),
        make_candidate("https://example.org/empty", "空正文页面"),
        make_candidate("https://example.org/success#details", "重复成功页面"),
    ]
    calls: Counter[str] = Counter()
    active = 0
    peak_active = 0

    async def fake_fetch_webpage(url: str) -> Source:
        nonlocal active, peak_active
        calls[url] += 1
        active += 1
        peak_active = max(peak_active, active)

        try:
            await asyncio.sleep(0.01)

            if url.endswith("/missing"):
                request = httpx.Request("GET", url)
                response = httpx.Response(404, request=request)
                raise httpx.HTTPStatusError(
                    "Not Found",
                    request=request,
                    response=response,
                )
            if url.endswith("/slow"):
                raise httpx.ReadTimeout("timed out")
            if url.endswith("/empty"):
                raise EmptyContentError("网页没有可用正文")

            return Source(
                source_id=f"web-{content_id(url)}",
                title="成功正文",
                content="完整正文",
                url=url,
                metadata={
                    "content_kind": "web_page",
                    "original_url": url,
                    "truncated": False,
                },
            )
        finally:
            active -= 1

    monkeypatch.setattr(web_module, "fetch_webpage", fake_fetch_webpage)

    pages, failures = await collect_pages(candidates, concurrency=3)

    assert len(candidates) == 5
    assert sum(calls.values()) == 4
    assert calls["https://example.org/success"] == 1
    assert len(pages) == 1
    assert pages[0].url == "https://example.org/success"
    assert pages[0].metadata["content_kind"] == "web_page"
    assert len(failures) == 3
    assert {failure["error_kind"] for failure in failures} == {
        "http_error",
        "timeout",
        "empty_content",
    }
    http_failure = next(
        failure for failure in failures if failure["error_kind"] == "http_error"
    )
    assert http_failure["status_code"] == 404
    assert peak_active == 3
    assert active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("concurrency", [0, -1, True, 1.5])
async def test_collect_pages_rejects_invalid_concurrency_before_fetch(
    monkeypatch,
    concurrency,
):
    call_count = 0

    async def unexpected_fetch(url: str) -> Source:
        nonlocal call_count
        call_count += 1
        raise AssertionError("非法 concurrency 不应触发抓取")

    monkeypatch.setattr(web_module, "fetch_webpage", unexpected_fetch)

    with pytest.raises(ValueError, match="concurrency"):
        await collect_pages(
            [make_candidate("https://example.org/page", "候选页面")],
            concurrency=concurrency,
        )

    assert call_count == 0


@pytest.mark.asyncio
async def test_collect_pages_records_missing_and_invalid_urls_without_fetch(
    monkeypatch,
):
    call_count = 0

    async def unexpected_fetch(url: str) -> Source:
        nonlocal call_count
        call_count += 1
        raise AssertionError("缺失或非法 URL 不应触发抓取")

    monkeypatch.setattr(web_module, "fetch_webpage", unexpected_fetch)
    candidates = [
        make_candidate(None, "缺少 URL"),
        make_candidate("javascript:alert(1)", "非法 URL"),
    ]

    pages, failures = await collect_pages(candidates)

    assert pages == []
    assert call_count == 0
    assert {failure["error_kind"] for failure in failures} == {
        "missing_url",
        "unsafe_url",
    }


@pytest.mark.asyncio
async def test_collect_pages_does_not_hide_programming_errors(monkeypatch):
    async def broken_fetch(url: str) -> Source:
        raise AssertionError("模拟程序错误")

    monkeypatch.setattr(web_module, "fetch_webpage", broken_fetch)

    with pytest.raises(AssertionError, match="模拟程序错误"):
        await collect_pages(
            [make_candidate("https://example.org/page", "候选页面")]
        )

