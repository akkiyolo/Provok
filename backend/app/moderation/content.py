"""Content moderation and topic policy.

A fast deterministic layer runs first (free, never fails); the utility model adds
judgement on top. If the model is unavailable we fall back to the deterministic
result and mark the content `unchecked` rather than blocking the debate.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.llm import prompts
from backend.app.llm.gateway import LLMError, Role, complete_json
from backend.app.moderation.injection import neutralise

log = get_logger("provok.moderation")

TOPIC_CATEGORIES = [
    "technology", "science", "ethics", "economics", "business", "culture", "sports", "entertainment", "lifestyle",
    "education", "health", "philosophy", "environment", "history", "food", "relationships", "politics", "religion",
    "caste", "other",
]

_BLOCKLIST: dict[str, list[str]] = {
    "politics": [
        r"elections?", r"vot(e|ing) (for|against) (the )?(bjp|congress|aap|tmc|democrats?|republicans?)",
        r"bjp", r"congress party", r"aam aadmi", r"modi", r"rahul gandhi", r"kejriwal", r"amit shah",
        r"yogi adityanath", r"trump", r"biden", r"kamala harris", r"democrats?", r"republicans?", r"left[- ]wing",
        r"right[- ]wing", r"prime minister", r"chief minister", r"parliament(ary)?", r"lok sabha", r"rajya sabha",
        r"kashmir", r"khalistan", r"israel", r"palestin\w*", r"gaza", r"hamas", r"ukraine war", r"putin",
        r"political part(y|ies)", r"\bnrc\b", r"\bcaa\b", r"article 370",
    ],
    "religion": [
        r"religions?", r"religious", r"\bgods?\b", r"allah", r"jesus", r"christ(ian(ity)?)?", r"hindu(ism|tva|s)?",
        r"muslims?", r"islam(ic)?", r"sikh(ism|s)?", r"jain(ism)?", r"buddhis(m|t)", r"judaism", r"\bjews?\b",
        r"quran|koran", r"holy bible", r"bhagavad gita|\bgita\b", r"mosques?", r"ram mandir",
        r"babri", r"atheis(m|ts?)", r"religious conversions?", r"hijab", r"love jihad",
    ],
    "caste": [r"caste", r"dalits?", r"brahmins?", r"\bobcs?\b", r"\bsc/st\b", r"scheduled castes?",
              r"reservations? (in|for|system|policy|quota)", r"\bquota system\b", r"untouchab\w+"],
}
_BLOCK_RES = {cat: re.compile(r"\b(?:" + "|".join(pats) + r")", re.IGNORECASE) for cat, pats in _BLOCKLIST.items()}

_PHONE_RE = re.compile(
    r"(?<![\d.,])(?:(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}|\+\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4})(?![\d.,])"
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


@dataclass(frozen=True)
class TopicCheck:
    ok: bool
    category: str
    reason: str | None = None
    suggestion: str | None = None
    code: str | None = None


@dataclass(frozen=True)
class ModerationResult:
    flagged: bool
    categories: list[str] = field(default_factory=list)
    reason: str | None = None
    checked: bool = True  # False when only the heuristic layer ran


def heuristic_blocked_category(text: str) -> str | None:
    blocked = get_settings().blocked_categories
    for cat, rx in _BLOCK_RES.items():
        if cat in blocked and rx.search(text):
            return cat
    return None


async def check_topic(question: str) -> TopicCheck:
    s = get_settings()
    q = question.strip()
    if len(q) < s.question_min_chars:
        return TopicCheck(False, "other", "Make the question a little longer so both sides know what they're arguing.",
                          code="too_short")
    if len(q) > s.question_max_chars:
        return TopicCheck(False, "other", f"Keep the question under {s.question_max_chars} characters.",
                          code="too_long")
    hit = heuristic_blocked_category(q)
    if hit:
        return TopicCheck(False, hit, _blocked_message(hit), code="blocked_category")

    try:
        data = await complete_json(Role.TOPIC_CHECK, None, [
            {"role": "user", "content": prompts.render("topic_check", question=neutralise(q),
                                                       categories=", ".join(TOPIC_CATEGORIES))}],
            max_tokens=200, timeout=15)
    except LLMError as exc:
        log.warning("topic_check_unavailable", error=str(exc))
        return TopicCheck(True, "other")

    category = str(data.get("category", "other")).lower()
    if category not in TOPIC_CATEGORIES:
        category = "other"
    if category in s.blocked_categories:
        return TopicCheck(False, category, _blocked_message(category), code="blocked_category")
    if data.get("abusive"):
        return TopicCheck(False, category, "This question can't be debated here. Try a question about ideas, "
                                           "not people.", code="abusive")
    if data.get("debatable") is False:
        sugg = data.get("suggestion")
        return TopicCheck(False, category, "That reads like a factual question. Debates need two defensible sides.",
                          suggestion=str(sugg)[:200] if sugg else None, code="not_debatable")
    return TopicCheck(True, category)


def _blocked_message(category: str) -> str:
    return (f"We're keeping {category} off Provok for now — those debates get heated fast. "
            "Try technology, science, culture, sports, ethics or anything else.")


def heuristic_moderation(text: str) -> ModerationResult:
    cats: list[str] = []
    if _EMAIL_RE.search(text) or _PHONE_RE.search(text):
        cats.append("personal_data")
    if len(URL_RE.findall(text)) > 4:
        cats.append("spam")
    return ModerationResult(bool(cats), cats, "Contains contact details or link spam" if cats else None, checked=False)


async def moderate(text: str, *, debate_id: uuid.UUID | None = None) -> ModerationResult:
    if not get_settings().moderation_enabled:
        return ModerationResult(False, checked=False)
    base = heuristic_moderation(text)
    if base.flagged:
        return ModerationResult(True, base.categories, base.reason, checked=True)
    try:
        data = await complete_json(Role.MODERATION, None, [
            {"role": "user", "content": prompts.render("moderation", text=neutralise(text[:6000]))}],
            max_tokens=150, timeout=15, debate_id=debate_id)
    except LLMError as exc:
        log.warning("moderation_unavailable", error=str(exc))
        return base
    flagged = bool(data.get("flagged")) and str(data.get("severity", "medium")) != "low"
    cats = [str(c) for c in data.get("categories", [])][:5]
    return ModerationResult(flagged, cats, str(data.get("reason") or "")[:200] or None, checked=True)
