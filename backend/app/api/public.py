"""Meta/config, leaderboards, search, reports and analytics ingestion."""
from __future__ import annotations

import re
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import case, desc, func, select

from backend.app.api.deps import DB, CurrentUser, OptionalUser
from backend.app.core.config import get_settings
from backend.app.core.errors import AppError, NotFound
from backend.app.core.ratelimit import client_ip, enforce
from backend.app.engine.types import Persona, Status, UserStatus
from backend.app.llm.registry import all_models, selectable_debaters
from backend.app.models import AnalyticsEvent, Debate, Post, Report, Side, Turn, User, Verdict
from backend.app.moderation.content import TOPIC_CATEGORIES
from backend.app.services import flags
from backend.app.services import posts as posts_svc
from backend.app.services.debate_view import build_cards, public_user
from backend.app.swarm.context import PERSONAS

router = APIRouter()


@router.get("/meta")
async def meta() -> dict:
    s = get_settings()
    models = await selectable_debaters()
    standard = [m for m in models if m.tier.value == "standard"]
    preferred = next((m for m in standard if m.key == s.default_swarm_model_key), standard[0] if standard else None)
    return {
        # A free-eligible default, so "debate an AI now" never lands a new user on a paywall.
        "default_model_key": preferred.key if preferred else (models[0].key if models else None),
        "models": [{"key": m.key, "display_name": m.display_name, "provider": m.provider, "tier": m.tier.value}
                   for m in models],
        "personas": [{"key": p.value, "description": PERSONAS[p]} for p in Persona],
        "word_limit": {"default": s.default_word_limit, "min": s.min_word_limit, "max": s.max_word_limit},
        "timings": {"live": s.live_turn_seconds, "async": s.async_turn_seconds, "video": s.video_turn_seconds},
        "free_ai_debates": s.free_ai_debates,
        "credit_costs": {"standard": s.standard_credit_cost, "flagship": s.flagship_credit_cost},
        "free_covers_flagship": s.free_debates_cover_flagship,
        "categories": [c for c in TOPIC_CATEGORIES if c not in s.blocked_categories],
        "blocked_categories": sorted(s.blocked_categories),
        "features": {
            "ai_debates": await flags.is_enabled(flags.AI_DEBATES),
            "video": s.livekit_enabled and await flags.is_enabled(flags.VIDEO_DEBATES),
            "payments": s.razorpay_enabled and await flags.is_enabled(flags.PAYMENTS),
            "google_login": s.google_oauth_enabled,
            "signups": await flags.is_enabled(flags.SIGNUPS),
        },
        "livekit_url": s.livekit_url or None,
        "question_chars": {"min": s.question_min_chars, "max": s.question_max_chars},
    }


# ── Leaderboards ───────────────────────────────────────────────────────────


@router.get("/leaderboard")
async def leaderboard(db: DB, type: Literal["human", "model"] = "human",
                      category: str | None = Query(default=None, max_length=40),
                      limit: int = Query(default=50, ge=1, le=100)) -> dict:
    if type == "human":
        rows = (await db.scalars(select(User).where(User.status == UserStatus.ACTIVE,
                                                    (User.wins + User.losses + User.draws) > 0)
                                 .order_by(desc(User.rating), desc(User.wins)).limit(limit))).all()
        return {"type": "human", "items": [
            {**(public_user(u) or {}), "wins": u.wins, "losses": u.losses, "draws": u.draws, "rank": i + 1}
            for i, u in enumerate(rows)]}

    model_key = Side.swarm_config["model_key"].astext
    won = case((Verdict.winner_side_id == Side.id, 1), else_=0)
    draw = case((Verdict.winner_side_id.is_(None), 1), else_=0)
    q = (select(model_key.label("model_key"), func.count().label("played"), func.sum(won).label("wins"),
                func.sum(draw).label("draws"))
         .select_from(Side).join(Verdict, Verdict.debate_id == Side.debate_id)
         .join(Debate, Debate.id == Side.debate_id)
         .where(Side.participant_type == "swarm", Debate.status == Status.COMPLETED.value)
         .group_by(model_key))
    if category:
        q = q.where(Debate.topic_category == category)
    models = await all_models()
    items = []
    for key, played, wins, draws in (await db.execute(q)).all():
        m = models.get(key)
        if m is None:
            continue
        wins, draws = int(wins or 0), int(draws or 0)
        items.append({"key": key, "display_name": m.display_name, "provider": m.provider, "tier": m.tier.value,
                      "rating": m.rating, "played": int(played), "wins": wins, "draws": draws,
                      "losses": int(played) - wins - draws,
                      "win_rate": round((wins + 0.5 * draws) / played, 4) if played else 0.0})
    items.sort(key=lambda x: (-x["win_rate"], -x["played"]))
    return {"type": "model", "category": category, "items": items[:limit]}


# ── Search ─────────────────────────────────────────────────────────────────


def _like(q: str) -> str:
    return "%" + re.sub(r"([%_\\])", r"\\\1", q) + "%"


@router.get("/search")
async def search(request: Request, db: DB, q: str = Query(min_length=1, max_length=100)) -> dict:
    await enforce("search", client_ip(request), "60/60")
    term = _like(" ".join(q.split()))
    debates = list((await db.scalars(select(Debate).where(Debate.question.ilike(term, escape="\\"),
                                                          Debate.is_hidden.is_(False),
                                                          Debate.status.not_in(["cancelled", "abandoned"]))
                                     .order_by(desc(Debate.created_at)).limit(20))).all())
    users = (await db.scalars(select(User).where(
        (User.username.ilike(term, escape="\\")) | (User.display_name.ilike(term, escape="\\")),
        User.status == UserStatus.ACTIVE).order_by(desc(User.rating)).limit(10))).all()
    viewer = None  # search results are the same for everyone; viewer flags come from the post views
    found = await posts_svc.search_posts(db, term, viewer)
    return {"debates": await build_cards(db, debates), "users": [public_user(u) for u in users],
            "posts": await posts_svc.build_views(db, found, viewer)}


# ── Reports ────────────────────────────────────────────────────────────────

REPORT_REASONS = ("harassment", "hate", "spam", "misinformation", "sexual", "violence", "self_harm",
                  "impersonation", "cheating", "other")


class ReportIn(BaseModel):
    target_type: Literal["debate", "turn", "user", "post"]
    target_id: uuid.UUID
    reason: Literal[REPORT_REASONS]  # type: ignore[valid-type]
    details: str | None = Field(default=None, max_length=1000)


@router.post("/reports", status_code=201)
async def report(body: ReportIn, user: CurrentUser, db: DB) -> dict:
    await enforce("report", str(user.id), get_settings().rl_report_user)
    model = {"debate": Debate, "turn": Turn, "user": User, "post": Post}[body.target_type]
    if await db.get(model, body.target_id) is None:
        raise NotFound("We couldn't find what you're reporting.")
    existing = await db.scalar(select(Report.id).where(Report.reporter_id == user.id,
                                                       Report.target_type == body.target_type,
                                                       Report.target_id == body.target_id))
    if not existing:
        db.add(Report(reporter_id=user.id, target_type=body.target_type, target_id=body.target_id,
                      reason=body.reason, details=body.details))
        await db.commit()
    return {"ok": True, "message": "Thanks — our moderators will take a look."}


# ── Analytics ──────────────────────────────────────────────────────────────

CLIENT_EVENTS = {
    "page_view", "share_clicked", "share_completed", "vote_prompt_shown", "signup_started", "login_prompt_shown",
    "onboarding_step", "create_started", "create_step", "matchup_selected", "wallet_viewed", "checkout_opened",
    "verdict_viewed", "clip_played", "rematch_clicked", "pwa_installed",
}


class EventIn(BaseModel):
    name: str = Field(max_length=64)
    anon_id: str | None = Field(default=None, max_length=64)
    debate_id: uuid.UUID | None = None
    props: dict[str, Any] | None = None


@router.post("/events", status_code=202)
async def track(body: EventIn, request: Request, db: DB, user: OptionalUser) -> dict:
    await enforce("events", client_ip(request), get_settings().rl_events_ip)
    if body.name not in CLIENT_EVENTS:
        raise AppError("Unknown event.", code="unknown_event", status_code=422)
    props = {k: v for k, v in (body.props or {}).items() if isinstance(v, (str, int, float, bool)) and len(k) <= 40}
    props = {k: (v[:200] if isinstance(v, str) else v) for k, v in list(props.items())[:20]}
    db.add(AnalyticsEvent(name=body.name, user_id=user.id if user else None, anon_id=body.anon_id,
                          debate_id=body.debate_id, props=props))
    await db.commit()
    return {"ok": True}
