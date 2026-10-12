"""Versioned prompt files live in llm/prompts/<name>.v<N>.md and use $placeholders."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

PROMPT_DIR = Path(__file__).parent / "prompts"

# Active version per prompt. Bump here when adding <name>.v2.md.
VERSIONS: dict[str, int] = {
    "debater_system": 1,
    "researcher": 1,
    "strategist": 1,
    "writer": 1,
    "critic": 1,
    "ledger": 1,
    "judge": 1,
    "citation_check": 1,
    "moderation": 1,
    "topic_check": 1,
    "post_question": 1,
    "fact_check": 1,
    "translate": 1,
}


@lru_cache
def _load(name: str, version: int) -> Template:
    return Template((PROMPT_DIR / f"{name}.v{version}.md").read_text(encoding="utf-8"))


def render(name: str, **values: object) -> str:
    """Render a prompt. Missing placeholders raise KeyError (fail loudly, never ship a broken prompt)."""
    return _load(name, VERSIONS[name]).substitute({k: str(v) for k, v in values.items()})


def prompt_id(name: str) -> str:
    return f"{name}.v{VERSIONS[name]}"
