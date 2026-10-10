"""Pure business rules: pricing, vote weighting, Elo. No I/O."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from backend.app.engine.types import Mode, ModelTier

# ── Pricing ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Charge:
    cost: int  # credits the debate is worth
    paid_with: str  # "none" | "free" | "credits"
    credits_to_debit: int
    uses_free_debate: bool


class InsufficientCredits(Exception):
    def __init__(self, cost: int, balance: int) -> None:
        super().__init__(f"Needs {cost} credits, you have {balance}.")
        self.cost = cost
        self.balance = balance


def debate_credit_cost(mode: Mode, swarm_tiers: list[ModelTier | str], *, standard_cost: int,
                       flagship_cost: int) -> int:
    """HvH is free. AI debates cost the flagship price if any side uses a flagship model."""
    if mode is Mode.HVH:
        return 0
    return flagship_cost if any(ModelTier(t) is ModelTier.FLAGSHIP for t in swarm_tiers) else standard_cost


def decide_charge(cost: int, *, free_used: int, free_allowance: int, balance: int, flagship: bool,
                  free_covers_flagship: bool = False) -> Charge:
    """Free AI debates first, then credits. By default free debates cover standard models only."""
    if cost == 0:
        return Charge(0, "none", 0, False)
    if free_used < free_allowance and (free_covers_flagship or not flagship):
        return Charge(cost, "free", 0, True)
    if balance >= cost:
        return Charge(cost, "credits", cost, False)
    raise InsufficientCredits(cost, balance)


# ── Votes ──────────────────────────────────────────────────────────────────


def vote_weight(account_created_at: datetime, now: datetime, *, new_account_days: int,
                new_account_weight: float) -> Decimal:
    if now - account_created_at < timedelta(days=new_account_days):
        return Decimal(str(new_account_weight)).quantize(Decimal("0.01"))
    return Decimal("1.00")


@dataclass(frozen=True)
class Tally:
    for_weight: float
    against_weight: float
    for_count: int
    against_count: int

    @property
    def total_weight(self) -> float:
        return self.for_weight + self.against_weight

    @property
    def for_share(self) -> float:
        """0..1 share of weighted votes for FOR; 0.5 when nobody voted."""
        return 0.5 if self.total_weight == 0 else self.for_weight / self.total_weight

    def as_dict(self) -> dict[str, float | int]:
        return {"for": round(self.for_weight, 2), "against": round(self.against_weight, 2),
                "for_count": self.for_count, "against_count": self.against_count,
                "for_share": round(self.for_share, 4)}


def tally(votes: list[tuple[str, Decimal | float]]) -> Tally:
    """votes: [(position, weight)]"""
    fw = aw = 0.0
    fc = ac = 0
    for position, weight in votes:
        if position == "for":
            fw += float(weight)
            fc += 1
        elif position == "against":
            aw += float(weight)
            ac += 1
    return Tally(fw, aw, fc, ac)


# ── Elo ────────────────────────────────────────────────────────────────────


def elo_expected(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def elo_update(rating_a: int, rating_b: int, score_a: float, k: int) -> tuple[int, int]:
    """score_a: 1 win, 0.5 draw, 0 loss. Returns new (a, b), rounded."""
    exp_a = elo_expected(rating_a, rating_b)
    delta = k * (score_a - exp_a)
    return round(rating_a + delta), round(rating_b - delta)
