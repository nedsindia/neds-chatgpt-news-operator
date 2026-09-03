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

mcp = FastMCP("NEDS India 24x7 News Operator")

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


async def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=CMS_BASE_URL, timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=False)


async def _login() -> str:
    global _token
    _check_config()
    if _token:
        return _token
    async with await _client() as c:
        r = await c.post("/api/auth/login", json={"email": CMS_LOGIN_EMAIL, "password": CMS_LOGIN_PASSWORD})
        r.raise_for_status()
        data = r.json()
        _token = data["access_token"]
        return _token


async def _request(method: str, path: str, **kwargs: Any) -> Any:
    global _token
    token = await _login()
    headers = dict(kwargs.pop("headers", {}) or {})
    headers["Authorization"] = f"Bearer {token}"
    async with await _client() as c:
        r = await c.request(method, path, headers=headers, **kwargs)
        if r.status_code == 401:
            _token = None
            token = await _login()
            headers["Authorization"] = f"Bearer {token}"
            r = await c.request(method, path, headers=headers, **kwargs)
        if r.is_error:
            detail = r.text[:1000]
            raise RuntimeError(f"CMS {r.status_code}: {detail}")
        return r.json() if r.content else {"ok": True}


def _safe_external_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname:
        raise ValueError("Only HTTPS image URLs are allowed")
    host = p.hostname
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        ips = {i[4][0] for i in infos}
        for raw in ips:
            ip = ipaddress.ip_address(raw)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError("Blocked private/internal image host")
    except socket.gaierror as e:
        raise ValueError("Could not resolve image host") from e


@mcp.tool()
async def get_portal_settings(api_key: str) -> dict:
    """Return the connected portal settings, including its slug and name."""
    _auth(api_key)
    return await _request("GET", "/api/portal/settings")


@mcp.tool()
async def get_categories(api_key: str) -> list[dict]:
    """List categories available in the connected news portal."""
    _auth(api_key)
    return await _request("GET", "/api/portal/categories")


@mcp.tool()
async def search_existing_news(api_key: str, status: Optional[str] = None, limit: int = 100) -> list[dict]:
    """Fetch portal news so ChatGPT can check for duplicates before creating an article."""
    _auth(api_key)
    limit = max(1, min(limit, 500))
    params = {"status": status} if status else {}
    data = await _request("GET", "/api/portal/news", params=params)
    if isinstance(data, list):
        return data[:limit]
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"][:limit]
    return data


@mcp.tool()
async def get_news(api_key: str, news_id: str) -> dict:
    """Get one CMS news item by ID."""
    _auth(api_key)
    return await _request("GET", f"/api/portal/news/{news_id}")


@mcp.tool()
async def create_news(
    api_key: str,
    title: str,
    subtitle: str,
    body: str,
    category_id: str,
    tags: list[str],
    language: str = "hi",
    location: Optional[str] = None,
    breaking: bool = False,
    cover_image: Optional[str] = None,
    video_url: Optional[str] = None,
    documents: Optional[list[str]] = None,
    gallery: Optional[list[str]] = None,
) -> dict:
    """Create a draft news item. Does not publish it."""
    _auth(api_key)
    payload = {
        "title": title, "subtitle": subtitle, "body": body,
        "category_id": category_id, "tags": tags, "language": language,
        "breaking": breaking,
    }
    if location is not None: payload["location"] = location
    if cover_image is not None: payload["cover_image"] = cover_image
    if video_url is not None: payload["video_url"] = video_url
    if documents is not None: payload["documents"] = documents
    if gallery is not None: payload["gallery"] = gallery
    return await _request("POST", "/api/portal/news", json=payload)


@mcp.tool()
async def update_news(
    api_key: str,
    news_id: str,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    body: Optional[str] = None,
    category_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
    location: Optional[str] = None,
    breaking: Optional[bool] = None,
    trending: Optional[bool] = None,
    cover_image: Optional[str] = None,
    video_url: Optional[str] = None,
    seo_title: Optional[str] = None,
    seo_description: Optional[str] = None,
    keywords: Optional[list[str]] = None,
) -> dict:
    """Update an existing news item, including SEO fields."""
    _auth(api_key)
    fields = locals().copy()
    fields.pop("api_key", None); fields.pop("news_id", None)
    payload = {k: v for k, v in fields.items() if v is not None}
    return await _request("PATCH", f"/api/portal/news/{news_id}", json=payload)


@mcp.tool()
async def upload_media_from_url(api_key: str, image_url: str, kind: str = "news") -> dict:
    """Download a public HTTPS image and upload it to the CMS media endpoint."""
    _auth(api_key)
    _safe_external_url(image_url)
    async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0), follow_redirects=False) as ext:
        r = await ext.get(image_url)
        r.raise_for_status()
        if len(r.content) > 12 * 1024 * 1024:
            raise ValueError("Image exceeds 12 MB limit")
        content_type = (r.headers.get("content-type") or "").split(";")[0].lower()
        if content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
            raise ValueError("URL did not return a supported image type")
        filename = image_url.split("/")[-1].split("?")[0] or "cover-image"
    token = await _login()
    async with await _client() as c:
        rr = await c.post(
            "/api/media/upload", params={"kind": kind},
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (filename, r.content, content_type)},
        )
        if rr.status_code == 401:
            global _token
            _token = None
            token = await _login()
            rr = await c.post("/api/media/upload", params={"kind": kind}, headers={"Authorization": f"Bearer {token}"}, files={"file": (filename, r.content, content_type)})
        if rr.is_error:
            raise RuntimeError(f"CMS {rr.status_code}: {rr.text[:1000]}")
        return rr.json()


@mcp.tool()
async def submit_news(api_key: str, news_id: str) -> dict:
    """Submit a created news item into the CMS review workflow."""
    _auth(api_key)
    return await _request("POST", f"/api/portal/news/{news_id}/submit")


@mcp.tool()
async def publish_news(api_key: str, news_id: str) -> dict:
    """Publish a news item. Disabled until NEDS_OPERATOR_PUBLISH_ENABLED=true."""
    _auth(api_key)
    if not PUBLISH_ENABLED:
        raise PermissionError("Publishing is disabled on this connector")
    return await _request("POST", f"/api/portal/news/{news_id}/publish")


@mcp.tool()
async def verify_published_news(api_key: str, news_id: str) -> dict:
    """Verify the public portal response for a published news item."""
    _auth(api_key)
    slug = PORTAL_SLUG
    if not slug:
        settings = await _request("GET", "/api/portal/settings")
        slug = settings.get("slug", "")
    if not slug:
        raise RuntimeError("Portal slug is not configured or available")
    async with httpx.AsyncClient(base_url=CMS_BASE_URL, timeout=20.0, follow_redirects=False) as c:
        r = await c.get(f"/api/public/portals/{slug}/news/{news_id}")
        if r.is_error:
            raise RuntimeError(f"Public verification failed: {r.status_code}: {r.text[:1000]}")
        return {"verified": True, "status_code": r.status_code, "news": r.json()}


if __name__ == "__main__":
    _check_config()
    mcp.run(transport="streamable-http")
