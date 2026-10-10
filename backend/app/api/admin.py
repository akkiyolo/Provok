"""Admin: moderation queue, actions (all audited), flags/kill switches, model registry, launch metrics."""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, distinct, func, select, text

from backend.app.api.deps import DB, AdminUser
from backend.app.core.config import get_settings
from backend.app.core.errors import AppError, NotFound
from backend.app.core.security import utcnow
from backend.app.engine import transitions as tx
from backend.app.engine.service import apply_event, get_debate_for_update
from backend.app.engine.types import ModerationStatus, UserStatus
from backend.app.llm.registry import invalidate_cache
from backend.app.models import (
    AuditLog,
    Debate,
    FeatureFlag,
    LLMCall,
    ModelRegistry,
    Report,
    Turn,
    User,
)
from backend.app.payments.credits import apply_credit
from backend.app.services import auth as auth_svc
from backend.app.services import flags
from backend.app.services.outbox import Outbox

router = APIRouter()


@router.get("/reports")
async def reports(db: DB, admin: AdminUser, status: Literal["open", "actioned", "dismissed"] = "open",
                  limit: int = Query(default=50, ge=1, le=200)) -> dict:
    rows = (await db.scalars(select(Report).where(Report.status == status).order_by(desc(Report.created_at))
                             .limit(limit))).all()
    out = []
    for r in rows:
        preview = None
        if r.target_type == "turn":
            t = await db.get(Turn, r.target_id)
            preview = {"content": t.content[:500], "debate_id": str(t.debate_id),
                       "moderation_status": t.moderation_status} if t else None
        elif r.target_type == "debate":
            d = await db.get(Debate, r.target_id)
            preview = {"question": d.question, "is_hidden": d.is_hidden} if d else None
        elif r.target_type == "user":
            u = await db.get(User, r.target_id)
            preview = {"username": u.username, "status": u.status} if u else None
        out.append({"id": str(r.id), "target_type": r.target_type, "target_id": str(r.target_id), "reason": r.reason,
                    "details": r.details, "status": r.status, "created_at": r.created_at, "preview": preview})
    return {"items": out}


@router.get("/flagged-turns")
async def flagged_turns(db: DB, admin: AdminUser) -> dict:
    rows = (await db.scalars(select(Turn).where(Turn.moderation_status == ModerationStatus.FLAGGED.value)
                             .order_by(desc(Turn.created_at)).limit(100))).all()
    return {"items": [{"id": str(t.id), "debate_id": str(t.debate_id), "content": t.content,
                       "reason": t.moderation_reason, "injection_flag": t.injection_flag,
                       "created_at": t.created_at} for t in rows]}


@router.get("/paused-debates")
async def paused(db: DB, admin: AdminUser) -> dict:
    rows = (await db.scalars(select(Debate).where(Debate.status == "paused").order_by(desc(Debate.updated_at))
                             .limit(100))).all()
    return {"items": [{"id": str(d.id), "question": d.question, "reason": d.paused_reason,
                       "paused_from": d.paused_from, "updated_at": d.updated_at} for d in rows]}


Action = Literal[
    "hide_turn", "approve_turn", "hide_debate", "unhide_debate", "feature_debate", "unfeature_debate",
    "ban_user", "unban_user", "restrict_user", "unrestrict_user", "resume_debate", "cancel_debate",
    "resolve_report", "dismiss_report", "grant_credits", "make_admin",
]


class ActionIn(BaseModel):
    action: Action
    target_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=300)
    amount: int | None = Field(default=None, ge=1, le=1000)


@router.post("/actions")
async def act(body: ActionIn, db: DB, admin: AdminUser) -> dict:
    a, tid = body.action, body.target_id
    outbox = Outbox()

    async def get(model):
        obj = await db.get(model, tid)
        if obj is None:
            raise NotFound("Target not found.")
        return obj

    if a in ("hide_turn", "approve_turn"):
        t = await get(Turn)
        t.moderation_status = (ModerationStatus.HIDDEN if a == "hide_turn" else ModerationStatus.APPROVED).value
    elif a in ("hide_debate", "unhide_debate"):
        (await get(Debate)).is_hidden = a == "hide_debate"
    elif a in ("feature_debate", "unfeature_debate"):
        (await get(Debate)).is_featured = a == "feature_debate"
    elif a in ("ban_user", "unban_user", "restrict_user", "unrestrict_user"):
        u = await get(User)
        if u.id == admin.id:
            raise AppError("You can't change your own status.", code="self_action")
        u.status = {"ban_user": UserStatus.BANNED, "restrict_user": UserStatus.RESTRICTED}.get(a, UserStatus.ACTIVE)
        if a == "ban_user":
            await auth_svc.revoke_all(db, u)
        if a == "unrestrict_user":
            u.injection_strikes = 0
    elif a in ("resume_debate", "cancel_debate"):
        debate = await get_debate_for_update(db, tid)
        event = tx.Resumed(utcnow()) if a == "resume_debate" else tx.Cancelled(admin.id, utcnow(), is_admin=True)
        try:
            outcome = await apply_event(db, debate, event)
        except tx.InvalidTransition as exc:
            raise AppError(exc.message, code=exc.code, status_code=409) from exc
        outbox.extend(outcome.outbox)
    elif a in ("resolve_report", "dismiss_report"):
        r = await get(Report)
        r.status = "actioned" if a == "resolve_report" else "dismissed"
        r.resolved_by, r.resolved_at = admin.id, utcnow()
    elif a == "grant_credits":
        await get(User)
        await apply_credit(db, tid, body.amount or 1, "grant", ref_id=str(admin.id),
                           idempotency_key=f"grant:{tid}:{uuid.uuid4()}")
    elif a == "make_admin":
        (await get(User)).role = "admin"
    db.add(AuditLog(actor_id=admin.id, action=a, target_type=a.split("_", 1)[1], target_id=str(tid),
                    details={"reason": body.reason, "amount": body.amount}))
    await db.commit()
    await outbox.flush()
    return {"ok": True}


# ── Flags / kill switches ──────────────────────────────────────────────────


@router.get("/flags")
async def get_flags(db: DB, admin: AdminUser) -> dict:
    rows = {r.key: r for r in (await db.scalars(select(FeatureFlag))).all()}
    return {"items": [{"key": k, "enabled": rows[k].enabled if k in rows else v,
                       "reason": rows[k].reason if k in rows else None} for k, v in flags.DEFAULTS.items()]}


class FlagIn(BaseModel):
    enabled: bool
    reason: str | None = Field(default=None, max_length=300)


@router.put("/flags/{key}")
async def put_flag(key: str, body: FlagIn, db: DB, admin: AdminUser) -> dict:
    if key not in flags.DEFAULTS:
        raise NotFound("Unknown flag.")
    await flags.set_flag(db, key, body.enabled, body.reason)
    db.add(AuditLog(actor_id=admin.id, action="set_flag", target_type="flag", target_id=key,
                    details={"enabled": body.enabled, "reason": body.reason}))
    await db.commit()
    return {"ok": True}


# ── Model registry ─────────────────────────────────────────────────────────


@router.get("/models")
async def models(db: DB, admin: AdminUser) -> dict:
    rows = (await db.scalars(select(ModelRegistry).order_by(ModelRegistry.sort_order))).all()
    return {"items": [{"key": m.key, "litellm_id": m.litellm_id, "display_name": m.display_name,
                       "provider": m.provider, "tier": m.tier, "enabled": m.enabled, "selectable": m.selectable,
                       "rating": m.rating, "notes": m.notes} for m in rows]}


class ModelPatch(BaseModel):
    enabled: bool | None = None
    selectable: bool | None = None
    litellm_id: str | None = Field(default=None, max_length=200)
    display_name: str | None = Field(default=None, max_length=80)
    tier: Literal["standard", "flagship", "utility", "judge"] | None = None


@router.patch("/models/{key}")
async def patch_model(key: str, body: ModelPatch, db: DB, admin: AdminUser) -> dict:
    m = await db.get(ModelRegistry, key)
    if m is None:
        raise NotFound("Unknown model.")
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(m, k, v)
    db.add(AuditLog(actor_id=admin.id, action="update_model", target_type="model", target_id=key, details=changes))
    await db.commit()
    invalidate_cache()
    return {"ok": True}


# ── Launch metrics (spec §13) ──────────────────────────────────────────────


@router.get("/metrics")
async def metrics(db: DB, admin: AdminUser, days: int = Query(default=30, ge=1, le=365)) -> dict:
    since = utcnow() - timedelta(days=days)
    by_mode = (await db.execute(
        select(Debate.mode, Debate.timing, func.count(), func.count().filter(Debate.status == "completed"))
        .where(Debate.created_at >= since, Debate.started_at.is_not(None))
        .group_by(Debate.mode, Debate.timing))).all()
    completion = [{"mode": m, "timing": t, "started": int(n), "completed": int(c or 0),
                   "completion_rate": round(int(c or 0) / int(n), 4) if n else 0} for m, t, n, c in by_mode]

    votes_per_debate = await db.scalar(text("""
        SELECT COALESCE(AVG(n), 0) FROM (
          SELECT d.id, COUNT(v.id) AS n FROM debates d
          LEFT JOIN votes v ON v.debate_id = d.id
          WHERE d.status = 'completed' AND d.created_at >= :since GROUP BY d.id) x"""), {"since": since})

    second_debate = (await db.execute(text("""
        WITH firsts AS (
          SELECT created_by AS uid, MIN(created_at) AS first_at FROM debates
          WHERE created_by IS NOT NULL GROUP BY created_by HAVING MIN(created_at) >= :since)
        SELECT COUNT(*) AS cohort,
               COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM debates d WHERE d.created_by = f.uid
                   AND d.created_at > f.first_at AND d.created_at <= f.first_at + interval '7 days')) AS returned
        FROM firsts f"""), {"since": since})).one()

    cost_rows = (await db.execute(text("""
        SELECT d.mode, COUNT(DISTINCT d.id) AS debates, COALESCE(SUM(c.cost_usd), 0) AS cost
        FROM debates d JOIN llm_calls c ON c.debate_id = d.id
        WHERE d.status = 'completed' AND d.created_at >= :since GROUP BY d.mode"""), {"since": since})).all()

    conversion = (await db.execute(text("""
        SELECT COUNT(*) FILTER (WHERE free_ai_debates_used >= :free) AS exhausted,
               COUNT(*) FILTER (WHERE free_ai_debates_used >= :free AND EXISTS (
                   SELECT 1 FROM payments p WHERE p.user_id = u.id AND p.status = 'paid')) AS paid
        FROM users u WHERE u.created_at >= :since"""),
        {"since": since, "free": get_settings().free_ai_debates})).one()

    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    spend_today = await db.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0))
                                  .where(LLMCall.created_at >= today))
    users_total = await db.scalar(select(func.count()).select_from(User).where(User.status != "deleted"))
    dau = await db.scalar(select(func.count(distinct(User.id))).where(User.last_login_at >= utcnow() - timedelta(days=1)))
    return {
        "window_days": days,
        "completion_by_mode": completion,
        "avg_votes_per_completed_debate": round(float(votes_per_debate or 0), 2),
        "second_debate_within_7d": {"cohort": second_debate.cohort, "returned": second_debate.returned,
                                    "rate": round(second_debate.returned / second_debate.cohort, 4)
                                    if second_debate.cohort else 0},
        "cost_per_completed_debate": [{"mode": m, "debates": int(n), "total_usd": float(c),
                                       "per_debate_usd": round(float(c) / int(n), 4) if n else 0}
                                      for m, n, c in cost_rows],
        "free_to_paid": {"exhausted_free": conversion.exhausted, "paid": conversion.paid,
                         "rate": round(conversion.paid / conversion.exhausted, 4) if conversion.exhausted else 0},
        "llm_spend_today_usd": float(spend_today or 0),
        "users_total": users_total or 0, "active_last_24h": dau or 0,
    }


@router.get("/audit")
async def audit(db: DB, admin: AdminUser, limit: int = Query(default=100, ge=1, le=500)) -> dict:
    rows = (await db.scalars(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit))).all()
    return {"items": [{"actor_id": str(r.actor_id) if r.actor_id else None, "action": r.action,
                       "target_type": r.target_type, "target_id": r.target_id, "details": r.details,
                       "created_at": r.created_at} for r in rows]}
