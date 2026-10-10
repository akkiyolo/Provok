"""
Deterministic stand-in for every model role.

Used by the test suite, and by local dev / browser E2E runs when `LLM_FAKE=true`
(never allowed in production). Debates run end to end without provider keys.
"""
from __future__ import annotations

import json
import re
from typing import Any

from backend.app.llm.gateway import Role

CRITERIA = ["argument_strength", "evidence_quality", "rebuttal_coverage", "responsiveness", "consistency"]


class FakeLLM:
    def __init__(self) -> None:
        self.overrides: dict[Role, Any] = {}
        self.calls: list[tuple[Role, str]] = []

    def default(self, role: Role, messages: list[dict]) -> Any:
        prompt = messages[-1]["content"] if isinstance(messages[-1]["content"], str) else ""
        if role is Role.TOPIC_CHECK:
            return {"category": "technology", "debatable": True, "abusive": False, "suggestion": None, "reason": "ok"}
        if role is Role.MODERATION:
            return {"flagged": False, "categories": [], "severity": "low", "reason": "fine"}
        if role is Role.RESEARCHER:
            return {"facts": []}
        if role is Role.STRATEGIST:
            return {"targets": [], "defend": [], "new_points": ["p"], "cross_exam_question_target": None,
                    "search_query": None, "plan": "press the advantage"}
        if role is Role.WRITER:
            if "question" in prompt.split("Write our ")[-1][:20]:
                return "Can you name one concrete study that supports your central claim?"
            return ("Our case rests on clear evidence and simple reasoning. The opponent has not answered the core "
                    "point, and the costs they ignore are real and measurable.")
        if role is Role.CRITIC:
            return {"blocking": False, "issues": []}
        if role is Role.LEDGER:
            return {"claims": [{"text": "A substantive claim from this turn.", "source_url": None,
                                "responds_to": [], "effect": None}]}
        if role is Role.CITATION_CHECK:
            return {"verdict": "supported", "reason": "ok"}
        if role is Role.JUDGE:
            rounds = re.search(r"each round played \(([^)]*)\)", prompt)
            names = [r.strip() for r in rounds.group(1).split(",")] if rounds else ["opening"]

            def side(score: int) -> dict:
                return {r: {c: {"score": score, "why": "C1"} for c in CRITERIA} for r in names}
            # Label-independent: FOR opens the transcript, so its label is the first one there.
            m = re.search(r'TRANSCRIPT.*?<debate_text side="([AB])"', prompt, re.S)
            for_label = m.group(1) if m else "A"
            other = "B" if for_label == "A" else "A"
            return {"scores": {for_label: side(8), other: side(6)}, "winner": for_label, "decisive_claims": [1],
                    "explanation": f"Side {for_label} built the stronger case (C1)."}
        return "ok"

    async def __call__(self, role: Role, model_key: str, messages: list[dict]) -> str:
        self.calls.append((role, model_key))
        override = self.overrides.get(role)
        if callable(override):
            value = override(messages)
        elif override is not None:
            value = override
        else:
            value = self.default(role, messages)
        return value if isinstance(value, str) else json.dumps(value)
