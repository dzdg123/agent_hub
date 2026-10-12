from pathlib import Path

import httpx
import pytest

import research_agent.web as web_module
from research_agent.documents import content_id
from research_agent.web import (
    DuckDuckGoHTMLSearch,
    SearchServiceError,
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


def install_fake_client(
    monkeypatch,
    *,
    status_code: int = 200,
    text: str = "",
    error: Exception | None = None,
):
    class FakeAsyncClient:
        calls: list[dict] = []

        def __init__(self, *args, **kwargs):
            self.options = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def get(self, url, *, params=None, headers=None):
            self.__class__.calls.append(
                {"url": url, "params": params, "headers": headers}
            )
            if error is not None:
                raise error
            request = httpx.Request("GET", url, params=params, headers=headers)
            return httpx.Response(status_code, text=text, request=request)

    monkeypatch.setattr(web_module.httpx, "AsyncClient", FakeAsyncClient)
    return FakeAsyncClient


def test_search_fixture_is_normalized_and_deduplicated():
    results = parse_search_html(read_fixture("search_results.html"))

    assert len(results) == 2
    assert results[0].title == "异步教程"
    assert results[0].url == "https://example.org/article"
    assert results[0].source_id == (
        f"web-{content_id('https://example.org/article')}"
    )
    assert results[0].content == "关于协程与等待的摘要。"
    assert results[0].metadata["content_kind"] == "search_snippet"
    assert results[0].metadata["provider"] == "duckduckgo_html"
    assert results[0].metadata["truncated"] is False
    assert results[0].metadata["original_url"] == (
        "https://example.org/article#intro"
    )
    assert results[1].url == "https://example.org/other?next=%2Fdocs"
    assert results[1].title == "另一篇文章"
    assert results[1].content == ""
    assert results[1].metadata["original_url"] == (
        "https://example.org/other?next=%2Fdocs"
    )


def test_fragment_variants_share_one_normalized_source_id():
    results = parse_search_html(
        """
        <div class="result">
          <a class="result__a" href="https://example.org/page#intro">第一页</a>
        </div>
        <div class="result">
          <a class="result__a" href="https://example.org/page#details">重复页</a>
        </div>
        """
    )

    assert len(results) == 1
    assert results[0].url == "https://example.org/page"
    assert results[0].source_id == f"web-{content_id(results[0].url)}"


def test_missing_link_and_invalid_protocol_are_skipped():
    results = parse_search_html(read_fixture("search_results.html"))

    assert [result.title for result in results] == ["异步教程", "另一篇文章"]
    assert all(result.url.startswith(("http://", "https://")) for result in results)


def test_max_results_caps_parsed_results():
    results = parse_search_html(
        read_fixture("search_results.html"),
        max_results=1,
    )

    assert len(results) == 1
    assert results[0].title == "异步教程"


@pytest.mark.parametrize("max_results", [0, 11, True, 1.5])
def test_parse_rejects_invalid_max_results(max_results):
    with pytest.raises(ValueError, match="max_results"):
        parse_search_html(read_fixture("search_results.html"), max_results)


def test_explicit_no_results_returns_empty_list():
    assert parse_search_html(read_fixture("no_results.html")) == []


def test_captcha_page_is_a_service_failure(caplog):
    with pytest.raises(SearchServiceError, match="验证码"):
        parse_search_html(read_fixture("captcha.html"))

    assert "preview" in caplog.text


def test_unrecognized_page_is_reported_as_uncertain(caplog):
    with pytest.raises(SearchServiceError, match="不确定") as exc_info:
        parse_search_html(read_fixture("uncertain_search.html"))

    assert "preview" in caplog.text
    assert len(str(exc_info.value)) < 400


def test_search_strips_query_before_request(monkeypatch):
    fake_client = install_fake_client(
        monkeypatch,
        text=read_fixture("search_results.html"),
    )

    results = run_immediate(
        DuckDuckGoHTMLSearch().search("  asyncio  ", max_results=2)
    )

    assert len(results) == 2
    assert fake_client.calls[0]["params"]["q"] == "asyncio"


@pytest.mark.parametrize(
    ("query", "max_results"),
    [("   ", 5), ("asyncio", 0), ("asyncio", 11)],
)
def test_invalid_input_fails_before_request(monkeypatch, query, max_results):
    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("无效输入不应创建 HTTP 客户端")

    monkeypatch.setattr(web_module.httpx, "AsyncClient", UnexpectedClient)

    with pytest.raises(ValueError):
        run_immediate(DuckDuckGoHTMLSearch().search(query, max_results=max_results))


def test_http_error_is_not_reported_as_empty_results(monkeypatch):
    install_fake_client(monkeypatch, status_code=503)

    with pytest.raises(httpx.HTTPStatusError):
        run_immediate(DuckDuckGoHTMLSearch().search("asyncio"))


def test_timeout_is_not_reported_as_empty_results(monkeypatch):
    install_fake_client(
        monkeypatch,
        error=httpx.ReadTimeout("timed out"),
    )

    with pytest.raises(httpx.ReadTimeout):
        run_immediate(DuckDuckGoHTMLSearch().search("asyncio"))
