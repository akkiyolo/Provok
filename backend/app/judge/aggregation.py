"""
Judge aggregation — pure.

Each judge run sees the debate blinded: sides are labelled A/B and the run records
which real position each label meant. The swap test runs judging twice with labels
(and presentation order) swapped; we map both runs back to FOR/AGAINST, average,
and mark the verdict *close* when the runs disagree or the margin is small.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Any

CRITERIA = ("argument_strength", "evidence_quality", "rebuttal_coverage", "responsiveness", "consistency")
ROUNDS = ("opening", "rebuttal", "cross_exam", "closing")
POSITIONS = ("for", "against")


class JudgeOutputError(ValueError):
    """The judge returned something we can't score."""


@dataclass(frozen=True)
class JudgeRun:
    """One blinded judging pass. scores[label][round][criterion] = (score 1-10, justification)."""
    label_to_position: dict[str, str]  # {"A": "for", "B": "against"}
    scores: dict[str, dict[str, dict[str, dict[str, Any]]]]
    winner_label: str | None
    explanation: str
    decisive_claims: list[int] = field(default_factory=list)

    def position_scores(self) -> dict[str, dict[str, dict[str, float]]]:
        out: dict[str, dict[str, dict[str, float]]] = {}
        for label, rounds in self.scores.items():
            pos = self.label_to_position[label]
            out[pos] = {r: {c: float(v["score"]) for c, v in crit.items()} for r, crit in rounds.items()}
        return out

    @property
    def winner_position(self) -> str | None:
        return self.label_to_position.get(self.winner_label) if self.winner_label else None


@dataclass(frozen=True)
class AggregatedVerdict:
    winner: str | None  # "for" | "against" | None (draw)
    is_close: bool
    totals: dict[str, float]  # overall 1..10 per position
    per_round: dict[str, dict[str, dict[str, float]]]  # round -> position -> criterion -> avg
    margin: float
    runs_agree: bool


def parse_run(raw: dict[str, Any], label_to_position: dict[str, str], rounds_played: list[str]) -> JudgeRun:
    """Validate and normalise judge JSON. Clamps scores to 1..10. Raises JudgeOutputError."""
    try:
        scores_raw = raw["scores"]
        out: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
        for label in label_to_position:
            out[label] = {}
            for r in rounds_played:
                crit_raw = scores_raw[label][r]
                out[label][r] = {}
                for c in CRITERIA:
                    item = crit_raw[c]
                    score = item["score"] if isinstance(item, dict) else item
                    score_f = min(10.0, max(1.0, float(score)))
                    just = item.get("why", "") if isinstance(item, dict) else ""
                    out[label][r][c] = {"score": score_f, "why": str(just)[:300]}
        winner = raw.get("winner")
        if winner not in (*label_to_position.keys(), None, "tie"):
            raise JudgeOutputError(f"Unknown winner label {winner!r}")
        decisive = [int(str(x).lstrip("Cc")) for x in raw.get("decisive_claims", [])
                    if str(x).lstrip("Cc").isdigit()][:5]
        return JudgeRun(label_to_position, out, None if winner in (None, "tie") else winner,
                        str(raw.get("explanation", ""))[:2000], decisive)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, JudgeOutputError):
            raise
        raise JudgeOutputError(f"Malformed judge output: {exc}") from exc


def aggregate(runs: list[JudgeRun], *, close_margin: float, conceded_position: str | None = None) -> AggregatedVerdict:
    if not runs:
        raise JudgeOutputError("No judge runs to aggregate")
    mapped = [r.position_scores() for r in runs]
    rounds = [r for r in ROUNDS if r in mapped[0].get("for", {})]
    per_round: dict[str, dict[str, dict[str, float]]] = {}
    for rnd in rounds:
        per_round[rnd] = {}
        for pos in POSITIONS:
            per_round[rnd][pos] = {c: round(mean(m[pos][rnd][c] for m in mapped), 2) for c in CRITERIA}
    totals = {
        pos: round(mean(mean(per_round[r][pos].values()) for r in rounds), 3) if rounds else 0.0
        for pos in POSITIONS
    }
    margin = round(abs(totals["for"] - totals["against"]), 3)
    run_winners = []
    for m in mapped:
        overall = {p: mean(mean(m[p][r].values()) for r in rounds) for p in POSITIONS}
        run_winners.append(None if overall["for"] == overall["against"]
                           else ("for" if overall["for"] > overall["against"] else "against"))
    runs_agree = len(set(run_winners)) == 1

    if conceded_position is not None:
        winner = "against" if conceded_position == "for" else "for"
        return AggregatedVerdict(winner, False, totals, per_round, margin, runs_agree)

    if totals["for"] == totals["against"]:
        winner = None
    else:
        winner = "for" if totals["for"] > totals["against"] else "against"
    is_close = winner is None or not runs_agree or margin < close_margin
    return AggregatedVerdict(winner, is_close, totals, per_round, margin, runs_agree)
