"""
One AI swarm turn: researcher → strategist → writer → critic (→ one revision).

v1 design choice (documented in PROGRESS.md): the critic runs BEFORE streaming. We
generate draft → critique → (revise) → final, then stream the final text to the
arena with a typing effect. Viewers never see text that is later retracted.
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.engine.types import Persona, Position, Round, TurnKind
from backend.app.llm import prompts
from backend.app.llm.gateway import LLMError, Role, complete, complete_json
from backend.app.models import Claim, Debate, ResearchCache, Side, Turn
from backend.app.moderation.injection import UNTRUSTED_NOTICE
from backend.app.realtime.publish import publish_debate
from backend.app.services.search import safe_search
from backend.app.swarm.context import (
    GUIDANCE,
    PERSONAS,
    QUESTION_WORD_CAP,
    ROUND_NAMES,
    facts_block,
    history_block,
    ledger_block,
)

log = get_logger("provok.swarm")

_FACT_MARK = re.compile(r"\[F(\d{1,3})\]")
_URL = re.compile(r"https?://[^\s)\]]+")
_MD = re.compile(r"(^#{1,6}\s+|\*\*|__|^\s*[-*•]\s+)", re.MULTILINE)


@dataclass
class SwarmContext:
    debate: Debate
    side: Side
    position: Position
    round: Round
    kind: TurnKind
    turns: list[Turn]
    claims: list[Claim]
    side_pos: dict[uuid.UUID, str]
    model_key: str
    persona: Persona


@dataclass
class SwarmOutput:
    content: str
    word_count: int
    citations: list[dict[str, Any]]
    model_key: str


def count_words(text: str) -> int:
    return len(text.split())


def word_cap(ctx_kind: TurnKind, word_limit: int) -> int:
    s = get_settings()
    if ctx_kind is TurnKind.ANSWER:
        return min(word_limit, s.cross_exam_answer_word_limit)
    if ctx_kind is TurnKind.QUESTION:
        return min(word_limit, QUESTION_WORD_CAP)
    return word_limit


def truncate_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text.strip()
    cut = " ".join(words[:limit])
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if end > len(cut) * 0.6:
        return cut[: end + 1].strip()
    return cut.rstrip(",;:") + "…"


def enforce_citations(text: str, facts: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Replace [F#] markers with [n] footnotes; drop unknown markers and any raw URL not in the cache."""
    by_id = {f["id"]: f for f in facts}
    allowed_urls = {f["url"] for f in facts}
    numbering: dict[str, int] = {}
    citations: list[dict[str, Any]] = []

    def _mark(m: re.Match[str]) -> str:
        fid = f"F{m.group(1)}"
        fact = by_id.get(fid)
        if fact is None:
            return ""
        if fid not in numbering:
            numbering[fid] = len(numbering) + 1
            citations.append({"n": numbering[fid], "url": fact["url"], "title": fact.get("title") or fact["url"]})
        return f"[{numbering[fid]}]"

    text = _FACT_MARK.sub(_mark, text)
    text = _URL.sub(lambda m: m.group(0) if m.group(0) in allowed_urls else "", text)
    text = _MD.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    return text.strip(), citations


# ── Research ───────────────────────────────────────────────────────────────


async def _extract_facts(question: str, position: Position, results: list, start_id: int,
                         debate_id: uuid.UUID, max_facts: int) -> list[dict[str, Any]]:
    if not results:
        return []
    block = "\n\n".join(f"[R{i + 1}] {r.title}\nurl: {r.url}\n{r.content}" for i, r in enumerate(results))
    try:
        data = await complete_json(Role.RESEARCHER, None, [{"role": "user", "content": prompts.render(
            "researcher", question=question, position_upper=position.value.upper(), results_block=block,
            max_facts=max_facts)}], max_tokens=1200, timeout=40, debate_id=debate_id)
    except LLMError as exc:
        log.warning("research_extract_failed", error=str(exc))
        return []
    valid_urls = {r.url: r.title for r in results}
    facts = []
    for f in data.get("facts", [])[:max_facts] if isinstance(data, dict) else []:
        url = str(f.get("url", ""))
        if url not in valid_urls or not str(f.get("fact", "")).strip():
            continue  # facts must come from an actual result
        facts.append({"id": f"F{start_id + len(facts)}", "fact": str(f["fact"])[:400], "url": url,
                      "title": str(f.get("title") or valid_urls[url])[:200], "use": f.get("use", "support")})
    return facts


async def ensure_research(db: AsyncSession, debate: Debate, position: Position) -> ResearchCache:
    s = get_settings()
    cache = await db.scalar(select(ResearchCache).where(ResearchCache.debate_id == debate.id,
                                                        ResearchCache.position == position.value))
    if cache is not None:
        return cache
    stance = "benefits evidence supporting" if position is Position.FOR else "risks evidence against"
    queries = [debate.question, f"{debate.question} {stance}"]
    results_lists = await asyncio.gather(*(safe_search(q) for q in queries))
    seen: set[str] = set()
    results = []
    for lst in results_lists:
        for r in lst:
            if r.url not in seen:
                seen.add(r.url)
                results.append(r)
    facts = await _extract_facts(debate.question, position, results[:10], 1, debate.id, s.research_max_facts)
    cache = ResearchCache(debate_id=debate.id, position=position.value, facts=facts, queries=queries)
    db.add(cache)
    await db.flush()
    return cache


async def targeted_research(db: AsyncSession, debate: Debate, cache: ResearchCache, query: str) -> None:
    s = get_settings()
    if len(cache.facts) >= s.research_max_facts * 2 or query in cache.queries:
        return
    results = await safe_search(query, 4)
    new = await _extract_facts(debate.question, Position(cache.position), results, len(cache.facts) + 1, debate.id, 4)
    known = {f["url"] + f["fact"] for f in cache.facts}
    cache.facts = cache.facts + [f for f in new if f["url"] + f["fact"] not in known]
    cache.queries = cache.queries + [query]
    await db.flush()


# ── Pipeline ───────────────────────────────────────────────────────────────


def _system(ctx: SwarmContext) -> dict[str, str]:
    return {"role": "system", "content": prompts.render(
        "debater_system", question=ctx.debate.question, position_upper=ctx.position.value.upper(),
        persona=PERSONAS[ctx.persona], untrusted_notice=UNTRUSTED_NOTICE)}


async def run_pipeline(db: AsyncSession, ctx: SwarmContext) -> SwarmOutput:
    debate = ctx.debate
    cache = await ensure_research(db, debate, ctx.position)
    ledger = ledger_block(ctx.claims, ctx.side_pos, relative_to=ctx.position.value)
    history = history_block(ctx.turns, ctx.side_pos)
    guidance = GUIDANCE[(ctx.round, ctx.kind)]
    round_name = ROUND_NAMES[ctx.round]
    cap = word_cap(ctx.kind, debate.word_limit)
    system = _system(ctx)

    # Strategist
    strategy: dict[str, Any] = {}
    try:
        raw = await complete_json(Role.STRATEGIST, ctx.model_key, [system, {"role": "user", "content": prompts.render(
            "strategist", round_name=round_name, kind=ctx.kind.value, round_guidance=guidance, ledger_block=ledger,
            facts_block=facts_block(cache.facts), history_block=history)}],
            max_tokens=600, timeout=60, debate_id=debate.id)
        strategy = raw if isinstance(raw, dict) else {}
    except LLMError as exc:
        if not (exc.transient or exc.malformed):
            raise
        log.warning("strategist_failed_continuing", error=str(exc))
    query = strategy.get("search_query")
    if isinstance(query, str) and query.strip():
        await targeted_research(db, debate, cache, query.strip()[:200])
    facts = list(cache.facts)

    async def write(revision_note: str = "") -> str:
        res = await complete(Role.WRITER, ctx.model_key, [system, {"role": "user", "content": prompts.render(
            "writer", kind=ctx.kind.value, round_name=round_name, round_guidance=guidance,
            strategy=json.dumps(strategy, ensure_ascii=False)[:2000] or "{}", facts_block=facts_block(facts),
            ledger_block=ledger, history_block=history, revision_block=revision_note, word_limit=cap,
            target_words=max(20, int(cap * 0.85)))}],
            max_tokens=min(1500, cap * 3 + 200), timeout=90, debate_id=debate.id, temperature=0.8)
        return res.text

    draft = await write()
    text, citations = enforce_citations(draft, facts)

    # Critic (before anything is shown to the audience)
    try:
        review = await complete_json(Role.CRITIC, ctx.model_key, [system, {"role": "user", "content": prompts.render(
            "critic", kind=ctx.kind.value, round_name=round_name, position_upper=ctx.position.value.upper(),
            question=debate.question, draft=draft, facts_block=facts_block(facts), ledger_block=ledger,
            word_limit=cap)}], max_tokens=400, timeout=45, debate_id=debate.id)
    except LLMError as exc:
        # The critic only improves a draft that already exists; an outage or unreadable review never fails the turn.
        if not (exc.transient or exc.malformed):
            raise
        log.warning("critic_failed_continuing", error=str(exc))
        review = {}
    if isinstance(review, dict) and review.get("blocking") and review.get("issues"):
        issues = "\n".join(f"- {i}" for i in list(review["issues"])[:6])
        note = (f"\nREVISION REQUIRED — your previous draft:\n{draft}\n\nFix these issues:\n{issues}\n")
        draft2 = await write(note)
        text, citations = enforce_citations(draft2, facts)

    text = truncate_words(text, cap)
    if not text:
        raise LLMError("Swarm produced an empty turn")
    used = {int(n) for n in re.findall(r"\[(\d+)\]", text)}
    citations = [c for c in citations if c["n"] in used]
    return SwarmOutput(text, count_words(text), citations, ctx.model_key)


async def stream_typing(debate_id: uuid.UUID, position: Position, text: str, *, words_per_chunk: int = 4,
                        delay: float = 0.07) -> None:
    """Broadcast the final text in small chunks so the arena can render a live typing effect."""
    words = text.split(" ")
    await publish_debate(debate_id, "typing_start", {"position": position.value})
    for i in range(0, len(words), words_per_chunk):
        await publish_debate(debate_id, "typing", {"position": position.value,
                                                   "delta": " ".join(words[i:i + words_per_chunk]) + " "})
        await asyncio.sleep(delay)
    await publish_debate(debate_id, "typing_end", {"position": position.value})


async def load_context(db: AsyncSession, debate: Debate, position: Position, round_: Round, kind: TurnKind,
                       ) -> SwarmContext:
    side = debate.side(position)
    cfg = side.swarm_config or {}
    turns = list((await db.scalars(select(Turn).where(Turn.debate_id == debate.id)
                                   .order_by(Turn.created_at, Turn.turn_index))).all())
    claims = list((await db.scalars(select(Claim).where(Claim.debate_id == debate.id).order_by(Claim.seq))).all())
    return SwarmContext(
        debate=debate, side=side, position=position, round=round_, kind=kind, turns=turns, claims=claims,
        side_pos={s.id: s.position for s in debate.sides},
        model_key=str(cfg.get("model_key") or get_settings().default_swarm_model_key),
        persona=Persona(cfg.get("persona", Persona.DATA_DRIVEN.value)),
    )

