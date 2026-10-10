"""Build the pure engine's config from settings. Timing modes differ only here."""
from __future__ import annotations

from backend.app.core.config import Settings, get_settings
from backend.app.engine.transitions import EngineConfig
from backend.app.engine.types import Timing

JUDGE_TIMEOUT_SECONDS = 15 * 60


def engine_config(timing: Timing | str, settings: Settings | None = None) -> EngineConfig:
    s = settings or get_settings()
    t = Timing(timing)
    live_like = t in (Timing.LIVE, Timing.VIDEO)
    return EngineConfig(
        human_turn_seconds={Timing.LIVE: s.live_turn_seconds, Timing.VIDEO: s.video_turn_seconds,
                            Timing.ASYNC: s.async_turn_seconds}[t],
        swarm_turn_timeout_seconds=s.swarm_turn_timeout_seconds,
        challenge_timeout_seconds=s.live_challenge_timeout_seconds if live_like else s.async_challenge_timeout_seconds,
        fallback_offer_timeout_seconds=s.fallback_offer_timeout_seconds,
        lobby_timeout_seconds=s.video_lobby_timeout_seconds,
        judge_timeout_seconds=JUDGE_TIMEOUT_SECONDS,
        round_vote_window_seconds=s.live_round_vote_window_seconds if live_like else None,
        final_vote_window_seconds=s.live_final_vote_window_seconds if live_like else s.async_final_vote_window_seconds,
        requires_ready_check=t is Timing.VIDEO,
    )
