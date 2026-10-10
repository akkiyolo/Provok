"""Credit accounting, vote rules, Elo and judge aggregation — the parts that must never break."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backend.app.engine.rules import (
    InsufficientCredits,
    debate_credit_cost,
    decide_charge,
    elo_expected,
    elo_update,
    tally,
    vote_weight,
)
from backend.app.engine.types import Mode, ModelTier
from backend.app.judge.aggregation import (
    CRITERIA,
    JudgeOutputError,
    aggregate,
    parse_run,
)

NOW = datetime(2026, 10, 1, tzinfo=UTC)

# ── Pricing ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("mode,tiers,expected", [
    (Mode.HVH, [], 0),
    (Mode.HVA, [ModelTier.STANDARD], 1),
    (Mode.HVA, [ModelTier.FLAGSHIP], 4),
    (Mode.AVA, [ModelTier.STANDARD, ModelTier.STANDARD], 1),
    (Mode.AVA, [ModelTier.STANDARD, ModelTier.FLAGSHIP], 4),
])
def test_debate_cost(mode, tiers, expected):
    assert debate_credit_cost(mode, tiers, standard_cost=1, flagship_cost=4) == expected


def test_hvh_never_charges():
    c = decide_charge(0, free_used=99, free_allowance=3, balance=0, flagship=False)
    assert c.paid_with == "none" and c.credits_to_debit == 0 and not c.uses_free_debate


def test_free_debates_used_first():
    for used in range(3):
        c = decide_charge(1, free_used=used, free_allowance=3, balance=10, flagship=False)
        assert c.paid_with == "free" and c.credits_to_debit == 0 and c.uses_free_debate


def test_fourth_ai_debate_requires_credits():
    c = decide_charge(1, free_used=3, free_allowance=3, balance=5, flagship=False)
    assert c.paid_with == "credits" and c.credits_to_debit == 1
    with pytest.raises(InsufficientCredits) as e:
        decide_charge(1, free_used=3, free_allowance=3, balance=0, flagship=False)
    assert e.value.cost == 1 and e.value.balance == 0


def test_flagship_not_free_by_default():
    with pytest.raises(InsufficientCredits):
        decide_charge(4, free_used=0, free_allowance=3, balance=3, flagship=True)
    c = decide_charge(4, free_used=0, free_allowance=3, balance=4, flagship=True)
    assert c.paid_with == "credits" and c.credits_to_debit == 4
    c2 = decide_charge(4, free_used=0, free_allowance=3, balance=0, flagship=True, free_covers_flagship=True)
    assert c2.paid_with == "free"


def test_exact_balance_is_enough():
    assert decide_charge(4, free_used=3, free_allowance=3, balance=4, flagship=True).credits_to_debit == 4


# ── Votes ──────────────────────────────────────────────────────────────────


def test_new_accounts_get_half_weight():
    assert vote_weight(NOW - timedelta(days=2), NOW, new_account_days=7, new_account_weight=0.5) == Decimal("0.50")
    assert vote_weight(NOW - timedelta(days=7), NOW, new_account_days=7, new_account_weight=0.5) == Decimal("1.00")


def test_tally_weights_and_counts():
    t = tally([("for", Decimal("1")), ("for", Decimal("0.5")), ("against", Decimal("1")), ("bogus", 1)])
    assert t.for_weight == 1.5 and t.against_weight == 1.0
    assert t.for_count == 2 and t.against_count == 1
    assert t.for_share == pytest.approx(0.6)


def test_empty_tally_is_even():
    assert tally([]).for_share == 0.5


# ── Elo ────────────────────────────────────────────────────────────────────


def test_elo_symmetry_and_conservation():
    a, b = elo_update(1200, 1200, 1.0, 32)
    assert (a, b) == (1216, 1184)
    a2, b2 = elo_update(1200, 1200, 0.5, 32)
    assert (a2, b2) == (1200, 1200)
    a3, b3 = elo_update(1400, 1200, 0.0, 32)
    assert a3 + b3 == 2600 and a3 < 1400


def test_elo_expected_bounds():
    assert elo_expected(1200, 1200) == 0.5
    assert 0.9 < elo_expected(1600, 1200) < 1


# ── Judge aggregation ──────────────────────────────────────────────────────

ROUNDS = ["opening", "rebuttal", "cross_exam", "closing"]


def raw_run(a_score: float, b_score: float, winner: str | None = None) -> dict:
    def side(score):
        return {r: {c: {"score": score, "why": "x"} for c in CRITERIA} for r in ROUNDS}
    return {"scores": {"A": side(a_score), "B": side(b_score)}, "winner": winner, "explanation": "e",
            "decisive_claims": ["C3", 5, "junk"]}


AB = {"A": "for", "B": "against"}
BA = {"A": "against", "B": "for"}


def test_swap_test_consistent_runs_give_clear_winner():
    r1 = parse_run(raw_run(8, 5, "A"), AB, ROUNDS)  # for strong
    r2 = parse_run(raw_run(5, 8, "B"), BA, ROUNDS)  # labels swapped; for still strong
    v = aggregate([r1, r2], close_margin=0.5)
    assert v.winner == "for" and not v.is_close and v.runs_agree
    assert v.totals == {"for": 8.0, "against": 5.0}
    assert r1.decisive_claims == [3, 5]


def test_swap_test_position_bias_marks_close():
    # Judge always prefers label A, regardless of content → runs disagree after mapping.
    r1 = parse_run(raw_run(8, 6, "A"), AB, ROUNDS)
    r2 = parse_run(raw_run(8, 6, "A"), BA, ROUNDS)
    v = aggregate([r1, r2], close_margin=0.5)
    assert not v.runs_agree and v.is_close


def test_small_margin_is_close():
    r1 = parse_run(raw_run(7.2, 7.0), AB, ROUNDS)
    r2 = parse_run(raw_run(7.0, 7.2), BA, ROUNDS)
    v = aggregate([r1, r2], close_margin=0.5)
    assert v.winner == "for" and v.is_close and v.margin == pytest.approx(0.2)


def test_exact_tie_is_draw():
    r1 = parse_run(raw_run(7, 7), AB, ROUNDS)
    v = aggregate([r1], close_margin=0.5)
    assert v.winner is None and v.is_close


def test_concession_overrides_scores():
    r1 = parse_run(raw_run(9, 3), AB, ROUNDS)
    v = aggregate([r1], close_margin=0.5, conceded_position="for")
    assert v.winner == "against" and not v.is_close


def test_scores_clamped_and_partial_rounds():
    raw = raw_run(15, -2)
    raw["scores"]["A"] = {r: v for r, v in raw["scores"]["A"].items() if r in ("opening", "rebuttal")}
    raw["scores"]["B"] = {r: v for r, v in raw["scores"]["B"].items() if r in ("opening", "rebuttal")}
    r = parse_run(raw, AB, ["opening", "rebuttal"])
    v = aggregate([r], close_margin=0.5)
    assert v.totals == {"for": 10.0, "against": 1.0}
    assert set(v.per_round) == {"opening", "rebuttal"}


@pytest.mark.parametrize("bad", [
    {"scores": {}},
    {"scores": {"A": {}, "B": {}}},
    {**raw_run(5, 5), "winner": "C"},
    {"scores": {"A": {r: {c: {"score": "high"} for c in CRITERIA} for r in ROUNDS},
                "B": {r: {c: {"score": 5} for c in CRITERIA} for r in ROUNDS}}},
])
def test_malformed_judge_output_rejected(bad):
    with pytest.raises(JudgeOutputError):
        parse_run(bad, AB, ROUNDS)


def test_relabel_maps_blinded_labels():
    from backend.app.judge.judge import relabel
    m = {"A": "for", "B": "against"}
    assert relabel("Side B wins. B consistently refuted A's claims.", m) == \
        "AGAINST wins. AGAINST consistently refuted FOR's claims."
    assert relabel("A strong case by Side A, but B was sharper than A.", m) == \
        "A strong case by FOR, but AGAINST was sharper than FOR."


def test_production_refuses_unsafe_config():
    from backend.app.core.config import Settings
    safe = dict(app_env="production", debug=False, jwt_secret_key="x" * 48, cookie_secure=True,
                cors_origins="https://provok.app", email_provider="resend", _env_file=None)
    Settings(**safe)
    for bad in ({"llm_fake": True}, {"debug": True}, {"jwt_secret_key": "short"}, {"cookie_secure": False},
                {"cors_origins": "*"}, {"email_provider": "console"}):
        with pytest.raises(ValueError):
            Settings(**{**safe, **bad})
