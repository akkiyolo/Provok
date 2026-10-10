"""LLM gateway retry/fallback semantics (provider calls stubbed)."""
from __future__ import annotations

import pytest

from backend.app.llm import gateway
from backend.app.llm.gateway import LLMError, LLMResult, Role


@pytest.fixture
def calls(monkeypatch):
    log: list[tuple[str, bool]] = []
    script: dict[str, list] = {}

    async def fake_call_once(role, model, messages, *, json_mode, **kw):
        log.append((model.key, json_mode))
        outcome = script[model.key].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return LLMResult(outcome, model.key, 0, 0, 0, 0)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(gateway, "_call_once", fake_call_once)
    monkeypatch.setattr(gateway.asyncio, "sleep", no_sleep)
    return log, script


async def test_debater_never_falls_back_to_another_model(calls):
    log, script = calls
    script["gemini_flash"] = [LLMError("429", transient=True)] * 3
    with pytest.raises(LLMError):
        await gateway.complete(Role.WRITER, "gemini_flash", [{"role": "user", "content": "x"}])
    assert {k for k, _ in log} == {"gemini_flash"} and len(log) == 3  # 1 try + 2 backoff retries


async def test_debater_recovers_after_rate_limit(calls):
    log, script = calls
    script["gemini_flash"] = [LLMError("429", transient=True), "ok"]
    res = await gateway.complete(Role.WRITER, "gemini_flash", [{"role": "user", "content": "x"}])
    assert res.text == "ok" and len(log) == 2


async def test_non_transient_error_is_not_retried(calls):
    log, script = calls
    script["gemini_flash"] = [LLMError("404 model not found")]
    with pytest.raises(LLMError):
        await gateway.complete(Role.JUDGE, "gemini_flash", [{"role": "user", "content": "x"}])
    assert len(log) == 1


async def test_json_mode_rejection_retries_without_json_mode(calls):
    log, script = calls
    script["gemini_flash"] = [LLMError("json_validate_failed", json_rejected=True), '{"ok": true}']
    data = await gateway.complete_json(Role.LEDGER, "gemini_flash", [{"role": "user", "content": "x"}])
    assert data == {"ok": True}
    assert log == [("gemini_flash", True), ("gemini_flash", False)]


async def test_utility_role_falls_back(calls):
    log, script = calls
    script["gemini_flash"] = [LLMError("503", transient=True)]
    script["groq_gpt_oss_small"] = ['{"flagged": false}']
    data = await gateway.complete_json(Role.MODERATION, "gemini_flash", [{"role": "user", "content": "x"}])
    assert data == {"flagged": False} and [k for k, _ in log] == ["gemini_flash", "groq_gpt_oss_small"]
