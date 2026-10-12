"""AI on posts: debate questions for "Challenge", fact-checks and translations. Post text is untrusted data and
only ever reaches a model inside delimiters, neutralised (CLAUDE.md rule 6)."""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import AppError
from backend.app.core.logging import get_logger
from backend.app.core.security import utcnow
from backend.app.db.session import session_scope
from backend.app.llm import prompts
from backend.app.llm.gateway import LLMError, Role, complete_json
from backend.app.models import Post, PostFactCheck, PostTranslation
from backend.app.moderation.injection import neutralise
from backend.app.services.search import safe_search

log = get_logger("provok.post_ai")

# ── Language ───────────────────────────────────────────────────────────────

# Unicode blocks of the scripts used in India, checked in order.
_SCRIPTS = [
    ("hi", 0x0900, 0x097F),  # Devanagari (Hindi, Marathi, …)
    ("bn", 0x0980, 0x09FF), ("pa", 0x0A00, 0x0A7F), ("gu", 0x0A80, 0x0AFF), ("or", 0x0B00, 0x0B7F),
    ("ta", 0x0B80, 0x0BFF), ("te", 0x0C00, 0x0C7F), ("kn", 0x0C80, 0x0CFF), ("ml", 0x0D00, 0x0D7F),
]
LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "bn": "Bengali", "pa": "Punjabi", "gu": "Gujarati", "or": "Odia",
                  "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "ml": "Malayalam"}
TRANSLATE_TO = ("en", "hi")


def detect_lang(text: str | None) -> str | None:
    """The script most of the letters are written in (romanised Hindi reads as English)."""
    letters = [c for c in (text or "") if c.isalpha()]
    if not letters:
        return None
    for code, lo, hi in _SCRIPTS:
        if sum(lo <= ord(c) <= hi for c in letters) / len(letters) >= 0.3:
            return code
    return "en"


# ── Challenge: post → debate question ──────────────────────────────────────


async def suggest_question(post: Post) -> dict[str, Any]:
    if not post.text:
        raise AppError("There's nothing to debate in this post.", code="not_debatable", status_code=422)
    try:
        data = await complete_json(Role.POST_QUESTION, None, [
            {"role": "user", "content": prompts.render("post_question", post=neutralise(post.text))}],
            max_tokens=200, timeout=20)
    except LLMError as exc:
        raise AppError("Couldn't suggest a question right now. Write your own.", code="suggest_unavailable",
                       status_code=503) from exc
    question = " ".join(str(data.get("question") or "").split())[:400]
    if not data.get("debatable", True) or not question:
        raise AppError("This post doesn't make a claim to debate. Try one with an opinion.", code="not_debatable",
                       status_code=422)
    author_side = "against" if str(data.get("author_side")).lower() == "against" else "for"
    return {"question": question, "author_side": author_side,
            "challenger_side": "for" if author_side == "against" else "against"}


# ── Fact-checks ────────────────────────────────────────────────────────────

FACTCHECK_RETRY_AFTER = timedelta(minutes=10)
RATINGS = {"accurate", "mostly_accurate", "missing_context", "misleading", "false", "unverifiable"}


def factcheck_view(fc: PostFactCheck | None) -> dict[str, Any] | None:
    if fc is None:
        return None
    return {"status": fc.status, "rating": fc.rating, "summary": fc.summary, "sources": fc.sources,
            "updated_at": fc.updated_at}


async def request_factcheck(db: AsyncSession, post: Post, user_id: uuid.UUID) -> tuple[PostFactCheck, bool]:
    """Returns the fact-check and whether a new check needs to run. One check per post, shared by all readers."""
    if not post.text:
        raise AppError("There's nothing to fact-check in this post.", code="not_checkable", status_code=422)
    fc = await db.get(PostFactCheck, post.id, with_for_update={"key_share": True})
    if fc is None:
        await db.execute(insert(PostFactCheck).values(post_id=post.id, status="pending", requested_by=user_id)
                         .on_conflict_do_nothing())
        fc = await db.get(PostFactCheck, post.id, populate_existing=True)
        return fc, True  # type: ignore[return-value]
    if fc.status == "failed" and fc.updated_at < utcnow() - FACTCHECK_RETRY_AFTER:
        fc.status, fc.requested_by = "pending", user_id
        return fc, True
    return fc, False


async def run_factcheck(post_id: uuid.UUID) -> None:
    async with session_scope() as db:
        post = await db.get(Post, post_id)
        fc = await db.get(PostFactCheck, post_id)
        if post is None or fc is None or fc.status != "pending" or not post.text:
            return
        text = post.text
    results = await safe_search(" ".join(text.split())[:300], max_results=5)
    status, rating, summary, sources = "failed", None, None, []
    if results:
        listing = "\n\n".join(f"[{i}] {neutralise(r.title)} ({r.url})\n{neutralise(r.content[:800])}"
                              for i, r in enumerate(results, 1))
        try:
            data = await complete_json(Role.FACT_CHECK, None, [
                {"role": "user", "content": prompts.render("fact_check", post=neutralise(text), sources=listing)}],
                max_tokens=400, timeout=40)
            if not data.get("checkable", True):
                status = "opinion"
            elif str(data.get("rating")) in RATINGS:
                status, rating = "done", str(data["rating"])
                summary = " ".join(str(data.get("summary") or "").split())[:600] or None
                picked = [int(n) for n in data.get("sources") or [] if str(n).isdigit()]
                sources = [{"title": results[n - 1].title[:200], "url": results[n - 1].url}
                           for n in picked[:3] if 1 <= n <= len(results)]
        except LLMError as exc:
            log.warning("factcheck_failed", post_id=str(post_id), error=str(exc))
    else:
        log.warning("factcheck_no_sources", post_id=str(post_id))
    async with session_scope() as db:
        fc = await db.get(PostFactCheck, post_id, with_for_update=True)
        if fc is not None and fc.status == "pending":
            fc.status, fc.rating, fc.summary, fc.sources = status, rating, summary, sources


# ── Translations ───────────────────────────────────────────────────────────


async def translate(db: AsyncSession, post: Post, to: str) -> dict[str, str]:
    if to not in TRANSLATE_TO:
        raise AppError("Translation to that language isn't available yet.", code="bad_language", status_code=422)
    if not post.text:
        raise AppError("There's no text to translate.", code="nothing_to_translate", status_code=422)
    cached = await db.scalar(select(PostTranslation.text).where(PostTranslation.post_id == post.id,
                                                                PostTranslation.lang == to))
    if cached is not None:
        return {"lang": to, "text": cached}
    try:
        data = await complete_json(Role.TRANSLATE, None, [
            {"role": "user", "content": prompts.render("translate", language=LANGUAGE_NAMES[to],
                                                       post=neutralise(post.text))}],
            max_tokens=900, timeout=30)
    except LLMError as exc:
        raise AppError("Translation isn't available right now. Try again in a moment.", code="translate_unavailable",
                       status_code=503) from exc
    text = str(data.get("text") or "").strip()[:1500]
    if not text:
        raise AppError("Translation isn't available right now.", code="translate_unavailable", status_code=503)
    await db.execute(insert(PostTranslation).values(post_id=post.id, lang=to, text=text).on_conflict_do_nothing())
    return {"lang": to, "text": text}
