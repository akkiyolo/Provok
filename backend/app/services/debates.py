"""Debate creation and joining logic (shared by API routes)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.core.errors import AppError, Forbidden, NotFound, PaymentRequired
from backend.app.core.ratelimit import enforce
from backend.app.core.security import utcnow
from backend.app.engine import transitions as tx
from backend.app.engine.config import engine_config
from backend.app.engine.rules import InsufficientCredits, debate_credit_cost, decide_charge
from backend.app.engine.service import Outcome, apply_initial
from backend.app.engine.types import Mode, ModelTier, ParticipantType, Persona, Position, Timing
from backend.app.llm.registry import ModelInfo, get_model
from backend.app.models import AnalyticsEvent, Debate, Side, User
from backend.app.moderation.content import check_topic
from backend.app.payments.credits import charge_for_debate
from backend.app.services import flags
from backend.app.services.notify import notify
from backend.app.video.livekit import minutes_used_this_month


class SideSpec(BaseModel):
    type: Literal["me", "open", "invite", "swarm"]
    username: str | None = Field(default=None, max_length=40)
    model_key: str | None = Field(default=None, max_length=64)
    persona: Persona | None = None


class CreateDebateIn(BaseModel):
    question: str = Field(min_length=1, max_length=400)
    timing: Timing = Timing.LIVE
    word_limit: int | None = Field(default=None, ge=20, le=2000)
    for_side: SideSpec = Field(alias="for")
    against_side: SideSpec = Field(alias="against")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _shape(self) -> CreateDebateIn:
        types = {self.for_side.type, self.against_side.type}
        kinds = sorted([self.for_side.type, self.against_side.type])
        allowed = {("me", "open"), ("invite", "me"), ("me", "swarm"), ("swarm", "swarm")}
        if tuple(kinds) not in allowed:
            raise ValueError("Pick who argues each side: you vs an open challenge, an invited opponent, or an AI; "
                             "or two AIs against each other.")
        if "me" in types and kinds.count("me") != 1:
            raise ValueError("You can only take one side.")
        for s in (self.for_side, self.against_side):
            if s.type == "swarm" and not s.model_key:
                raise ValueError("Choose a model for each AI side.")
            if s.type == "invite" and not s.username:
                raise ValueError("Choose who to challenge.")
        if self.for_side.type == "swarm" and self.against_side.type == "swarm":
            pf = self.for_side.persona or Persona.DATA_DRIVEN
            pa = self.against_side.persona or Persona.MORAL_FRAMING
            if pf == pa:
                raise ValueError("In AI vs AI, give the two sides different personas.")
        return self

    @property
    def mode(self) -> Mode:
        types = {self.for_side.type, self.against_side.type}
        if types == {"swarm"}:
            return Mode.AVA
        if "swarm" in types:
            return Mode.HVA
        return Mode.HVH


@dataclass
class Created:
    debate: Debate
    outcome: Outcome


async def _resolve_model(key: str) -> ModelInfo:
    m = await get_model(key)
    if m is None or not m.enabled or not m.selectable or m.tier not in (ModelTier.STANDARD, ModelTier.FLAGSHIP):
        raise AppError("That AI model isn't available right now. Pick another.", code="model_unavailable",
                       status_code=422)
    return m


async def charge_ai(db: AsyncSession, user: User, debate: Debate, models: list[ModelInfo]) -> None:
    s = get_settings()
    cost = debate_credit_cost(Mode(debate.mode), [m.tier for m in models], standard_cost=s.standard_credit_cost,
                              flagship_cost=s.flagship_credit_cost)
    try:
        charge = decide_charge(cost, free_used=user.free_ai_debates_used, free_allowance=s.free_ai_debates,
                               balance=user.credits, flagship=any(m.tier is ModelTier.FLAGSHIP for m in models),
                               free_covers_flagship=s.free_debates_cover_flagship)
    except InsufficientCredits as exc:
        raise PaymentRequired(
            f"This debate costs {exc.cost} credit{'s' if exc.cost != 1 else ''}. Top up to continue.",
            code="insufficient_credits", details={"cost": exc.cost, "balance": exc.balance}) from exc
    await charge_for_debate(db, user, debate, charge)


async def create_debate(db: AsyncSession, creator: User, body: CreateDebateIn) -> Created:
    s = get_settings()
    mode = body.mode
    await enforce("debate_create", str(creator.id), s.rl_debate_create_user,
                  "You've started a lot of debates this hour. Give it a little while.")
    if mode is not Mode.HVH:
        if not await flags.is_enabled(flags.AI_DEBATES):
            raise AppError("AI debates are paused for a moment. Human vs human is open!", code="ai_paused",
                           status_code=503)
        await enforce("ai_debates_day", str(creator.id), s.rl_ai_debates_user_day,
                      "You've hit today's AI debate limit. Come back tomorrow.")
    if body.timing is Timing.VIDEO:
        if mode is not Mode.HVH:
            raise AppError("Video debates are human vs human.", code="video_requires_humans", status_code=422)
        if not s.livekit_enabled or not await flags.is_enabled(flags.VIDEO_DEBATES):
            raise AppError("Video debates aren't available right now.", code="video_unavailable", status_code=503)
        cap = s.video_free_minutes_per_month
        if cap is not None and minutes_used_this_month(creator) >= cap:
            raise PaymentRequired(f"You've used this month's {cap} free video minutes.", code="video_cap")

    question = " ".join(body.question.split())
    topic = await check_topic(question)
    if not topic.ok:
        raise AppError(topic.reason or "Try a different question.", code=topic.code or "topic_rejected",
                       status_code=422, details={"category": topic.category, "suggestion": topic.suggestion})

    word_limit = body.word_limit or s.default_word_limit
    if not s.min_word_limit <= word_limit <= s.max_word_limit:
        raise AppError(f"Word limit must be between {s.min_word_limit} and {s.max_word_limit}.",
                       code="bad_word_limit", status_code=422)

    # Lock the creator row: credit checks and debits must be serialised per user.
    creator = await db.scalar(select(User).where(User.id == creator.id).with_for_update(key_share=True))
    assert creator is not None

    debate = Debate(question=question, topic_category=topic.category, mode=mode.value, timing=body.timing.value,
                    status="waiting_for_opponent", created_by=creator.id, word_limit=word_limit)
    db.add(debate)
    await db.flush()

    models: list[ModelInfo] = []
    side_states: dict[Position, tx.SideState] = {}
    invited_user: User | None = None
    for pos, spec in ((Position.FOR, body.for_side), (Position.AGAINST, body.against_side)):
        side = Side(debate_id=debate.id, position=pos.value)
        if spec.type == "me":
            side.participant_type, side.user_id = ParticipantType.HUMAN.value, creator.id
        elif spec.type == "swarm":
            m = await _resolve_model(spec.model_key or "")
            models.append(m)
            default_persona = Persona.DATA_DRIVEN if pos is Position.FOR else Persona.MORAL_FRAMING
            side.participant_type = ParticipantType.SWARM.value
            side.swarm_config = {"model_key": m.key, "persona": (spec.persona or default_persona).value}
        elif spec.type == "invite":
            invited_user = await db.scalar(select(User).where(func.lower(User.username) == (spec.username or "").lower(),
                                                              User.status == "active"))
            if invited_user is None:
                raise NotFound("We couldn't find that user.", code="invitee_not_found")
            if invited_user.id == creator.id:
                raise AppError("You can't challenge yourself.", code="self_invite", status_code=422)
            side.invited_user_id = invited_user.id
        db.add(side)
        side_states[pos] = tx.SideState(
            position=pos, participant_type=ParticipantType(side.participant_type) if side.participant_type else None,
            user_id=side.user_id, invited_user_id=side.invited_user_id)
    await db.flush()
    await db.refresh(debate, ["sides"])

    if mode is not Mode.HVH:
        await charge_ai(db, creator, debate, models)

    try:
        initial = tx.initial_transition(mode=mode, timing=body.timing, created_by=creator.id, sides=side_states,
                                        word_limit=word_limit, config=engine_config(body.timing), now=utcnow())
    except tx.InvalidTransition as exc:
        raise AppError(exc.message, code=exc.code, status_code=422) from exc
    outcome = await apply_initial(db, debate, initial)
    db.add(AnalyticsEvent(name="debate_created", user_id=creator.id, debate_id=debate.id,
                          props={"mode": mode.value, "timing": body.timing.value, "paid_with": debate.paid_with}))
    if invited_user is not None:
        await notify(db, outcome.outbox, invited_user.id, "challenge",
                     f"{creator.display_name} challenged you to a debate", body=question[:200],
                     link=f"/d/{debate.id}")
    return Created(debate, outcome)


async def fallback_swarm_config(model_key: str | None, persona: Persona | None) -> tuple[ModelInfo, dict]:
    s = get_settings()
    m = await _resolve_model(model_key or s.default_swarm_model_key)
    return m, {"model_key": m.key, "persona": (persona or Persona.DATA_DRIVEN).value}


async def assert_can_join(db: AsyncSession, debate: Debate, user: User) -> None:
    if debate.created_by == user.id:
        raise Forbidden("You can't take the other side of your own debate.", code="own_debate")
    if debate.timing == Timing.VIDEO.value:
        cap = get_settings().video_free_minutes_per_month
        if cap is not None and minutes_used_this_month(user) >= cap:
            raise PaymentRequired(f"You've used this month's {cap} free video minutes.", code="video_cap")
