"""Public representations of debates (full arena view and lightweight feed cards)."""
from __future__ import annotations

import time
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import get_logger
from backend.app.core.redis import get_redis
from backend.app.core.security import utcnow
from backend.app.engine.transitions import expected_turn
from backend.app.engine.types import ModerationStatus, Position, Round, Status
from backend.app.llm.registry import all_models
from backend.app.models import Claim, Debate, DebateRound, Side, Turn, User, Verdict, Vote

log = get_logger("provok.view")

HIDDEN_TEXT = "This turn is under review."
VIEWER_WINDOW_SECONDS = 60


def public_user(u: User | None) -> dict[str, Any] | None:
    if u is None or u.status == "deleted":
        return None if u is None else {"id": None, "username": "deleted", "display_name": "Deleted user",
                                       "avatar_url": None, "rating": None}
    return {"id": str(u.id), "username": u.username, "display_name": u.display_name, "avatar_url": u.avatar_url,
            "rating": u.rating}


async def viewer_counts(debate_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not debate_ids:
        return {}
    cutoff = time.time() - VIEWER_WINDOW_SECONDS
    try:
        pipe = get_redis().pipeline()
        for d in debate_ids:
            pipe.zcount(f"viewers:{d}", cutoff, "+inf")
        counts = await pipe.execute()
        return {d: int(c) for d, c in zip(debate_ids, counts)}
    except Exception as exc:
        log.warning("viewer_count_failed", error=str(exc))
        return {d: 0 for d in debate_ids}


def momentum_from_rounds(rounds: list[DebateRound]) -> dict[str, Any] | None:
    fw = aw = 0.0
    closed = 0
    for r in rounds:
        if r.vote_closed_at is not None and r.tally:
            fw += float(r.tally.get("for", 0))
            aw += float(r.tally.get("against", 0))
            closed += 1
    total = fw + aw
    if closed == 0 or total == 0:
        return None  # no lean to show until someone has actually voted
    return {"for_share": round(fw / total, 4), "rounds_closed": closed,
            "votes_weight": round(total, 2)}


async def _load_users(db: AsyncSession, sides: list[Side]) -> dict[uuid.UUID, User]:
    user_ids = {s.user_id for s in sides if s.user_id} | {s.invited_user_id for s in sides if s.invited_user_id}
    if not user_ids:
        return {}
    return {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(user_ids)))).all()}


async def _side_views(db: AsyncSession, sides: list[Side], users: dict[uuid.UUID, User] | None = None, *,
                      reveal_invite_token: bool = False) -> list[dict[str, Any]]:
    if users is None:
        users = await _load_users(db, sides)
    models = await all_models()
    out = []
    for s in sorted(sides, key=lambda x: 0 if x.position == Position.FOR else 1):
        model = None
        persona = None
        if s.swarm_config:
            m = models.get(s.swarm_config.get("model_key", ""))
            model = {"key": m.key, "display_name": m.display_name, "provider": m.provider, "tier": m.tier.value} \
                if m else {"key": s.swarm_config.get("model_key"), "display_name": "AI", "provider": None,
                           "tier": None}
            persona = s.swarm_config.get("persona")
        out.append({
            "id": str(s.id), "position": s.position, "participant_type": s.participant_type,
            "user": public_user(users.get(s.user_id)) if s.user_id else None,
            "invited": public_user(users.get(s.invited_user_id)) if s.invited_user_id else None,
            "model": model, "persona": persona, "ready": s.ready_at is not None,
            "invite_link": s.invite_token is not None,
            "invite_token": s.invite_token if reveal_invite_token else None,
        })
    return out


async def build_debate_view(db: AsyncSession, debate: Debate, viewer: User | None) -> dict[str, Any]:
    sides = list(debate.sides)
    side_pos = {s.id: s.position for s in sides}
    viewer_side = next((s for s in sides if viewer and s.user_id == viewer.id), None)
    is_admin = bool(viewer and viewer.is_admin)

    turns = (await db.scalars(select(Turn).where(Turn.debate_id == debate.id)
                              .order_by(Turn.created_at, Turn.turn_index))).all()
    rounds = (await db.scalars(select(DebateRound).where(DebateRound.debate_id == debate.id))).all()
    claims = (await db.scalars(select(Claim).where(Claim.debate_id == debate.id).order_by(Claim.seq))).all()
    claim_seq = {c.id: c.seq for c in claims}
    models = await all_models()

    turn_views = []
    for t in turns:
        hidden = t.moderation_status in (ModerationStatus.FLAGGED, ModerationStatus.HIDDEN)
        can_see = not hidden or is_admin or (viewer_side is not None and viewer_side.id == t.side_id)
        m = models.get(t.model_key or "")
        turn_views.append({
            "id": str(t.id), "round": t.round, "turn_index": t.turn_index, "position": side_pos.get(t.side_id),
            "kind": t.kind, "content": t.content if can_see else HIDDEN_TEXT, "hidden": hidden,
            "word_count": t.word_count, "source": t.source, "is_forfeit": t.is_forfeit,
            "model": {"key": m.key, "display_name": m.display_name} if m else None,
            "citations": (t.citations or []) if can_see else [], "created_at": t.created_at,
        })

    round_order = {r.value: i for i, r in enumerate(Round)}
    round_views = []
    for r in sorted(rounds, key=lambda x: round_order[x.round]):
        round_views.append({
            "round": r.round, "started_at": r.started_at, "ended_at": r.ended_at,
            "vote_open": r.vote_open, "vote_closes_at": r.vote_closes_at, "vote_closed_at": r.vote_closed_at,
            "tally": r.tally if r.vote_closed_at else None,
        })

    my_votes: dict[str, str] = {}
    if viewer:
        rows = (await db.execute(select(Vote.round, Vote.side_id).where(Vote.debate_id == debate.id,
                                                                        Vote.user_id == viewer.id))).all()
        my_votes = {rnd: side_pos.get(sid, "") for rnd, sid in rows}

    expected = None
    status = Status(debate.status)
    if status.is_round and debate.current_round:
        pos, kind = expected_turn(Round(debate.current_round), debate.current_turn_index)
        expected = {"position": pos.value, "kind": kind.value}

    verdict = None
    if status is Status.COMPLETED:
        v = await db.scalar(select(Verdict).where(Verdict.debate_id == debate.id))
        if v:
            verdict = {"winner_position": side_pos.get(v.winner_side_id) if v.winner_side_id else None,
                       "is_close": v.is_close, "scores": v.scores}

    viewers = (await viewer_counts([debate.id])).get(debate.id, 0)
    return {
        "id": str(debate.id), "question": debate.question, "topic_category": debate.topic_category,
        "mode": debate.mode, "timing": debate.timing, "status": debate.status,
        "current_round": debate.current_round, "turn_index": debate.current_turn_index, "expected": expected,
        "deadline_at": debate.deadline_at, "server_time": utcnow(), "word_limit": debate.word_limit,
        "is_featured": debate.is_featured, "paused_reason": debate.paused_reason,
        "conceded_position": debate.conceded_position,
        "created_at": debate.created_at, "started_at": debate.started_at, "completed_at": debate.completed_at,
        # Monotonic per state change: clients use it to discard out-of-order (stale) responses.
        "version": debate.updated_at.isoformat() if debate.updated_at else None,
        "created_by": str(debate.created_by) if debate.created_by else None,
        "sides": await _side_views(db, sides, reveal_invite_token=bool(viewer and debate.created_by == viewer.id)),
        "turns": turn_views, "rounds": round_views,
        "claims": [{"id": str(c.id), "seq": c.seq, "position": side_pos.get(c.side_id), "turn_id": str(c.turn_id),
                    "text": c.text, "source_url": c.source_url,
                    "responds_to": claim_seq.get(c.responds_to_claim_id) if c.responds_to_claim_id else None,
                    "status": c.status} for c in claims],
        "momentum": momentum_from_rounds(list(rounds)), "verdict": verdict, "viewers": viewers,
        "viewer": {
            "position": viewer_side.position if viewer_side else None,
            "is_creator": bool(viewer and debate.created_by == viewer.id),
            "is_admin": is_admin, "votes": my_votes,
        } if viewer else None,
    }


async def build_cards(db: AsyncSession, debates: list[Debate]) -> list[dict[str, Any]]:
    """Feed cards for many debates with a fixed number of queries."""
    if not debates:
        return []
    ids = [d.id for d in debates]
    sides = (await db.scalars(select(Side).where(Side.debate_id.in_(ids)))).all()
    by_debate: dict[uuid.UUID, list[Side]] = defaultdict(list)
    for s in sides:
        by_debate[s.debate_id].append(s)
    rounds = (await db.scalars(select(DebateRound).where(DebateRound.debate_id.in_(ids)))).all()
    rounds_by: dict[uuid.UUID, list[DebateRound]] = defaultdict(list)
    for r in rounds:
        rounds_by[r.debate_id].append(r)
    vote_counts = dict((await db.execute(select(Vote.debate_id, func.count()).where(Vote.debate_id.in_(ids))
                                         .group_by(Vote.debate_id))).all())
    winners = dict((await db.execute(select(Verdict.debate_id, Verdict.winner_side_id)
                                     .where(Verdict.debate_id.in_(ids)))).all())
    viewers = await viewer_counts(ids)
    users = await _load_users(db, list(sides))
    side_pos = {s.id: s.position for s in sides}
    out = []
    for d in debates:
        out.append({
            "id": str(d.id), "question": d.question, "topic_category": d.topic_category, "mode": d.mode,
            "timing": d.timing, "status": d.status, "current_round": d.current_round, "deadline_at": d.deadline_at,
            "is_featured": d.is_featured, "created_at": d.created_at, "completed_at": d.completed_at,
            "sides": await _side_views(db, by_debate[d.id], users),
            "momentum": momentum_from_rounds(rounds_by[d.id]),
            "votes": int(vote_counts.get(d.id, 0)), "viewers": viewers.get(d.id, 0),
            "winner_position": side_pos.get(winners[d.id]) if winners.get(d.id) else None,
        })
    return out
