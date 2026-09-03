import os
import ipaddress
import socket
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

CMS_BASE_URL = os.getenv("CMS_BASE_URL", "").rstrip("/")
CMS_LOGIN_EMAIL = os.getenv("CMS_LOGIN_EMAIL", "")
CMS_LOGIN_PASSWORD = os.getenv("CMS_LOGIN_PASSWORD", "")
OPERATOR_KEY = os.getenv("NEDS_OPERATOR_API_KEY", "")
PUBLISH_ENABLED = os.getenv("NEDS_OPERATOR_PUBLISH_ENABLED", "false").lower() == "true"
PORTAL_SLUG = os.getenv("NEDS_PORTAL_SLUG", "").strip()
SERVER_HOST = os.getenv("HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("PORT", "8080"))

mcp = FastMCP("NEDS India 24x7 News Operator")
mcp.settings.host = SERVER_HOST
mcp.settings.port = SERVER_PORT

_token: Optional[str] = None


def _check_config() -> None:
    missing = [k for k, v in {
        "CMS_BASE_URL": CMS_BASE_URL,
        "CMS_LOGIN_EMAIL": CMS_LOGIN_EMAIL,
        "CMS_LOGIN_PASSWORD": CMS_LOGIN_PASSWORD,
        "NEDS_OPERATOR_API_KEY": OPERATOR_KEY,
    }.items() if not v]
    if missing:
        raise RuntimeError("Missing server configuration: " + ", ".join(missing))
    if not CMS_BASE_URL.startswith("https://"):
        raise RuntimeError("CMS_BASE_URL must use HTTPS")


def _auth(api_key: str) -> None:
    if not OPERATOR_KEY or api_key != OPERATOR_KEY:
        raise PermissionError("Invalid operator API key")


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _login() -> str:
    global _token
    if _token:
        return _token
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{CMS_BASE_URL}/api/auth/login",
            json={"email": CMS_LOGIN_EMAIL, "password": CMS_LOGIN_PASSWORD},
        )
        r.raise_for_status()
        data = r.json()
        _token = data["access_token"]
        return _token


async def _request(method: str, path: str, **kwargs: Any) -> Any:
    token = await _login()
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.request(method, f"{CMS_BASE_URL}{path}", headers=_headers(token), **kwargs)
        if r.status_code == 401:
            global _token
            _token = None
            token = await _login()
            r = await client.request(method, f"{CMS_BASE_URL}{path}", headers=_headers(token), **kwargs)
        r.raise_for_status()
        if not r.content:
            return {"ok": True}
        return r.json()


@mcp.tool()
async def get_portal_settings(api_key: str) -> dict:
    """Get NEDS India 24x7 portal settings."""
    _auth(api_key)
    return await _request("GET", "/api/portal/settings")


@mcp.tool()
async def get_categories(api_key: str) -> Any:
    """List available news categories."""
    _auth(api_key)
    return await _request("GET", "/api/portal/categories")


@mcp.tool()
async def search_existing_news(api_key: str, limit: int = 100) -> Any:
    """Fetch recent CMS news for duplicate checking. ChatGPT should compare titles/topics itself."""
    _auth(api_key)
    limit = max(1, min(limit, 100))
    data = await _request("GET", "/api/portal/news")
    if isinstance(data, list):
        return data[:limit]
    return data


@mcp.tool()
async def get_news(api_key: str, news_id: str) -> Any:
    """Get one CMS news item by ID."""
    _auth(api_key)
    return await _request("GET", f"/api/portal/news/{news_id}")


@mcp.tool()
async def create_news(api_key: str, news: dict) -> Any:
    """Create a news article as a CMS draft."""
    _auth(api_key)
    return await _request("POST", "/api/portal/news", json=news)


@mcp.tool()
async def update_news(api_key: str, news_id: str, news: dict) -> Any:
    """Update a CMS news article."""
    _auth(api_key)
    return await _request("PATCH", f"/api/portal/news/{news_id}", json=news)


@mcp.tool()
async def upload_media_from_url(api_key: str, image_url: str, filename: str = "cover.jpg") -> Any:
    """Download an HTTPS image from a public host and upload it to the CMS media endpoint."""
    _auth(api_key)
    parsed = urlparse(image_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Only HTTPS image URLs are allowed")
    try:
        infos = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        for info in infos:
            addr = info[4][0]
            ip = ipaddress.ip_address(addr)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError("Private or internal image hosts are not allowed")
    except socket.gaierror as exc:
        raise ValueError("Could not resolve image host") from exc

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        r = await client.get(image_url)
        r.raise_for_status()
        content = r.content
        if len(content) > 12 * 1024 * 1024:
            raise ValueError("Image exceeds 12 MB limit")
        content_type = r.headers.get("content-type", "image/jpeg").split(";")[0].lower()
        allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
        if content_type not in allowed:
            raise ValueError(f"Unsupported image content type: {content_type}")

    token = await _login()
    async with httpx.AsyncClient(timeout=60) as client:
        files = {"file": (filename, content, content_type)}
        r = await client.post(f"{CMS_BASE_URL}/api/media/upload", headers=_headers(token), files=files)
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def submit_news(api_key: str, news_id: str) -> Any:
    """Submit a draft news item for CMS review."""
    _auth(api_key)
    return await _request("POST", f"/api/portal/news/{news_id}/submit")


@mcp.tool()
async def publish_news(api_key: str, news_id: str) -> Any:
    """Publish a news item. Disabled until NEDS_OPERATOR_PUBLISH_ENABLED=true."""
    _auth(api_key)
    if not PUBLISH_ENABLED:
        raise PermissionError("Publishing is disabled on this operator")
    return await _request("POST", f"/api/portal/news/{news_id}/publish")


@mcp.tool()
async def verify_published_news(api_key: str, news_id: str) -> Any:
    """Verify the public CMS response for a news item."""
    _auth(api_key)
    if not PORTAL_SLUG:
        raise RuntimeError("NEDS_PORTAL_SLUG is required for publication verification")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{CMS_BASE_URL}/api/public/portals/{PORTAL_SLUG}/news/{news_id}")
        r.raise_for_status()
        return r.json()


if __name__ == "__main__":
    _check_config()
    mcp.run(transport="streamable-http")
