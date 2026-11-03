"""Seasonal moments: the date window, IST dates, seasonal questions first, the public endpoint, and topic safety."""
from __future__ import annotations

from datetime import UTC, date, datetime

from backend.app.core.config import get_settings
from backend.app.moderation.content import TOPIC_CATEGORIES, heuristic_blocked_category
from backend.app.services import seasons
from backend.app.services.featured import load_questions

A = "/api/v1"
DIWALI = next(s for s in seasons.load_seasons() if s["key"] == "diwali-2026")
DIWALI_QS = {q["question"] for q in DIWALI["questions"]}


def test_season_window_is_inclusive():
    assert seasons.active_season(date(2026, 10, 31)) is None
    assert seasons.active_season(date(2026, 11, 1))["key"] == "diwali-2026"
    assert seasons.active_season(date(2026, 11, 8))["key"] == "diwali-2026"
    assert seasons.active_season(date(2026, 11, 12))["key"] == "diwali-2026"
    assert seasons.active_season(date(2026, 11, 13)) is None


def test_dates_are_local_time():
    # 20:00 UTC on 31 Oct is already 1 Nov in India.
    assert seasons.local_today(datetime(2026, 10, 31, 20, 0, tzinfo=UTC)) == date(2026, 11, 1)
    assert seasons.local_today(datetime(2026, 10, 31, 18, 0, tzinfo=UTC)) == date(2026, 10, 31)


def test_seasonal_questions_come_first_then_the_regular_bank():
    bank = load_questions()
    picked = seasons.seasonal_first(bank, set(), date(2026, 11, 3))
    assert {q["question"] for q in picked} == DIWALI_QS
    all_used = seasons.seasonal_first(bank, DIWALI_QS, date(2026, 11, 3))
    assert {q["question"] for q in all_used} == {q["question"] for q in bank}  # season exhausted: regular bank
    assert seasons.seasonal_first(bank, set(), date(2026, 12, 1)) == bank


def test_every_canned_question_passes_the_topic_policy():
    blocked = get_settings().blocked_categories
    questions = load_questions() + [q for s in seasons.load_seasons() for q in s["questions"]]
    for q in questions:
        assert heuristic_blocked_category(q["question"]) is None, q["question"]
        assert q["category"] in TOPIC_CATEGORIES and q["category"] not in blocked, q
        assert get_settings().question_min_chars <= len(q["question"]) <= get_settings().question_max_chars
    assert len({q["question"] for q in questions}) == len(questions)  # no duplicates across banks


async def test_season_endpoint_and_preview(client, monkeypatch):
    r = (await client.get(f"{A}/season")).json()
    assert r["active"] is (seasons.active_season() is not None)
    monkeypatch.setattr(get_settings(), "season_preview", "diwali-2026")
    r = (await client.get(f"{A}/season")).json()
    assert r == {"active": True, "key": "diwali-2026", "label": "Diwali", "headline": DIWALI["headline"],
                 "sub": DIWALI["sub"], "until": "2026-11-12"}


async def test_daily_debate_uses_the_season(client):
    from backend.app.services.daily import create_daily
    row = await create_daily(date(2026, 11, 5))
    assert row is not None and row.question in DIWALI_QS
