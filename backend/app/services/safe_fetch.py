"""
SSRF-safe HTTP fetching for user-supplied URLs (citation checks).

- http/https only, standard ports only
- every hop's hostname is resolved and must map to public IPs only
- redirects followed manually (max 3), each re-validated
- hard timeout and byte cap; text-like content types only
"""
from __future__ import annotations

import asyncio
import html as html_lib
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx

from backend.app.core.config import get_settings


class FetchBlocked(Exception):
    pass


_ALLOWED_PORTS = {None, 80, 443}
_TEXT_TYPES = ("text/html", "text/plain", "application/xhtml+xml", "application/xml", "text/xml")


def _ip_is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved
                or addr.is_unspecified or (addr.version == 6 and addr.ipv4_mapped is not None
                                           and not _ip_is_public(str(addr.ipv4_mapped))))


async def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchBlocked("scheme not allowed")
    if not parsed.hostname or parsed.username or parsed.password:
        raise FetchBlocked("bad host")
    if parsed.port not in _ALLOWED_PORTS:
        raise FetchBlocked("port not allowed")
    host = parsed.hostname
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchBlocked("dns failure") from exc
    ips = {i[4][0] for i in infos}
    if not ips or not all(_ip_is_public(ip) for ip in ips):
        raise FetchBlocked("non-public address")
    return url


_SCRIPT_RE = re.compile(r"<(script|style|noscript|svg|nav|footer|header)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def html_to_text(raw: str) -> str:
    raw = _SCRIPT_RE.sub(" ", raw)
    raw = _TAG_RE.sub(" ", raw)
    return _WS_RE.sub(" ", html_lib.unescape(raw)).strip()


async def fetch_text(url: str, *, max_chars: int = 12_000) -> str:
    s = get_settings()
    current = url
    async with httpx.AsyncClient(timeout=s.citation_fetch_timeout_seconds, follow_redirects=False,
                                 headers={"User-Agent": "ProvokCitationCheck/1.0 (+https://provok.app)"}) as client:
        for _ in range(4):
            await validate_url(current)
            async with client.stream("GET", current) as resp:
                if resp.is_redirect:
                    loc = resp.headers.get("location")
                    if not loc:
                        raise FetchBlocked("redirect without location")
                    current = urljoin(current, loc)
                    continue
                if resp.status_code >= 400:
                    raise FetchBlocked(f"status {resp.status_code}")
                ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype and not ctype.startswith(_TEXT_TYPES):
                    raise FetchBlocked(f"content-type {ctype}")
                chunks: list[bytes] = []
                size = 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    chunks.append(chunk)
                    if size >= s.citation_fetch_max_bytes:
                        break
                body = b"".join(chunks)[: s.citation_fetch_max_bytes].decode(resp.encoding or "utf-8", "replace")
                text = html_to_text(body) if "html" in ctype or not ctype else body
                return text[:max_chars]
    raise FetchBlocked("too many redirects")
