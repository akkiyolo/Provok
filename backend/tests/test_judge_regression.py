"""
Judge regression suite (spec §7): 10 fixture debates with expected outcomes.
LLM output is fixed in the fixtures, so this fails only if aggregation logic changes.
A separate manual script (backend/scripts/judge_live_eval.py) runs real models.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.core.config import get_settings
from backend.app.judge.aggregation import aggregate, parse_run

CASES = json.loads((Path(__file__).parent / "fixtures" / "judge_cases.json").read_text())


def test_there_are_ten_fixtures():
    assert len(CASES) == 10


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_judge_fixture(case):
    r1 = parse_run(case["run_for_is_A"], {"A": "for", "B": "against"}, case["rounds"])
    r2 = parse_run(case["run_for_is_B"], {"A": "against", "B": "for"}, case["rounds"])
    v = aggregate([r1, r2], close_margin=get_settings().close_margin, conceded_position=case["conceded_position"])
    assert (v.winner, v.is_close) == (case["expected"]["winner"], case["expected"]["is_close"]), case["description"]
