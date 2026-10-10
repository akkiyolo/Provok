"""Exhaustive tests for the pure debate state machine."""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.app.engine.transitions import (
    TURN_PLAN,
    AssignHuman,
    AssignSwarm,
    Cancelled,
    CloseRoundVote,
    Conceded,
    DeadlineExpired,
    DebateState,
    EndRound,
    EngineConfig,
    EnqueueJudge,
    EnqueueSwarmTurn,
    FallbackAccepted,
    FlagForReview,
    InvalidTransition,
    JudgingDone,
    JudgingFailed,
    MarkCompleted,
    MarkReady,
    MarkStarted,
    NotifyCreator,
    NotifyTurn,
    OpenRoundVote,
    OpponentJoined,
    Ready,
    RecordTurn,
    RefundIfCharged,
    Resumed,
    ScheduleDeadline,
    SideState,
    StaleEvent,
    StartRound,
    SwarmFailed,
    SyncVideo,
    TurnSubmitted,
    initial_transition,
    transition,
)
from backend.app.engine.types import Mode, ParticipantType, Position, Round, Status, Timing, TurnKind

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
CREATOR = uuid.uuid4()
OPPONENT = uuid.uuid4()
STRANGER = uuid.uuid4()

CFG_LIVE = EngineConfig(
    human_turn_seconds=120, swarm_turn_timeout_seconds=240, challenge_timeout_seconds=900,
    fallback_offer_timeout_seconds=3600, lobby_timeout_seconds=600, judge_timeout_seconds=900,
    round_vote_window_seconds=30, final_vote_window_seconds=90, requires_ready_check=False,
)
CFG_ASYNC = replace(CFG_LIVE, human_turn_seconds=86400, round_vote_window_seconds=None, final_vote_window_seconds=21600)
CFG_VIDEO = replace(CFG_LIVE, human_turn_seconds=90, requires_ready_check=True)

FULL_ORDER = [(r, i, *TURN_PLAN[r][i]) for r in Round for i in range(len(TURN_PLAN[r]))]


def human(p: Position, uid: uuid.UUID | None) -> SideState:
    return SideState(p, ParticipantType.HUMAN, uid)


def swarm(p: Position) -> SideState:
    return SideState(p, ParticipantType.SWARM)


def open_slot(p: Position, invited: uuid.UUID | None = None) -> SideState:
    return SideState(p, None, invited_user_id=invited)


def new_hvh(timing: Timing = Timing.LIVE, cfg: EngineConfig = CFG_LIVE, invited: uuid.UUID | None = None):
    return initial_transition(
        mode=Mode.HVH, timing=timing, created_by=CREATOR,
        sides={Position.FOR: human(Position.FOR, CREATOR), Position.AGAINST: open_slot(Position.AGAINST, invited)},
        word_limit=200, config=cfg, now=T0,
    )


def started_hvh(cfg: EngineConfig = CFG_LIVE, timing: Timing = Timing.LIVE) -> DebateState:
    t = transition(new_hvh(timing, cfg).state, OpponentJoined(OPPONENT, T0), cfg)
    return t.state


def started_hva(human_pos: Position = Position.FOR, cfg: EngineConfig = CFG_LIVE):
    sides = {human_pos: human(human_pos, CREATOR), human_pos.other: swarm(human_pos.other)}
    return initial_transition(mode=Mode.HVA, timing=Timing.LIVE, created_by=CREATOR, sides=sides, word_limit=200,
                              config=cfg, now=T0)


def started_ava(cfg: EngineConfig = CFG_LIVE):
    sides = {Position.FOR: swarm(Position.FOR), Position.AGAINST: swarm(Position.AGAINST)}
    return initial_transition(mode=Mode.AVA, timing=Timing.LIVE, created_by=CREATOR, sides=sides, word_limit=200,
                              config=cfg, now=T0)


def submit(state: DebateState, cfg: EngineConfig = CFG_LIVE, now: datetime = T0, words: int = 50):
    pos, kind = state.expected  # type: ignore[misc]
    return transition(state, TurnSubmitted(pos, kind, words, now, is_swarm=state.side(pos).is_swarm), cfg)


def effects_of(t, typ):
    return [e for e in t.effects if isinstance(e, typ)]


# ── Creation ───────────────────────────────────────────────────────────────


def test_hvh_open_challenge_waits_with_deadline():
    t = new_hvh()
    assert t.state.status is Status.WAITING_FOR_OPPONENT
    assert t.state.deadline_at == T0 + timedelta(seconds=900)
    assert effects_of(t, ScheduleDeadline) == [ScheduleDeadline(T0 + timedelta(seconds=900))]


def test_hva_starts_immediately_and_human_for_goes_first():
    t = started_hva(Position.FOR)
    assert t.state.status is Status.OPENING
    assert t.state.current_round is Round.OPENING and t.state.turn_index == 0
    assert MarkStarted() in t.effects and StartRound(Round.OPENING) in t.effects
    assert effects_of(t, NotifyTurn) == [NotifyTurn(Position.FOR)]
    assert not effects_of(t, EnqueueSwarmTurn)


def test_hva_swarm_for_is_enqueued_immediately():
    t = started_hva(Position.AGAINST)
    assert effects_of(t, EnqueueSwarmTurn) == [EnqueueSwarmTurn(Position.FOR, Round.OPENING, 0, TurnKind.ARGUMENT, 0)]
    assert t.state.deadline_at == T0 + timedelta(seconds=CFG_LIVE.swarm_turn_timeout_seconds)


def test_ava_starts_and_enqueues_swarm():
    t = started_ava()
    assert t.state.status is Status.OPENING
    assert len(effects_of(t, EnqueueSwarmTurn)) == 1


@pytest.mark.parametrize("mode,sides", [
    (Mode.HVH, {Position.FOR: open_slot(Position.FOR), Position.AGAINST: open_slot(Position.AGAINST)}),
    (Mode.HVA, {Position.FOR: human(Position.FOR, CREATOR), Position.AGAINST: human(Position.AGAINST, OPPONENT)}),
    (Mode.HVA, {Position.FOR: human(Position.FOR, CREATOR), Position.AGAINST: open_slot(Position.AGAINST)}),
    (Mode.AVA, {Position.FOR: swarm(Position.FOR), Position.AGAINST: human(Position.AGAINST, CREATOR)}),
])
def test_invalid_side_configurations_rejected(mode, sides):
    with pytest.raises(InvalidTransition):
        initial_transition(mode=mode, timing=Timing.LIVE, created_by=CREATOR, sides=sides, word_limit=200,
                           config=CFG_LIVE, now=T0)


def test_video_requires_hvh():
    sides = {Position.FOR: human(Position.FOR, CREATOR), Position.AGAINST: swarm(Position.AGAINST)}
    with pytest.raises(InvalidTransition) as e:
        initial_transition(mode=Mode.HVA, timing=Timing.VIDEO, created_by=CREATOR, sides=sides, word_limit=200,
                           config=CFG_VIDEO, now=T0)
    assert e.value.code == "video_requires_humans"


# ── Joining / fallback ─────────────────────────────────────────────────────


def test_opponent_join_starts_debate():
    t = transition(new_hvh().state, OpponentJoined(OPPONENT, T0), CFG_LIVE)
    assert t.state.status is Status.OPENING
    assert AssignHuman(Position.AGAINST, OPPONENT) in t.effects
    assert t.state.side(Position.AGAINST).user_id == OPPONENT


def test_creator_cannot_join_own_debate():
    with pytest.raises(InvalidTransition) as e:
        transition(new_hvh().state, OpponentJoined(CREATOR, T0), CFG_LIVE)
    assert e.value.code == "already_seated"


def test_invite_only_challenge():
    state = new_hvh(invited=OPPONENT).state
    with pytest.raises(InvalidTransition) as e:
        transition(state, OpponentJoined(STRANGER, T0), CFG_LIVE)
    assert e.value.code == "invite_only"
    assert transition(state, OpponentJoined(OPPONENT, T0), CFG_LIVE).state.status is Status.OPENING


def test_join_after_start_rejected():
    with pytest.raises(InvalidTransition):
        transition(started_hvh(), OpponentJoined(STRANGER, T0), CFG_LIVE)


def test_challenge_timeout_offers_fallback_then_abandons():
    s = new_hvh().state
    t1 = transition(s, DeadlineExpired(s.deadline_at), CFG_LIVE)  # type: ignore[arg-type]
    assert t1.state.status is Status.SWARM_FALLBACK_OFFERED
    assert NotifyCreator("fallback_offered") in t1.effects
    t2 = transition(t1.state, DeadlineExpired(t1.state.deadline_at), CFG_LIVE)  # type: ignore[arg-type]
    assert t2.state.status is Status.ABANDONED
    assert effects_of(t2, RefundIfCharged)


def test_human_can_still_join_after_fallback_offered():
    s = new_hvh().state
    offered = transition(s, DeadlineExpired(s.deadline_at), CFG_LIVE).state  # type: ignore[arg-type]
    assert transition(offered, OpponentJoined(OPPONENT, T0), CFG_LIVE).state.status is Status.OPENING


def test_fallback_accept_converts_to_hva():
    s = new_hvh().state
    offered = transition(s, DeadlineExpired(s.deadline_at), CFG_LIVE).state  # type: ignore[arg-type]
    t = transition(offered, FallbackAccepted(CREATOR, T0), CFG_LIVE)
    assert t.state.mode is Mode.HVA
    assert t.state.side(Position.AGAINST).is_swarm
    assert AssignSwarm(Position.AGAINST) in t.effects
    assert t.state.status is Status.OPENING


def test_fallback_only_by_creator():
    with pytest.raises(InvalidTransition) as e:
        transition(new_hvh().state, FallbackAccepted(STRANGER, T0), CFG_LIVE)
    assert e.value.code == "not_creator"


def test_video_fallback_becomes_live_text():
    t0 = new_hvh(Timing.VIDEO, CFG_VIDEO)
    t = transition(t0.state, FallbackAccepted(CREATOR, T0), CFG_VIDEO)
    assert t.state.timing is Timing.LIVE and t.state.status is Status.OPENING


# ── Video lobby ────────────────────────────────────────────────────────────


def test_video_lobby_ready_check():
    t = transition(new_hvh(Timing.VIDEO, CFG_VIDEO).state, OpponentJoined(OPPONENT, T0), CFG_VIDEO)
    assert t.state.status is Status.LOBBY
    t2 = transition(t.state, Ready(CREATOR, T0), CFG_VIDEO)
    assert t2.state.status is Status.LOBBY and MarkReady(Position.FOR) in t2.effects
    t3 = transition(t2.state, Ready(OPPONENT, T0), CFG_VIDEO)
    assert t3.state.status is Status.OPENING
    assert SyncVideo(frozenset({Position.FOR})) in t3.effects
    assert t3.state.deadline_at == T0 + timedelta(seconds=90)


def test_lobby_timeout_abandons():
    lobby = transition(new_hvh(Timing.VIDEO, CFG_VIDEO).state, OpponentJoined(OPPONENT, T0), CFG_VIDEO).state
    t = transition(lobby, DeadlineExpired(lobby.deadline_at), CFG_VIDEO)  # type: ignore[arg-type]
    assert t.state.status is Status.ABANDONED


def test_ready_by_stranger_rejected():
    lobby = transition(new_hvh(Timing.VIDEO, CFG_VIDEO).state, OpponentJoined(OPPONENT, T0), CFG_VIDEO).state
    with pytest.raises(InvalidTransition):
        transition(lobby, Ready(STRANGER, T0), CFG_VIDEO)


def test_video_cross_exam_unmutes_both():
    s = transition(new_hvh(Timing.VIDEO, CFG_VIDEO).state, OpponentJoined(OPPONENT, T0), CFG_VIDEO).state
    s = transition(s, Ready(CREATOR, T0), CFG_VIDEO).state
    s = transition(s, Ready(OPPONENT, T0), CFG_VIDEO).state
    t = None
    for _ in range(4):  # opening x2, rebuttal x2 -> cross-exam begins
        t = submit(s, CFG_VIDEO)
        s = t.state
    assert t is not None and s.current_round is Round.CROSS_EXAM
    assert SyncVideo(frozenset(Position)) in t.effects


# ── Turn order (full debate) ───────────────────────────────────────────────


def test_full_hvh_debate_follows_exact_turn_order_live():
    s = started_hvh()
    seen = []
    for r, i, pos, kind in FULL_ORDER:
        assert s.current_round is r and s.turn_index == i
        assert s.expected == (pos, kind)
        t = submit(s)
        seen.append(effects_of(t, RecordTurn)[0])
        s = t.state
    assert s.status is Status.JUDGING
    assert [(e.round, e.turn_index, e.position, e.kind) for e in seen] == [tuple(x) for x in FULL_ORDER]


def test_cross_exam_order():
    assert TURN_PLAN[Round.CROSS_EXAM] == (
        (Position.FOR, TurnKind.QUESTION), (Position.AGAINST, TurnKind.ANSWER),
        (Position.AGAINST, TurnKind.QUESTION), (Position.FOR, TurnKind.ANSWER),
    )


def test_round_end_live_opens_timed_vote():
    s = started_hvh()
    s = submit(s).state
    t = submit(s)
    assert EndRound(Round.OPENING) in t.effects
    assert OpenRoundVote(Round.OPENING, T0 + timedelta(seconds=30)) in t.effects
    assert StartRound(Round.REBUTTAL) in t.effects
    assert not effects_of(t, CloseRoundVote)
    assert t.state.status is Status.REBUTTAL


def test_round_end_async_vote_stays_open_until_next_round_ends():
    s = started_hvh(CFG_ASYNC, Timing.ASYNC)
    s = submit(s, CFG_ASYNC).state
    t = submit(s, CFG_ASYNC)
    assert OpenRoundVote(Round.OPENING, None) in t.effects
    s = submit(t.state, CFG_ASYNC).state
    t2 = submit(s, CFG_ASYNC)
    assert OpenRoundVote(Round.REBUTTAL, None) in t2.effects
    assert CloseRoundVote(Round.OPENING) in t2.effects


def test_closing_round_hands_to_judge_with_final_vote():
    s = started_hvh()
    t = None
    for _ in FULL_ORDER:
        t = submit(s)
        s = t.state
    assert t is not None
    assert s.status is Status.JUDGING
    assert EnqueueJudge(0) in t.effects
    assert OpenRoundVote(Round.CLOSING, T0 + timedelta(seconds=90)) in t.effects


def test_judging_done_completes():
    s = started_hvh()
    for _ in FULL_ORDER:
        s = submit(s).state
    t = transition(s, JudgingDone(T0), CFG_LIVE)
    assert t.state.status is Status.COMPLETED and MarkCompleted() in t.effects
    with pytest.raises(InvalidTransition):
        transition(t.state, JudgingDone(T0), CFG_LIVE)


# ── Turn validation ────────────────────────────────────────────────────────


def test_out_of_turn_rejected():
    s = started_hvh()
    with pytest.raises(InvalidTransition) as e:
        transition(s, TurnSubmitted(Position.AGAINST, TurnKind.ARGUMENT, 10, T0), CFG_LIVE)
    assert e.value.code == "not_your_turn"


def test_wrong_kind_rejected():
    s = started_hvh()
    with pytest.raises(InvalidTransition) as e:
        transition(s, TurnSubmitted(Position.FOR, TurnKind.QUESTION, 10, T0), CFG_LIVE)
    assert e.value.code == "wrong_turn_kind"


def test_over_word_limit_rejected():
    s = started_hvh()
    with pytest.raises(InvalidTransition) as e:
        transition(s, TurnSubmitted(Position.FOR, TurnKind.ARGUMENT, 201, T0), CFG_LIVE)
    assert e.value.code == "over_word_limit"
    assert transition(s, TurnSubmitted(Position.FOR, TurnKind.ARGUMENT, 200, T0), CFG_LIVE).state.turn_index == 1


def test_empty_turn_rejected():
    with pytest.raises(InvalidTransition):
        transition(started_hvh(), TurnSubmitted(Position.FOR, TurnKind.ARGUMENT, 0, T0), CFG_LIVE)


def test_human_cannot_submit_for_swarm_side():
    s = started_hva(Position.AGAINST).state
    with pytest.raises(InvalidTransition) as e:
        transition(s, TurnSubmitted(Position.FOR, TurnKind.ARGUMENT, 10, T0, is_swarm=False), CFG_LIVE)
    assert e.value.code == "wrong_participant"


def test_turn_before_start_rejected():
    with pytest.raises(InvalidTransition) as e:
        transition(new_hvh().state, TurnSubmitted(Position.FOR, TurnKind.ARGUMENT, 10, T0), CFG_LIVE)
    assert e.value.code == "no_turn_open"


def test_terminal_states_reject_everything():
    s = transition(new_hvh().state, Cancelled(CREATOR, T0), CFG_LIVE).state
    for ev in [OpponentJoined(OPPONENT, T0), DeadlineExpired(T0), Resumed(T0), JudgingDone(T0)]:
        with pytest.raises(InvalidTransition) as e:
            transition(s, ev, CFG_LIVE)
        assert e.value.code == "debate_over"


# ── Deadlines ──────────────────────────────────────────────────────────────


def test_human_deadline_records_forfeit_and_continues():
    s = started_hvh()
    t = transition(s, DeadlineExpired(s.deadline_at), CFG_LIVE)  # type: ignore[arg-type]
    rec = effects_of(t, RecordTurn)[0]
    assert rec.forfeit and rec.position is Position.FOR
    assert t.state.turn_index == 1 and t.state.status is Status.OPENING


def test_deadline_before_due_is_stale():
    s = started_hvh()
    with pytest.raises(StaleEvent):
        transition(s, DeadlineExpired(T0 + timedelta(seconds=5)), CFG_LIVE)


def test_deadline_for_superseded_timer_is_stale():
    s = started_hvh()
    old_deadline = s.deadline_at
    s2 = submit(s, now=T0 + timedelta(seconds=10)).state
    with pytest.raises(StaleEvent):
        transition(s2, DeadlineExpired(T0 + timedelta(hours=1), expected_deadline_at=old_deadline), CFG_LIVE)


def test_swarm_deadline_retries_once_then_pauses():
    s = started_ava().state
    t1 = transition(s, DeadlineExpired(s.deadline_at), CFG_LIVE)  # type: ignore[arg-type]
    assert t1.state.status is Status.OPENING and t1.state.swarm_retry_count == 1
    assert effects_of(t1, EnqueueSwarmTurn)[0].attempt == 1
    t2 = transition(t1.state, DeadlineExpired(t1.state.deadline_at), CFG_LIVE)  # type: ignore[arg-type]
    assert t2.state.status is Status.PAUSED and t2.state.paused_from is Status.OPENING
    assert effects_of(t2, FlagForReview)


def test_swarm_failed_event_and_resume():
    s = started_ava().state
    s1 = transition(s, SwarmFailed(Position.FOR, Round.OPENING, 0, T0), CFG_LIVE).state
    s2 = transition(s1, SwarmFailed(Position.FOR, Round.OPENING, 0, T0), CFG_LIVE).state
    assert s2.status is Status.PAUSED
    with pytest.raises(InvalidTransition) as e:
        transition(s2, TurnSubmitted(Position.FOR, TurnKind.ARGUMENT, 10, T0, is_swarm=True), CFG_LIVE)
    assert e.value.code == "no_turn_open"
    t = transition(s2, Resumed(T0), CFG_LIVE)
    assert t.state.status is Status.OPENING and t.state.swarm_retry_count == 0
    assert effects_of(t, EnqueueSwarmTurn)


def test_stale_swarm_failure_ignored():
    s = started_ava().state
    s = submit(s).state  # FOR done, now AGAINST
    with pytest.raises(StaleEvent):
        transition(s, SwarmFailed(Position.FOR, Round.OPENING, 0, T0), CFG_LIVE)


def test_swarm_success_resets_retry_count():
    s = started_ava().state
    s = transition(s, DeadlineExpired(s.deadline_at), CFG_LIVE).state  # type: ignore[arg-type]
    assert s.swarm_retry_count == 1
    s = submit(s).state
    assert s.swarm_retry_count == 0


def test_judge_timeout_retries_then_pauses_then_resumes():
    s = started_ava().state
    for _ in FULL_ORDER:
        s = submit(s).state
    t1 = transition(s, DeadlineExpired(s.deadline_at), CFG_LIVE)  # type: ignore[arg-type]
    assert EnqueueJudge(1) in t1.effects and t1.state.status is Status.JUDGING
    t2 = transition(t1.state, JudgingFailed(T0), CFG_LIVE)
    assert t2.state.status is Status.PAUSED and t2.state.paused_from is Status.JUDGING
    t3 = transition(t2.state, Resumed(T0), CFG_LIVE)
    assert t3.state.status is Status.JUDGING and EnqueueJudge(0) in t3.effects


# ── Concede / cancel ───────────────────────────────────────────────────────


def test_concede_goes_to_judging():
    s = started_hvh()
    t = transition(s, Conceded(OPPONENT, T0), CFG_LIVE)
    assert t.state.status is Status.JUDGING and t.state.conceded_position is Position.AGAINST
    assert EnqueueJudge(0) in t.effects


def test_spectator_cannot_concede():
    with pytest.raises(InvalidTransition):
        transition(started_hvh(), Conceded(STRANGER, T0), CFG_LIVE)


def test_creator_can_cancel_before_start_only():
    t = transition(new_hvh().state, Cancelled(CREATOR, T0), CFG_LIVE)
    assert t.state.status is Status.CANCELLED and effects_of(t, RefundIfCharged)
    with pytest.raises(InvalidTransition) as e:
        transition(started_hvh(), Cancelled(CREATOR, T0), CFG_LIVE)
    assert e.value.code == "already_started"


def test_stranger_cannot_cancel_but_admin_can():
    with pytest.raises(InvalidTransition):
        transition(new_hvh().state, Cancelled(STRANGER, T0), CFG_LIVE)
    assert transition(started_hvh(), Cancelled(None, T0, is_admin=True), CFG_LIVE).state.status is Status.CANCELLED


def test_resume_requires_paused():
    with pytest.raises(InvalidTransition):
        transition(started_hvh(), Resumed(T0), CFG_LIVE)
