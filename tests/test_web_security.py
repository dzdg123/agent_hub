import socket

import pytest

import research_agent.web as web_module
from research_agent.web import UnsafeURLError, ensure_public_url


def install_fake_dns(monkeypatch, *addresses: str, error: Exception | None = None):
    calls: list[tuple[str, int]] = []

    class FakeLoop:
        async def getaddrinfo(self, host, port, *, type):
            calls.append((host, port))
            assert type == socket.SOCK_STREAM
            if error is not None:
                raise error
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))
                for address in addresses
            ]

    monkeypatch.setattr(web_module.asyncio, "get_running_loop", FakeLoop)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1", "http://localhost:8000"])
async def test_private_and_non_http_urls_are_rejected(url):
    with pytest.raises(UnsafeURLError):
        await ensure_public_url(url)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "expected_port"),
    [
        ("http://public.example/article", 80),
        ("https://public.example/article", 443),
        ("https://public.example:8443/article", 8443),
    ],
)
async def test_http_and_https_public_addresses_are_allowed(
    monkeypatch,
    url,
    expected_port,
):
    calls = install_fake_dns(monkeypatch, "93.184.216.34")

    assert await ensure_public_url(url) == url
    assert calls == [("public.example", expected_port)]


@pytest.mark.asyncio
async def test_hostname_resolving_to_private_address_is_rejected(monkeypatch):
    calls = install_fake_dns(monkeypatch, "192.168.1.20")

    with pytest.raises(UnsafeURLError, match="私网"):
        await ensure_public_url("https://private.example/page")

    assert calls == [("private.example", 443)]


@pytest.mark.asyncio
async def test_mixed_public_and_private_dns_results_are_rejected(monkeypatch):
    install_fake_dns(monkeypatch, "93.184.216.34", "10.0.0.8")

    with pytest.raises(UnsafeURLError, match="私网"):
        await ensure_public_url("https://mixed.example/page")


@pytest.mark.asyncio
async def test_dns_failure_is_reported_without_real_network(monkeypatch):
    install_fake_dns(monkeypatch, error=socket.gaierror("mock DNS failure"))

    with pytest.raises(UnsafeURLError, match="域名无法解析"):
        await ensure_public_url("https://missing.example/page")

