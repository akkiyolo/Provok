"""
The debate state machine — a pure function.

    transition(state, event, config) -> Transition(state, effects)

No I/O, no clock reads, no randomness: time arrives inside events. The service
layer (`engine/service.py`) loads state from the DB under a row lock, calls
`transition`, persists the new state and executes the returned effects.

Lifecycle
    WAITING_FOR_OPPONENT ──(deadline)──> SWARM_FALLBACK_OFFERED ──(deadline)──> ABANDONED
            │  opponent_joined / fallback_accepted                │
            ▼                                                     ▼
       [LOBBY (video: ready-check)] ──> OPENING → REBUTTAL → CROSS_EXAM → CLOSING → JUDGING → COMPLETED
    any non-terminal ──> CANCELLED ; swarm/judge failure ──> PAUSED ──(resume)──> previous status
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Union

from backend.app.engine.types import (
    ROUND_ORDER,
    Mode,
    ParticipantType,
    Position,
    Round,
    Status,
    Timing,
    TurnKind,
    status_for_round,
)

# ── Turn order ─────────────────────────────────────────────────────────────

_ARGUMENT_ROUND = ((Position.FOR, TurnKind.ARGUMENT), (Position.AGAINST, TurnKind.ARGUMENT))
TURN_PLAN: dict[Round, tuple[tuple[Position, TurnKind], ...]] = {
    Round.OPENING: _ARGUMENT_ROUND,
    Round.REBUTTAL: _ARGUMENT_ROUND,
    Round.CROSS_EXAM: (
        (Position.FOR, TurnKind.QUESTION),
        (Position.AGAINST, TurnKind.ANSWER),
        (Position.AGAINST, TurnKind.QUESTION),
        (Position.FOR, TurnKind.ANSWER),
    ),
    Round.CLOSING: _ARGUMENT_ROUND,
}


def expected_turn(round_: Round, turn_index: int) -> tuple[Position, TurnKind]:
    return TURN_PLAN[round_][turn_index]


def next_round(round_: Round) -> Round | None:
    i = ROUND_ORDER.index(round_)
    return ROUND_ORDER[i + 1] if i + 1 < len(ROUND_ORDER) else None


def previous_round(round_: Round) -> Round | None:
    i = ROUND_ORDER.index(round_)
    return ROUND_ORDER[i - 1] if i > 0 else None


# ── State ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SideState:
    position: Position
    participant_type: ParticipantType | None  # None = open slot
    user_id: uuid.UUID | None = None
    invited_user_id: uuid.UUID | None = None
    ready: bool = False

    @property
    def is_open(self) -> bool:
        return self.participant_type is None

    @property
    def is_human(self) -> bool:
        return self.participant_type is ParticipantType.HUMAN

    @property
    def is_swarm(self) -> bool:
        return self.participant_type is ParticipantType.SWARM


@dataclass(frozen=True)
class DebateState:
    status: Status
    mode: Mode
    timing: Timing
    created_by: uuid.UUID | None
    sides: dict[Position, SideState]
    word_limit: int
    current_round: Round | None = None
    turn_index: int = 0
    deadline_at: datetime | None = None
    swarm_retry_count: int = 0
    paused_from: Status | None = None
    paused_reason: str | None = None
    conceded_position: Position | None = None

    def side(self, p: Position) -> SideState:
        return self.sides[p]

    def position_of(self, user_id: uuid.UUID) -> Position | None:
        for p, s in self.sides.items():
            if s.user_id == user_id and s.is_human:
                return p
        return None

    @property
    def expected(self) -> tuple[Position, TurnKind] | None:
        if self.status.is_round and self.current_round is not None:
            return expected_turn(self.current_round, self.turn_index)
        return None


@dataclass(frozen=True)
class EngineConfig:
    human_turn_seconds: int
    swarm_turn_timeout_seconds: int
    challenge_timeout_seconds: int
    fallback_offer_timeout_seconds: int
    lobby_timeout_seconds: int
    judge_timeout_seconds: int
    # None = async: a round's vote stays open until the next round ends.
    round_vote_window_seconds: int | None
    final_vote_window_seconds: int
    requires_ready_check: bool
    swarm_max_retries: int = 1
    judge_max_retries: int = 1


# ── Events ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OpponentJoined:
    user_id: uuid.UUID
    now: datetime


@dataclass(frozen=True)
class FallbackAccepted:
    user_id: uuid.UUID
    now: datetime


@dataclass(frozen=True)
class Ready:
    user_id: uuid.UUID
    now: datetime


@dataclass(frozen=True)
class TurnSubmitted:
    position: Position
    kind: TurnKind
    word_count: int
    now: datetime
    is_swarm: bool = False


@dataclass(frozen=True)
class DeadlineExpired:
    now: datetime
    # The deadline the job was scheduled for; a mismatch means the event is stale.
    expected_deadline_at: datetime | None = None


@dataclass(frozen=True)
class SwarmFailed:
    position: Position
    round: Round
    turn_index: int
    now: datetime
    reason: str = "swarm_error"


@dataclass(frozen=True)
class JudgingDone:
    now: datetime


@dataclass(frozen=True)
class JudgingFailed:
    now: datetime
    reason: str = "judge_error"


@dataclass(frozen=True)
class Conceded:
    user_id: uuid.UUID
    now: datetime


@dataclass(frozen=True)
class Cancelled:
    user_id: uuid.UUID | None
    now: datetime
    is_admin: bool = False


@dataclass(frozen=True)
class Resumed:
    now: datetime


Event = Union[
    OpponentJoined, FallbackAccepted, Ready, TurnSubmitted, DeadlineExpired, SwarmFailed, JudgingDone,
    JudgingFailed, Conceded, Cancelled, Resumed,
]

# ── Effects ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AssignHuman:
    position: Position
    user_id: uuid.UUID


@dataclass(frozen=True)
class AssignSwarm:
    position: Position


@dataclass(frozen=True)
class MarkReady:
    position: Position


@dataclass(frozen=True)
class MarkStarted:
    pass


@dataclass(frozen=True)
class RecordTurn:
    position: Position
    round: Round
    turn_index: int
    kind: TurnKind
    forfeit: bool = False


@dataclass(frozen=True)
class StartRound:
    round: Round


@dataclass(frozen=True)
class EndRound:
    round: Round


@dataclass(frozen=True)
class OpenRoundVote:
    round: Round
    closes_at: datetime | None


@dataclass(frozen=True)
class CloseRoundVote:
    round: Round


@dataclass(frozen=True)
class ScheduleDeadline:
    at: datetime


@dataclass(frozen=True)
class EnqueueSwarmTurn:
    position: Position
    round: Round
    turn_index: int
    kind: TurnKind
    attempt: int


@dataclass(frozen=True)
class NotifyTurn:
    position: Position


@dataclass(frozen=True)
class NotifyCreator:
    kind: str


@dataclass(frozen=True)
class EnqueueJudge:
    attempt: int


@dataclass(frozen=True)
class SyncVideo:
    """Who may speak right now (server-controlled muting)."""
    speakers: frozenset[Position]


@dataclass(frozen=True)
class FlagForReview:
    reason: str


@dataclass(frozen=True)
class RefundIfCharged:
    reason: str


@dataclass(frozen=True)
class MarkCompleted:
    pass


Effect = Union[
    AssignHuman, AssignSwarm, MarkReady, MarkStarted, RecordTurn, StartRound, EndRound, OpenRoundVote,
    CloseRoundVote, ScheduleDeadline, EnqueueSwarmTurn, NotifyTurn, NotifyCreator, EnqueueJudge, SyncVideo,
    FlagForReview, RefundIfCharged, MarkCompleted,
]


@dataclass(frozen=True)
class Transition:
    state: DebateState
    effects: tuple[Effect, ...] = field(default_factory=tuple)


class InvalidTransition(Exception):
    """The event is not allowed in the current state. `code` is machine-readable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class StaleEvent(InvalidTransition):
    """A timer fired for a state that has already moved on — safe to ignore."""


# ── Initial state ──────────────────────────────────────────────────────────


def initial_transition(
    *, mode: Mode, timing: Timing, created_by: uuid.UUID | None, sides: dict[Position, SideState],
    word_limit: int, config: EngineConfig, now: datetime,
) -> Transition:
    """State for a freshly created debate (open challenge, lobby, or straight into round 1)."""
    if timing is Timing.VIDEO and mode is not Mode.HVH:
        raise InvalidTransition("video_requires_humans", "Video debates are human vs human.")
    open_sides = [s for s in sides.values() if s.is_open]
    if mode is Mode.HVH:
        if len(open_sides) > 1:
            raise InvalidTransition("bad_sides", "The creator must take one side.")
    elif mode is Mode.HVA:
        if open_sides or sum(s.is_swarm for s in sides.values()) != 1:
            raise InvalidTransition("bad_sides", "Human vs AI needs exactly one human and one swarm.")
    elif mode is Mode.AVA:
        if not all(s.is_swarm for s in sides.values()):
            raise InvalidTransition("bad_sides", "AI vs AI needs two swarms.")

    state = DebateState(status=Status.WAITING_FOR_OPPONENT, mode=mode, timing=timing, created_by=created_by,
                        sides=dict(sides), word_limit=word_limit)
    if open_sides:
        deadline = now + timedelta(seconds=config.challenge_timeout_seconds)
        return Transition(replace(state, deadline_at=deadline), (ScheduleDeadline(deadline),))
    return _after_all_seated(state, config, now, ())


# ── Transition function ────────────────────────────────────────────────────


def transition(state: DebateState, event: Event, config: EngineConfig) -> Transition:
    if state.status.is_terminal:
        raise InvalidTransition("debate_over", "This debate has already ended.")
    handler = _HANDLERS.get(type(event))
    if handler is None:  # pragma: no cover - programming error
        raise InvalidTransition("unknown_event", f"Unknown event {type(event).__name__}")
    return handler(state, event, config)


def _on_opponent_joined(state: DebateState, ev: OpponentJoined, config: EngineConfig) -> Transition:
    if state.status not in (Status.WAITING_FOR_OPPONENT, Status.SWARM_FALLBACK_OFFERED):
        raise InvalidTransition("not_open", "This debate is no longer looking for an opponent.")
    if state.position_of(ev.user_id) is not None:
        raise InvalidTransition("already_seated", "You're already debating in this one.")
    open_pos = _open_position(state)
    slot = state.side(open_pos)
    if slot.invited_user_id is not None and slot.invited_user_id != ev.user_id:
        raise InvalidTransition("invite_only", "This challenge was sent to someone else.")
    sides = dict(state.sides)
    sides[open_pos] = replace(slot, participant_type=ParticipantType.HUMAN, user_id=ev.user_id)
    new = replace(state, sides=sides, deadline_at=None)
    return _after_all_seated(new, config, ev.now, (AssignHuman(open_pos, ev.user_id),))


def _on_fallback_accepted(state: DebateState, ev: FallbackAccepted, config: EngineConfig) -> Transition:
    if state.status not in (Status.WAITING_FOR_OPPONENT, Status.SWARM_FALLBACK_OFFERED):
        raise InvalidTransition("not_open", "This debate already has an opponent.")
    if ev.user_id != state.created_by:
        raise InvalidTransition("not_creator", "Only the creator can bring in an AI opponent.")
    open_pos = _open_position(state)
    sides = dict(state.sides)
    sides[open_pos] = replace(state.side(open_pos), participant_type=ParticipantType.SWARM, user_id=None,
                              invited_user_id=None)
    # Video needs two humans on camera; an AI fallback continues as a live text debate.
    timing = Timing.LIVE if state.timing is Timing.VIDEO else state.timing
    new = replace(state, sides=sides, mode=Mode.HVA, timing=timing, deadline_at=None)
    return _after_all_seated(new, config, ev.now, (AssignSwarm(open_pos),))


def _on_ready(state: DebateState, ev: Ready, config: EngineConfig) -> Transition:
    if state.status is not Status.LOBBY:
        raise InvalidTransition("not_in_lobby", "This debate isn't waiting for a ready check.")
    pos = state.position_of(ev.user_id)
    if pos is None:
        raise InvalidTransition("not_a_debater", "Only debaters can ready up.")
    sides = dict(state.sides)
    sides[pos] = replace(sides[pos], ready=True)
    new = replace(state, sides=sides)
    effects: tuple[Effect, ...] = (MarkReady(pos),)
    if all(s.ready for s in sides.values() if s.is_human):
        return _start_debate(replace(new, deadline_at=None), config, ev.now, effects)
    return Transition(new, effects)


def _on_turn_submitted(state: DebateState, ev: TurnSubmitted, config: EngineConfig) -> Transition:
    expected = state.expected
    if expected is None or state.current_round is None:
        raise InvalidTransition("no_turn_open", "No turn is open right now.")
    exp_pos, exp_kind = expected
    if ev.position is not exp_pos:
        raise InvalidTransition("not_your_turn", "It's not your turn yet.")
    if ev.kind is not exp_kind:
        raise InvalidTransition("wrong_turn_kind", f"This turn must be a {exp_kind.value}.")
    if ev.is_swarm != state.side(ev.position).is_swarm:
        raise InvalidTransition("wrong_participant", "That side is not yours to play.")
    if ev.word_count < 1:
        raise InvalidTransition("empty_turn", "Your turn can't be empty.")
    if ev.word_count > state.word_limit:
        raise InvalidTransition("over_word_limit",
                                f"Your turn is {ev.word_count} words; the limit is {state.word_limit}.")
    record = RecordTurn(ev.position, state.current_round, state.turn_index, ev.kind)
    return _advance(state, config, ev.now, (record,))


def _on_deadline(state: DebateState, ev: DeadlineExpired, config: EngineConfig) -> Transition:
    if state.deadline_at is None:
        raise StaleEvent("no_deadline", "No deadline is pending.")
    if ev.expected_deadline_at is not None and ev.expected_deadline_at != state.deadline_at:
        raise StaleEvent("stale_deadline", "The deadline has moved on.")
    if ev.now < state.deadline_at:
        raise StaleEvent("not_yet", "The deadline has not passed.")

    if state.status is Status.WAITING_FOR_OPPONENT:
        deadline = ev.now + timedelta(seconds=config.fallback_offer_timeout_seconds)
        return Transition(replace(state, status=Status.SWARM_FALLBACK_OFFERED, deadline_at=deadline),
                          (ScheduleDeadline(deadline), NotifyCreator("fallback_offered")))
    if state.status in (Status.SWARM_FALLBACK_OFFERED, Status.LOBBY):
        return Transition(replace(state, status=Status.ABANDONED, deadline_at=None),
                          (RefundIfCharged("abandoned_before_start"),))
    if state.status is Status.JUDGING:
        return _judge_retry_or_pause(state, config, ev.now, "judge_timeout")
    if state.status.is_round and state.current_round is not None:
        pos, kind = expected_turn(state.current_round, state.turn_index)
        if state.side(pos).is_swarm:
            return _swarm_retry_or_pause(state, config, ev.now, "swarm_timeout")
        forfeit = RecordTurn(pos, state.current_round, state.turn_index, kind, forfeit=True)
        return _advance(state, config, ev.now, (forfeit,))
    raise StaleEvent("no_timer_for_status", f"No timer applies in status {state.status.value}.")


def _on_swarm_failed(state: DebateState, ev: SwarmFailed, config: EngineConfig) -> Transition:
    if not (state.status.is_round and state.current_round is ev.round and state.turn_index == ev.turn_index):
        raise StaleEvent("stale_swarm_failure", "The swarm turn is no longer current.")
    exp_pos, _ = expected_turn(ev.round, ev.turn_index)
    if exp_pos is not ev.position or not state.side(ev.position).is_swarm:
        raise StaleEvent("stale_swarm_failure", "The swarm turn is no longer current.")
    return _swarm_retry_or_pause(state, config, ev.now, ev.reason)


def _on_judging_done(state: DebateState, ev: JudgingDone, config: EngineConfig) -> Transition:
    if state.status is not Status.JUDGING:
        raise InvalidTransition("not_judging", "The debate is not being judged.")
    return Transition(replace(state, status=Status.COMPLETED, deadline_at=None, swarm_retry_count=0),
                      (MarkCompleted(),))


def _on_judging_failed(state: DebateState, ev: JudgingFailed, config: EngineConfig) -> Transition:
    if state.status is not Status.JUDGING:
        raise StaleEvent("not_judging", "The debate is not being judged.")
    return _judge_retry_or_pause(state, config, ev.now, ev.reason)


def _on_conceded(state: DebateState, ev: Conceded, config: EngineConfig) -> Transition:
    if not state.status.is_round or state.current_round is None:
        raise InvalidTransition("not_in_progress", "You can only concede while the debate is running.")
    pos = state.position_of(ev.user_id)
    if pos is None:
        raise InvalidTransition("not_a_debater", "Only debaters can concede.")
    new = replace(state, conceded_position=pos)
    return _finish_rounds(new, config, ev.now, ())


def _on_cancelled(state: DebateState, ev: Cancelled, config: EngineConfig) -> Transition:
    pre_start = state.status in (Status.WAITING_FOR_OPPONENT, Status.SWARM_FALLBACK_OFFERED, Status.LOBBY)
    if not ev.is_admin:
        if ev.user_id is None or ev.user_id != state.created_by:
            raise InvalidTransition("not_creator", "Only the creator can cancel this debate.")
        if not pre_start:
            raise InvalidTransition("already_started", "A debate can't be cancelled once it has started. "
                                                       "You can concede instead.")
    return Transition(replace(state, status=Status.CANCELLED, deadline_at=None),
                      (RefundIfCharged("cancelled"),))


def _on_resumed(state: DebateState, ev: Resumed, config: EngineConfig) -> Transition:
    if state.status is not Status.PAUSED or state.paused_from is None:
        raise InvalidTransition("not_paused", "The debate is not paused.")
    restored = replace(state, status=state.paused_from, paused_from=None, paused_reason=None, swarm_retry_count=0)
    if restored.status is Status.JUDGING:
        deadline = ev.now + timedelta(seconds=config.judge_timeout_seconds)
        return Transition(replace(restored, deadline_at=deadline), (EnqueueJudge(attempt=0), ScheduleDeadline(deadline)))
    return _begin_turn(restored, config, ev.now, ())


_HANDLERS = {
    OpponentJoined: _on_opponent_joined,
    FallbackAccepted: _on_fallback_accepted,
    Ready: _on_ready,
    TurnSubmitted: _on_turn_submitted,
    DeadlineExpired: _on_deadline,
    SwarmFailed: _on_swarm_failed,
    JudgingDone: _on_judging_done,
    JudgingFailed: _on_judging_failed,
    Conceded: _on_conceded,
    Cancelled: _on_cancelled,
    Resumed: _on_resumed,
}

# ── Helpers ────────────────────────────────────────────────────────────────


def _open_position(state: DebateState) -> Position:
    for p, s in state.sides.items():
        if s.is_open:
            return p
    raise InvalidTransition("no_open_side", "Both sides are already taken.")


def _after_all_seated(state: DebateState, config: EngineConfig, now: datetime,
                      effects: tuple[Effect, ...]) -> Transition:
    if config.requires_ready_check and state.timing is Timing.VIDEO:
        deadline = now + timedelta(seconds=config.lobby_timeout_seconds)
        return Transition(replace(state, status=Status.LOBBY, deadline_at=deadline),
                          effects + (ScheduleDeadline(deadline),))
    return _start_debate(state, config, now, effects)


def _start_debate(state: DebateState, config: EngineConfig, now: datetime,
                  effects: tuple[Effect, ...]) -> Transition:
    first = ROUND_ORDER[0]
    started = replace(state, status=status_for_round(first), current_round=first, turn_index=0, swarm_retry_count=0)
    return _begin_turn(started, config, now, effects + (MarkStarted(), StartRound(first)))


def _begin_turn(state: DebateState, config: EngineConfig, now: datetime,
                effects: tuple[Effect, ...]) -> Transition:
    assert state.current_round is not None
    pos, kind = expected_turn(state.current_round, state.turn_index)
    side = state.side(pos)
    out: list[Effect] = list(effects)
    if side.is_swarm:
        deadline = now + timedelta(seconds=config.swarm_turn_timeout_seconds)
        out.append(EnqueueSwarmTurn(pos, state.current_round, state.turn_index, kind, state.swarm_retry_count))
    else:
        deadline = now + timedelta(seconds=config.human_turn_seconds)
        out.append(NotifyTurn(pos))
    if state.timing is Timing.VIDEO:
        speakers = frozenset(Position) if state.current_round is Round.CROSS_EXAM else frozenset({pos})
        out.append(SyncVideo(speakers))
    out.append(ScheduleDeadline(deadline))
    return Transition(replace(state, deadline_at=deadline), tuple(out))


def _advance(state: DebateState, config: EngineConfig, now: datetime, effects: tuple[Effect, ...]) -> Transition:
    assert state.current_round is not None
    next_index = state.turn_index + 1
    if next_index < len(TURN_PLAN[state.current_round]):
        return _begin_turn(replace(state, turn_index=next_index, swarm_retry_count=0), config, now, effects)
    return _end_round(state, config, now, effects)


def _end_round(state: DebateState, config: EngineConfig, now: datetime, effects: tuple[Effect, ...]) -> Transition:
    assert state.current_round is not None
    finished = state.current_round
    nxt = next_round(finished)
    if nxt is None:
        return _finish_rounds(state, config, now, effects)
    out: list[Effect] = list(effects) + [EndRound(finished)]
    out += _vote_effects_for_round_end(finished, config, now, final=False)
    advanced = replace(state, status=status_for_round(nxt), current_round=nxt, turn_index=0, swarm_retry_count=0)
    return _begin_turn(advanced, config, now, tuple(out) + (StartRound(nxt),))


def _finish_rounds(state: DebateState, config: EngineConfig, now: datetime,
                   effects: tuple[Effect, ...]) -> Transition:
    """Closing round done (or a concession): open the final vote and hand over to the judge."""
    assert state.current_round is not None
    out: list[Effect] = list(effects) + [EndRound(state.current_round)]
    out += _vote_effects_for_round_end(state.current_round, config, now, final=True)
    deadline = now + timedelta(seconds=config.judge_timeout_seconds)
    out += [EnqueueJudge(attempt=0), ScheduleDeadline(deadline)]
    if state.timing is Timing.VIDEO:
        out.append(SyncVideo(frozenset(Position)))
    return Transition(replace(state, status=Status.JUDGING, deadline_at=deadline, swarm_retry_count=0), tuple(out))


def _vote_effects_for_round_end(finished: Round, config: EngineConfig, now: datetime, *, final: bool) -> list[Effect]:
    out: list[Effect] = []
    if final:
        closes_at: datetime | None = now + timedelta(seconds=config.final_vote_window_seconds)
    elif config.round_vote_window_seconds is not None:
        closes_at = now + timedelta(seconds=config.round_vote_window_seconds)
    else:
        closes_at = None  # async: stays open until the next round ends
    out.append(OpenRoundVote(finished, closes_at))
    prev = previous_round(finished)
    if config.round_vote_window_seconds is None and prev is not None:
        out.append(CloseRoundVote(prev))
    return out


def _swarm_retry_or_pause(state: DebateState, config: EngineConfig, now: datetime, reason: str) -> Transition:
    assert state.current_round is not None
    if state.swarm_retry_count < config.swarm_max_retries:
        return _begin_turn(replace(state, swarm_retry_count=state.swarm_retry_count + 1), config, now, ())
    return Transition(
        replace(state, status=Status.PAUSED, paused_from=state.status, paused_reason=reason, deadline_at=None),
        (FlagForReview(reason),),
    )


def _judge_retry_or_pause(state: DebateState, config: EngineConfig, now: datetime, reason: str) -> Transition:
    if state.swarm_retry_count < config.judge_max_retries:
        attempt = state.swarm_retry_count + 1
        deadline = now + timedelta(seconds=config.judge_timeout_seconds)
        return Transition(replace(state, swarm_retry_count=attempt, deadline_at=deadline),
                          (EnqueueJudge(attempt=attempt), ScheduleDeadline(deadline)))
    return Transition(
        replace(state, status=Status.PAUSED, paused_from=Status.JUDGING, paused_reason=reason, deadline_at=None),
        (FlagForReview(reason),),
    )
