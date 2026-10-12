from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import httpx
from bs4 import BeautifulSoup

import research_agent.web as web_module
from research_agent.models import Source
from research_agent.web import (
    DuckDuckGoHTMLSearch,
    collect_pages,
    extract_webpage,
    parse_search_html,
    resolve_search_url,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "day06"
DEFAULT_QUERY = "Python asyncio 官方教程"


def read_fixture(name: str) -> str:
    """从项目固定位置读取样例，避免依赖 PyCharm 的工作目录。"""
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def preview(text: str, limit: int = 240) -> str:
    """生成便于人工检查的单行正文预览。"""
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}…"


def print_source(source: Source, *, index: int | None = None) -> None:
    prefix = f"[{index}] " if index is not None else ""
    print(f"{prefix}标题: {source.title}")
    print(f"    URL: {source.url}")
    print(f"    source_id: {source.source_id}")
    print(f"    content_kind: {source.metadata.get('content_kind', 'unknown')}")
    print(f"    original_url: {source.metadata.get('original_url')}")
    print(f"    fetched_at: {source.fetched_at.isoformat()}")
    print(f"    正文长度: {len(source.content)}")
    print(f"    truncated: {source.metadata.get('truncated', False)}")
    print(f"    预览: {preview(source.content)!r}")


def print_failures(failures: list[dict]) -> None:
    if not failures:
        print("失败目标: 无")
        return

    print(f"失败目标: {len(failures)} 个")
    for failure in failures:
        status = failure.get("status_code")
        status_text = f", status={status}" if status is not None else ""
        print(
            f"  - {failure.get('url')}: {failure.get('error_kind')}"
            f"{status_text}, {failure.get('message')}"
        )


async def run_offline() -> None:
    """只使用 fixture 和假抓取器验证完整链路，不访问互联网。"""
    started_at = datetime.now(timezone.utc)
    started = perf_counter()
    print("=== Day 06 Web Lab：OFFLINE ===")
    print(f"运行时间(UTC): {started_at.isoformat()}")
    print("网络访问: 否（fixture + Mock）")

    search_html = read_fixture("search_results.html")
    search_results = parse_search_html(search_html)
    soup = BeautifulSoup(search_html, "html.parser")
    raw_targets = [
        resolved
        for anchor in soup.select(".result__a")
        if (resolved := resolve_search_url(str(anchor.get("href", ""))))
    ]
    normalized_urls = {item.url for item in search_results if item.url}

    print("\n--- 搜索 fixture 解析 ---")
    print("搜索服务状态: Mock 成功")
    print(f"解析结果数: {len(search_results)}")
    print(f"原始目标数: {len(raw_targets)}")
    print(f"归一化去重后 URL 数: {len(normalized_urls)}")
    for index, source in enumerate(search_results, start=1):
        print_source(source, index=index)

    article_html = read_fixture("article.html")
    article_url = "https://example.org/article"
    duplicate = search_results[0].model_copy(
        update={"url": f"{article_url}#details"}
    )
    candidates = [*search_results, duplicate]
    mock_calls: list[str] = []

    async def fake_fetch_webpage(url: str) -> Source:
        mock_calls.append(url)
        await asyncio.sleep(0)
        if url == article_url:
            return extract_webpage(article_html, url)

        request = httpx.Request("GET", url)
        response = httpx.Response(503, request=request)
        raise httpx.HTTPStatusError(
            "Mock Service Unavailable",
            request=request,
            response=response,
        )

    print("\n--- Mock 批量正文抓取 ---")
    with patch.object(web_module, "fetch_webpage", new=fake_fetch_webpage):
        pages, failures = await collect_pages(candidates, concurrency=3)

    print(f"输入候选数: {len(candidates)}")
    print(f"实际抓取数: {len(mock_calls)}（重复 URL 只抓取一次）")
    print(f"成功正文数: {len(pages)}")
    for index, page in enumerate(pages, start=1):
        print_source(page, index=index)
    print_failures(failures)
    print(f"\n离线实验完成，用时: {perf_counter() - started:.3f} 秒")


async def run_live(query: str) -> None:
    """执行少量真实请求；搜索最多 5 条，正文最多抓取 3 条。"""
    started_at = datetime.now(timezone.utc)
    started = perf_counter()
    print("=== Day 06 Web Lab：LIVE ===")
    print(f"运行时间(UTC): {started_at.isoformat()}")
    print(f"查询词: {query}")

    provider = DuckDuckGoHTMLSearch()
    try:
        search_results = await provider.search(query, max_results=5)
    except httpx.HTTPStatusError as exc:
        print(f"搜索服务失败: HTTP {exc.response.status_code}")
        raise
    except httpx.TimeoutException:
        print("搜索服务失败: timeout")
        raise
    except Exception as exc:
        print(f"搜索服务失败: {type(exc).__name__}: {exc}")
        raise

    print("搜索服务状态: 成功（2xx，已完成 HTML 解析）")
    print(f"搜索结果数: {len(search_results)}")
    print(
        "去重后的 URL 数: "
        f"{len({source.url for source in search_results if source.url})}"
    )

    candidates = search_results[:3]
    print(f"本次正文抓取目标数: {len(candidates)}（上限 3）")
    pages, failures = await collect_pages(candidates, concurrency=3)

    print(f"成功正文数: {len(pages)}")
    for index, page in enumerate(pages, start=1):
        print_source(page, index=index)
    print_failures(failures)
    print("\n人工检查提示：打开成功来源，核对预览关键句，并检查导航或广告是否混入。")
    print("验证码、登录页和仅 JavaScript 渲染的页面属于当前提取器的局限。")
    print(f"真实实验完成，用时: {perf_counter() - started:.3f} 秒")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Day 06 网页搜索、正文提取与批量抓取实验",
    )
    parser.add_argument(
        "--mode",
        choices=("offline", "live"),
        default="offline",
        help="offline 使用 fixture/Mock；live 执行少量真实请求（默认 offline）",
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help=f"live 模式查询词（默认：{DEFAULT_QUERY}）",
    )
    return parser


async def async_main(args: argparse.Namespace) -> None:
    if args.mode == "offline":
        await run_offline()
        return

    query = args.query.strip()
    if not query:
        raise ValueError("live 模式的 query 不能为空")
    await run_live(query)


def main() -> None:
    # PyCharm、PowerShell 和重定向输出都统一使用 UTF-8 显示中文。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
