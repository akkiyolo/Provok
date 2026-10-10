"""Model registry: DB-backed, cached in-process, seeded from a JSON config file."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.db.session import session_scope
from backend.app.engine.types import ModelTier
from backend.app.models import ModelRegistry

log = get_logger("provok.llm.registry")
_CACHE_TTL = 60.0


@dataclass(frozen=True)
class ModelInfo:
    key: str
    litellm_id: str
    display_name: str
    provider: str
    tier: ModelTier
    enabled: bool
    selectable: bool
    rating: int
    sort_order: int


_cache: dict[str, ModelInfo] = {}
_cache_at = 0.0


def _to_info(m: ModelRegistry) -> ModelInfo:
    return ModelInfo(m.key, m.litellm_id, m.display_name, m.provider, ModelTier(m.tier), m.enabled, m.selectable,
                     m.rating, m.sort_order)


async def all_models(force: bool = False) -> dict[str, ModelInfo]:
    global _cache, _cache_at
    if force or not _cache or time.monotonic() - _cache_at > _CACHE_TTL:
        async with session_scope() as db:
            rows = (await db.scalars(select(ModelRegistry))).all()
        _cache = {m.key: _to_info(m) for m in rows}
        _cache_at = time.monotonic()
    return _cache


def invalidate_cache() -> None:
    global _cache_at
    _cache_at = 0.0


async def get_model(key: str) -> ModelInfo | None:
    return (await all_models()).get(key)


async def selectable_debaters() -> list[ModelInfo]:
    models = await all_models()
    return sorted(
        (m for m in models.values()
         if m.enabled and m.selectable and m.tier in (ModelTier.STANDARD, ModelTier.FLAGSHIP)),
        key=lambda m: m.sort_order,
    )


async def judge_candidates(debater_providers: set[str]) -> list[ModelInfo]:
    """Enabled judges in preference order: configured order, cross-family (vs the debaters) first."""
    models = await all_models()
    judges = [models[k] for k in get_settings().judge_keys if k in models and models[k].enabled]
    judges += sorted((m for m in models.values() if m.tier is ModelTier.JUDGE and m.enabled and m not in judges),
                     key=lambda m: m.sort_order)
    cross = [j for j in judges if j.provider not in debater_providers]
    return cross + [j for j in judges if j.provider in debater_providers]


async def pick_judge(debater_providers: set[str], attempt: int = 0) -> ModelInfo | None:
    """One judge per verdict (both blind runs use it). Retries rotate to the next candidate,
    so a provider outage doesn't strand debates — this is a new attempt, not a mid-run fallback."""
    candidates = await judge_candidates(debater_providers)
    return candidates[attempt % len(candidates)] if candidates else None


async def seed_registry(db: AsyncSession) -> int:
    """Insert seed models that don't exist yet. Never overwrites admin edits."""
    settings = get_settings()
    path = Path(settings.model_registry_seed_path)
    if not path.exists():
        log.warning("model_seed_missing", path=str(path))
        return 0
    seeds = json.loads(path.read_text(encoding="utf-8"))
    existing = set((await db.scalars(select(ModelRegistry.key))).all())
    added = 0
    for s in seeds:
        if s["key"] in existing:
            continue
        enabled = bool(s.get("enabled", True)) and (settings.llm_fake or settings.provider_configured(s["provider"]))
        db.add(ModelRegistry(
            key=s["key"], litellm_id=s["litellm_id"], display_name=s["display_name"], provider=s["provider"],
            tier=s["tier"], enabled=enabled, selectable=bool(s.get("selectable", True)), notes=s.get("notes"),
            sort_order=int(s.get("sort_order", 100)),
        ))
        added += 1
    if added:
        await db.flush()
        log.info("model_registry_seeded", added=added)
    invalidate_cache()
    return added
