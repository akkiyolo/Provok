"""Web research behind a swappable interface (Tavily by default)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger

log = get_logger("provok.search")


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    content: str


class SearchProvider(Protocol):
    async def search(self, query: str, max_results: int) -> list[SearchResult]: ...


class TavilySearch:
    endpoint = "https://api.tavily.com/search"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        payload = {"api_key": self.api_key, "query": query[:400], "max_results": max_results,
                   "search_depth": "advanced", "include_answer": False, "include_raw_content": False}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(self.endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return [SearchResult(str(r.get("title", ""))[:200], str(r.get("url", "")), str(r.get("content", ""))[:1500])
                for r in data.get("results", []) if r.get("url", "").startswith(("http://", "https://"))]


class NoSearch:
    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        return []


_override: SearchProvider | None = None


def set_search_provider(p: SearchProvider | None) -> None:
    global _override
    _override = p


def get_search_provider() -> SearchProvider:
    if _override is not None:
        return _override
    key = get_settings().tavily_key
    return TavilySearch(key) if key else NoSearch()


async def safe_search(query: str, max_results: int | None = None) -> list[SearchResult]:
    try:
        return await get_search_provider().search(query, max_results or get_settings().research_max_results)
    except Exception as exc:
        log.warning("search_failed", error=str(exc), query=query[:80])
        return []
