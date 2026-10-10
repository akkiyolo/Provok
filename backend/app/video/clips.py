"""
Highlight clips for video debates (ffmpeg in the worker).

Moments, in priority order: judge-decisive claims, sources caught as
"misattributed", and the round with the biggest audience vote swing. Each clip is
a 30-60s vertical (9:16) cut with burned-in captions and the question on top.
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.db.session import session_scope
from backend.app.engine.types import ClaimStatus
from backend.app.models import Claim, Clip, DebateRound, Turn, Verdict, VideoSession
from backend.app.services import storage

log = get_logger("provok.clips")
MAX_CLIPS = 3


@dataclass(frozen=True)
class Moment:
    start_ms: int
    end_ms: int
    reason: str
    turn: Turn


def _window(turn: Turn, reason: str) -> Moment | None:
    s = get_settings()
    if turn.started_ms is None or turn.ended_ms is None:
        return None
    start = max(0, turn.started_ms - 1500)
    end = min(turn.ended_ms + 1500, start + s.clip_max_seconds * 1000)
    if end - start < s.clip_min_seconds * 1000:
        end = start + s.clip_min_seconds * 1000
    return Moment(start, end, reason, turn)


def pick_moments(turns: list[Turn], claims: list[Claim], decisive_ids: list[str],
                 rounds: list[DebateRound]) -> list[Moment]:
    by_id = {t.id: t for t in turns}
    picks: list[Moment] = []
    used: set[uuid.UUID] = set()

    def add(turn: Turn | None, reason: str) -> None:
        if turn is None or turn.id in used or len(picks) >= MAX_CLIPS:
            return
        m = _window(turn, reason)
        if m:
            picks.append(m)
            used.add(turn.id)

    claim_by_id = {str(c.id): c for c in claims}
    for cid in decisive_ids:
        c = claim_by_id.get(cid)
        if c:
            add(by_id.get(c.turn_id), f"Decisive moment (C{c.seq})")
    for c in claims:
        if c.status == ClaimStatus.MISATTRIBUTED:
            add(by_id.get(c.turn_id), f"Source doesn't say that (C{c.seq})")
    prev = 0.5
    swings = []
    for r in sorted(rounds, key=lambda x: x.started_at or x.ended_at or 0):  # type: ignore[arg-type,return-value]
        if r.tally:
            share = float(r.tally.get("for_share", 0.5))
            swings.append((abs(share - prev), r.round))
            prev = share
    if swings:
        _, swing_round = max(swings)
        round_turns = [t for t in turns if t.round == swing_round and not t.is_forfeit]
        if round_turns:
            add(max(round_turns, key=lambda t: t.word_count), "Biggest audience swing")
    return picks


def _srt(segments: list[dict], start_ms: int, end_ms: int) -> str:
    def ts(ms: int) -> str:
        h, rem = divmod(ms, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, ms_ = divmod(rem, 1000)
        return f"{h:02}:{m:02}:{s:02},{ms_:03}"
    lines, n = [], 1
    for seg in segments:
        a, b = int(seg.get("start_ms", 0)), int(seg.get("end_ms", 0))
        if b <= start_ms or a >= end_ms:
            continue
        lines.append(f"{n}\n{ts(max(0, a - start_ms))} --> {ts(min(end_ms, b) - start_ms)}\n{seg['text']}\n")
        n += 1
    return "\n".join(lines)


def _ffmpeg_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")


async def _render(src: Path, out: Path, m: Moment, question: str, workdir: Path) -> None:
    srt_path = workdir / f"{m.turn.id}.srt"
    srt_path.write_text(_srt(m.turn.segments or [], m.start_ms, m.end_ms), encoding="utf-8")
    q = _ffmpeg_escape(question[:90])
    vf = (
        "crop=ih*9/16:ih,scale=1080:1920,"
        f"drawtext=text='{q}':fontcolor=white:fontsize=54:box=1:boxcolor=black@0.55:boxborderw=24:"
        "x=(w-text_w)/2:y=140,"
        f"subtitles='{_ffmpeg_escape(srt_path.as_posix())}':force_style='FontSize=18,Outline=2,MarginV=120'"
    )
    cmd = ["ffmpeg", "-y", "-ss", f"{m.start_ms / 1000:.2f}", "-to", f"{m.end_ms / 1000:.2f}", "-i", str(src),
           "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "128k",
           "-movflags", "+faststart", str(out)]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL,
                                                stderr=asyncio.subprocess.PIPE)
    _, err = await asyncio.wait_for(proc.communicate(), timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {err.decode(errors='replace')[-400:]}")


async def generate_clips_for_debate(debate_id: uuid.UUID) -> int:
    if shutil.which("ffmpeg") is None:
        log.error("ffmpeg_missing")
        return 0
    async with session_scope() as db:
        vs = await db.scalar(select(VideoSession).where(VideoSession.debate_id == debate_id))
        if vs is None or not vs.recording_key:
            log.info("clips_no_recording", debate_id=str(debate_id))
            return 0
        if await db.scalar(select(Clip.id).where(Clip.debate_id == debate_id).limit(1)):
            return 0  # idempotent
        from backend.app.models import Debate
        debate = await db.get(Debate, debate_id)
        turns = list((await db.scalars(select(Turn).where(Turn.debate_id == debate_id))).all())
        claims = list((await db.scalars(select(Claim).where(Claim.debate_id == debate_id))).all())
        verdict = await db.scalar(select(Verdict).where(Verdict.debate_id == debate_id))
        rounds = list((await db.scalars(select(DebateRound).where(DebateRound.debate_id == debate_id))).all())
        moments = pick_moments(turns, claims, (verdict.decisive_claim_ids or []) if verdict else [], rounds)
        rec_key, question = vs.recording_key, debate.question if debate else ""
    if not moments:
        return 0
    made = 0
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        src = await storage.download_to(rec_key, work / "recording.mp4")
        for i, m in enumerate(moments):
            out = work / f"clip{i}.mp4"
            try:
                await _render(src, out, m, question, work)
                url = await storage.put_bytes(f"clips/{debate_id}/{i}.mp4", out.read_bytes(), "video/mp4")
                status = "ready"
            except Exception as exc:
                log.error("clip_render_failed", debate_id=str(debate_id), error=str(exc)[:300])
                url, status = None, "failed"
            async with session_scope() as db:
                db.add(Clip(debate_id=debate_id, start_ms=m.start_ms, end_ms=m.end_ms, reason=m.reason,
                            caption=m.turn.content[:500], url=url, status=status))
            made += status == "ready"
    return made
