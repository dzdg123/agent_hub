import pytest
from mcp import Client

from research_agent.mcp_server import create_server


@pytest.mark.asyncio
async def test_mcp_server_lists_expected_tools():
    async with Client(create_server()) as client:
        result = await client.list_tools()
        names = {tool.name for tool in result.tools}
        assert {"health", "list_documents", "search_documents", "fetch_public_webpage", "get_source"} <= names


@pytest.mark.asyncio
async def test_mcp_health_tool_returns_structured_result():
    async with Client(create_server()) as client:
        result = await client.call_tool("health", {})
        assert not result.is_error
        assert result.structured_content["ok"] is True

