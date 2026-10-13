"""Link preview cards: title, description and image of the first link in a post, read from the page's <head>.

Fetched after posting by a background job through the SSRF-safe fetcher. Values are plain text (the web app
renders them as text, never HTML) and the image must be an absolute http(s) URL.
"""
from __future__ import annotations

import html
import re
import uuid
from typing import Any
from urllib.parse import urljoin, urlparse

from backend.app.core.logging import get_logger
from backend.app.db.session import session_scope
from backend.app.models import Post
from backend.app.moderation.content import URL_RE
from backend.app.services.safe_fetch import FetchBlocked, fetch_html

log = get_logger("provok.link_preview")

_META_RE = re.compile(r"<meta\s+[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r'([a-zA-Z:_-]+)\s*=\s*("([^"]*)"|\'([^\']*)\')')
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TRAILING = ".,:;!?)]}'\""


def first_url(text: str | None) -> str | None:
    m = URL_RE.search(text or "")
    return m.group(0).rstrip(_TRAILING) if m else None


def _clean(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    v = " ".join(html.unescape(value).split())
    return v[:limit] or None


def parse_preview(page: str, url: str) -> dict[str, Any] | None:
    head = page[: page.lower().find("</head>")] if "</head>" in page.lower() else page[:200_000]
    meta: dict[str, str] = {}
    for tag in _META_RE.findall(head):
        attrs = {k.lower(): (v1 if v1 is not None else v2) for k, _, v1, v2 in
                 ((m[0], m[1], m[2] or None, m[3]) for m in _ATTR_RE.findall(tag))}
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key and attrs.get("content") and key not in meta:
            meta[key] = attrs["content"]
    title = meta.get("og:title") or meta.get("twitter:title")
    if not title and (t := _TITLE_RE.search(head)):
        title = t.group(1)
    title = _clean(title, 200)
    if not title:
        return None
    image = meta.get("og:image") or meta.get("twitter:image")
    image = urljoin(url, image.strip()) if image else None
    if image and urlparse(image).scheme not in ("http", "https"):
        image = None
    host = urlparse(url).hostname or ""
    return {"url": url, "title": title, "description": _clean(meta.get("og:description") or meta.get("description"), 300),
            "image": image[:1000] if image else None,
            "site": _clean(meta.get("og:site_name"), 80) or host.removeprefix("www.")}


async def fetch_preview(url: str) -> dict[str, Any] | None:
    try:
        page, final = await fetch_html(url)
    except (FetchBlocked, Exception) as exc:  # any network failure just means no card
        log.info("link_preview_unavailable", url=url[:200], error=str(exc)[:120])
        return None
    return parse_preview(page, final)


async def attach_preview(post_id: uuid.UUID) -> None:
    async with session_scope() as db:
        post = await db.get(Post, post_id)
        url = first_url(post.text) if post and post.status == "visible" else None
    if not url:
        return
    preview = await fetch_preview(url)
    if preview is None:
        return
    async with session_scope() as db:
        post = await db.get(Post, post_id)
        if post is not None and post.link_preview is None:
            post.link_preview = preview
