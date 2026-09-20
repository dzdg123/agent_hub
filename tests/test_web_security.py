import pytest

from research_agent.web import UnsafeURLError, ensure_public_url


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1", "http://localhost:8000"])
async def test_private_and_non_http_urls_are_rejected(url):
    with pytest.raises(UnsafeURLError):
        await ensure_public_url(url)

