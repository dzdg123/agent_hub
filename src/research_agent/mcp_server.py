from __future__ import annotations

from .config import get_settings
from .documents import load_all_documents
from .models import Source
from .runtime import get_index
from .web import fetch_webpage

from pydantic import BaseModel, Field


class HealthResult(BaseModel):
    ok: bool
    document_root: str


class SourceListResult(BaseModel):
    results: list[Source] = Field(default_factory=list)


class GetSourceResult(BaseModel):
    ok: bool
    source: Source | None = None
    error: str | None = None


def create_server():
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError:
        from mcp.server.fastmcp import FastMCP as MCPServer

    mcp = MCPServer("Agent Learning Lab Research Tools")
    settings = get_settings()

    @mcp.tool(structured_output=True)
    def health() -> HealthResult:
        """检查研究工具服务器是否正常运行。"""
        return HealthResult(ok=True, document_root=str(settings.document_root.resolve()))

    @mcp.tool(structured_output=True)
    def list_documents() -> SourceListResult:
        """列出允许目录内已经加载的本地文档片段。"""
        return SourceListResult(results=load_all_documents(settings.document_root))

    @mcp.tool(structured_output=True)
    def search_documents(query: str, top_k: int = 5) -> SourceListResult:
        """在本地文档中搜索与 query 相关的片段，top_k 范围为 1 到 10。"""
        top_k = max(1, min(top_k, 10))
        return SourceListResult(results=get_index().search(query, top_k))

    @mcp.tool(structured_output=True)
    async def fetch_public_webpage(url: str) -> Source:
        """读取公开 HTTP(S) 网页正文；拒绝本机、私网和保留地址。"""
        return await fetch_webpage(url)

    @mcp.tool(structured_output=True)
    def get_source(source_id: str) -> GetSourceResult:
        """根据来源 ID 获取一个已经索引的本地来源。"""
        source = get_index().get(source_id)
        if source is None:
            return GetSourceResult(ok=False, error="来源不存在")
        return GetSourceResult(ok=True, source=source)

    return mcp


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
