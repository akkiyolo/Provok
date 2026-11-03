"""Seasonal moments (e.g. Diwali week): a date window with its own headline and question bank.

While a season is on, the Daily Debate and featured AI-vs-AI debates draw from its questions first, and the web app
shows the season's banner. Seasons live in `seasons.json` (data, not code); dates are inclusive, in local time
(`SEASON_UTC_OFFSET_MINUTES`). `SEASON_PREVIEW=<key>` forces one on, for checking the look before it starts.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.app.core.config import get_settings
from backend.app.core.security import utcnow

SEASONS_PATH = Path(__file__).with_name("seasons.json")


@lru_cache
def load_seasons(path: Path = SEASONS_PATH) -> tuple[dict[str, Any], ...]:
    seasons = json.loads(path.read_text(encoding="utf-8"))
    for s in seasons:
        s["start_date"], s["end_date"] = date.fromisoformat(s["start"]), date.fromisoformat(s["end"])
    return tuple(seasons)


def local_today(now: datetime | None = None) -> date:
    return ((now or utcnow()) + timedelta(minutes=get_settings().season_utc_offset_minutes)).date()


def active_season(day: date | None = None) -> dict[str, Any] | None:
    seasons = load_seasons()
    preview = get_settings().season_preview
    if preview:
        return next((s for s in seasons if s["key"] == preview), None)
    day = day or local_today()
    return next((s for s in seasons if s["start_date"] <= day <= s["end_date"]), None)


def seasonal_first(bank: list[dict], used: set[str], day: date | None = None) -> list[dict]:
    """Fresh questions from the active season, else fresh ones from `bank`, else the whole bank."""
    season = active_season(day)
    if season:
        fresh = [q for q in season["questions"] if q["question"] not in used]
        if fresh:
            return fresh
    return [q for q in bank if q["question"] not in used] or bank


def public_view(day: date | None = None) -> dict[str, Any]:
    season = active_season(day)
    if not season:
        return {"active": False}
    return {"active": True, "key": season["key"], "label": season["label"], "headline": season["headline"],
            "sub": season["sub"], "until": season["end"]}
