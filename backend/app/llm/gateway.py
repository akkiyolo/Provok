"""
The single LLM gateway. Every model call in Provok goes through `complete()`.

- Resolves `model_key` → LiteLLM id via the model registry.
- Logs every call (tokens, cost, latency, success) to `llm_calls`.
- Fallbacks are allowed ONLY for utility roles. Debater and judge roles retry the
  same model once on transient errors and then fail, so model-vs-model results
  are always honest.
- Marks system prompts cacheable for Anthropic models.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.db.session import session_scope
from backend.app.llm.registry import ModelInfo, get_model
from backend.app.models import LLMCall

log = get_logger("provok.llm")


class Role(StrEnum):
    RESEARCHER = "researcher"
    STRATEGIST = "strategist"
    WRITER = "writer"
    CRITIC = "critic"
    LEDGER = "ledger"
    JUDGE = "judge"
    CITATION_CHECK = "citation_check"
    MODERATION = "moderation"
    TOPIC_CHECK = "topic_check"
    INJECTION_CHECK = "injection_check"


DEBATER_ROLES = {Role.STRATEGIST, Role.WRITER, Role.CRITIC}
JUDGE_ROLES = {Role.JUDGE, Role.CITATION_CHECK}
UTILITY_ROLES = set(Role) - DEBATER_ROLES - JUDGE_ROLES


class LLMError(Exception):
    def __init__(self, message: str, *, transient: bool = False, retry_after: float | None = None,
                 json_rejected: bool = False, malformed: bool = False) -> None:
        super().__init__(message)
        self.transient = transient
        self.retry_after = retry_after
        self.json_rejected = json_rejected
        self.malformed = malformed  # the call succeeded but the output could not be parsed


@dataclass(frozen=True)
class LLMResult:
    text: str
    model_key: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    latency_ms: int


Messages = list[dict[str, Any]]
# Test hook: replaces the provider call. (role, model_key, messages) -> text
Responder = Callable[[Role, str, Messages], Awaitable[str]]
_test_responder: Responder | None = None


def set_test_responder(fn: Responder | None) -> None:
    global _test_responder
    _test_responder = fn


_fake: Responder | None = None


def _fake_responder() -> Responder | None:
    global _fake
    if not get_settings().llm_fake:
        return None
    if _fake is None:
        from backend.app.llm.fake import FakeLLM
        _fake = FakeLLM()
    return _fake


_initialised = False


def _init_litellm() -> None:
    global _initialised
    if _initialised:
        return
    import litellm

    settings = get_settings()
    settings.export_provider_keys()
    litellm.suppress_debug_info = True
    litellm.drop_params = True  # ignore params a provider doesn't support (e.g. response_format)
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]
    _initialised = True


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def clean_text(text: str) -> str:
    """Remove reasoning traces some models emit."""
    if "</think>" in text:
        text = text.split("</think>")[-1]
    return _THINK_RE.sub("", text).replace("<think>", "").strip()


def parse_json(text: str) -> Any:
    """Extract the first JSON object/array from model output (handles ``` fences and chatter)."""
    t = clean_text(text)
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = t.find(open_c)
        end = t.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(t[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError("Model did not return valid JSON", malformed=True)


def _with_cache_control(messages: Messages, model: ModelInfo) -> Messages:
    if model.provider != "anthropic" or model.litellm_id.startswith("bedrock/"):
        return messages
    out: Messages = []
    for i, m in enumerate(messages):
        # Cache the system prompt and the long shared history (everything before the final instruction).
        if m["role"] == "system" or (i == len(messages) - 2 and isinstance(m.get("content"), str)):
            out.append({"role": m["role"], "content": [
                {"type": "text", "text": m["content"], "cache_control": {"type": "ephemeral"}}]})
        else:
            out.append(m)
    return out


async def _log_call(*, debate_id: uuid.UUID | None, role: Role, model: ModelInfo, input_tokens: int,
                    output_tokens: int, cost: Decimal, latency_ms: int, success: bool, error: str | None) -> None:
    try:
        async with session_scope() as db:
            db.add(LLMCall(debate_id=debate_id, role=role.value, model_key=model.key, litellm_id=model.litellm_id,
                           input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost,
                           latency_ms=latency_ms, success=success, error=(error or "")[:500] or None))
    except Exception as exc:  # pragma: no cover - logging must never break the caller
        log.warning("llm_call_log_failed", error=str(exc))


def _is_reasoning_model(model: ModelInfo) -> bool:
    lid = model.litellm_id.lower()
    return ("gpt-oss" in lid or "/o1" in lid or "/o3" in lid or "/o4" in lid or "deepseek-r1" in lid
            or "gemini-2.5" in lid or "gemini-3" in lid)


def _retry_after(exc: Exception) -> float | None:
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None) or {}
    try:
        value = headers.get("retry-after") or headers.get("Retry-After")
        return float(value) if value else None
    except (TypeError, ValueError):
        return None


def _is_transient(exc: Exception) -> bool:
    name = type(exc).__name__
    return any(k in name for k in ("Timeout", "RateLimit", "ServiceUnavailable", "APIConnection",
                                   "InternalServer", "BadGateway")) or isinstance(exc, asyncio.TimeoutError)


async def _call_once(role: Role, model: ModelInfo, messages: Messages, *, max_tokens: int, timeout: int,
                     temperature: float, json_mode: bool, debate_id: uuid.UUID | None) -> LLMResult:
    started = time.perf_counter()
    responder = _test_responder or _fake_responder()
    if responder is not None:
        text = await responder(role, model.key, messages)
        latency = int((time.perf_counter() - started) * 1000)
        await _log_call(debate_id=debate_id, role=role, model=model, input_tokens=0, output_tokens=0,
                        cost=Decimal("0"), latency_ms=latency, success=True, error=None)
        return LLMResult(clean_text(text), model.key, 0, 0, Decimal("0"), latency)

    _init_litellm()
    import litellm

    kwargs: dict[str, Any] = {
        "model": model.litellm_id,
        "messages": _with_cache_control(messages, model),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "timeout": timeout,
        "num_retries": 0,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if _is_reasoning_model(model):
        # Reasoning tokens count against max_tokens; keep effort low and leave room for the visible answer.
        kwargs["reasoning_effort"] = "low"
        kwargs["max_tokens"] = max(max_tokens * 3, 2000)
    try:
        resp = await asyncio.wait_for(litellm.acompletion(**kwargs), timeout=timeout + 5)
    except Exception as exc:
        latency = int((time.perf_counter() - started) * 1000)
        await _log_call(debate_id=debate_id, role=role, model=model, input_tokens=0, output_tokens=0,
                        cost=Decimal("0"), latency_ms=latency, success=False, error=f"{type(exc).__name__}: {exc}")
        msg = str(exc).lower()
        raise LLMError(f"{model.key} failed: {type(exc).__name__}", transient=_is_transient(exc),
                       retry_after=_retry_after(exc),
                       json_rejected=json_mode and "json" in msg and "BadRequest" in type(exc).__name__) from exc

    latency = int((time.perf_counter() - started) * 1000)
    content = resp.choices[0].message.content
    if isinstance(content, list):
        content = "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
    text = clean_text(str(content or ""))
    usage = getattr(resp, "usage", None)
    in_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
    out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
    try:
        cost = Decimal(str(litellm.completion_cost(completion_response=resp) or 0)).quantize(Decimal("0.000001"))
    except Exception:
        cost = Decimal("0")
    if cost == 0 and (model.provider in ("anthropic", "openai", "gemini") or model.litellm_id.startswith("bedrock/")) \
            and (in_tok or out_tok):
        log.warning("llm_cost_zero_for_paid_model", model_key=model.key, litellm_id=model.litellm_id)
    await _log_call(debate_id=debate_id, role=role, model=model, input_tokens=in_tok, output_tokens=out_tok,
                    cost=cost, latency_ms=latency, success=bool(text), error=None if text else "empty response")
    if not text:
        raise LLMError(f"{model.key} returned an empty response", transient=True)
    return LLMResult(text, model.key, in_tok, out_tok, cost, latency)


async def complete(role: Role, model_key: str | None, messages: Messages, *, max_tokens: int | None = None,
                   timeout: int | None = None, temperature: float = 0.7, json_mode: bool = False,
                   debate_id: uuid.UUID | None = None) -> LLMResult:
    settings = get_settings()
    key = model_key or settings.utility_model_key
    max_tokens = max_tokens or settings.llm_max_output_tokens
    timeout = timeout or settings.llm_timeout_seconds

    async def attempt(model: ModelInfo, *, retries: int) -> LLMResult:
        """Same-model retries: JSON-mode rejections retry without JSON mode; transient errors back off."""
        use_json = json_mode
        n = 0
        while True:
            try:
                return await _call_once(role, model, messages, max_tokens=max_tokens, timeout=timeout,
                                        temperature=temperature, json_mode=use_json, debate_id=debate_id)
            except LLMError as exc:
                if exc.json_rejected and use_json:
                    use_json = False  # provider's strict JSON validator; our parser handles loose JSON
                    continue
                if not exc.transient or n >= retries:
                    raise
                delay = min(20.0, exc.retry_after if exc.retry_after else (2.0 * (3 ** n)))
                log.warning("llm_retry_same_model", role=role.value, model_key=model.key, delay=delay, error=str(exc))
                n += 1
                await asyncio.sleep(delay)

    if role in UTILITY_ROLES:
        candidates = [key, *[k for k in settings.utility_fallbacks if k != key]]
        last_exc: Exception | None = None
        for k in candidates:
            model = await get_model(k)
            if model is None or not model.enabled:
                continue
            try:
                return await attempt(model, retries=0)
            except LLMError as exc:
                last_exc = exc
                log.warning("llm_utility_fallback", role=role.value, failed=k, error=str(exc))
        raise LLMError(f"All utility models failed for {role.value}: {last_exc}", transient=True)

    # Debater and judge roles never switch models (model-vs-model results must be honest).
    model = await get_model(key)
    if model is None:
        raise LLMError(f"Unknown model '{key}'")
    if not model.enabled:
        raise LLMError(f"Model '{key}' is disabled")
    return await attempt(model, retries=2)


async def complete_json(role: Role, model_key: str | None, messages: Messages, **kwargs: Any) -> Any:
    """complete() + JSON parsing, with one repair attempt on malformed JSON."""
    res = await complete(role, model_key, messages, json_mode=True, temperature=kwargs.pop("temperature", 0.2),
                         **kwargs)
    try:
        return parse_json(res.text)
    except LLMError:
        repair = messages + [{"role": "assistant", "content": res.text},
                             {"role": "user", "content": "That was not valid JSON. Reply with ONLY the JSON."}]
        res2 = await complete(role, model_key, repair, json_mode=True, temperature=0.0, **kwargs)
        return parse_json(res2.text)
