"""Featured AI-vs-AI debates: keeps the feed alive and shows off model-vs-model matchups."""
from __future__ import annotations

import json
import random
import uuid
from pathlib import Path

from sqlalchemy import select

from backend.app.core.config import APP_DIR
from backend.app.core.logging import get_logger
from backend.app.core.security import utcnow
from backend.app.db.session import session_scope
from backend.app.engine import transitions as tx
from backend.app.engine.config import engine_config
from backend.app.engine.service import apply_initial
from backend.app.engine.types import Mode, ParticipantType, Persona, Position, Timing
from backend.app.llm.registry import selectable_debaters
from backend.app.models import Debate, Side
from backend.app.services import flags
from backend.app.services.outbox import Outbox

log = get_logger("provok.featured")
QUESTIONS_PATH = APP_DIR / "services" / "featured_questions.json"


def load_questions(path: Path = QUESTIONS_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


async def create_featured(count: int = 1, *, items: list[dict] | None = None,
                          source_post_id: uuid.UUID | None = None) -> list[str]:
    """AI-vs-AI featured debates, from the question bank (or the given `items`, e.g. today's Daily Debate)."""
    if not await flags.is_enabled(flags.AI_DEBATES):
        return []
    models = await selectable_debaters()
    if not models:
        log.warning("featured_no_models")
        return []
    async with session_scope() as db:
        used = set((await db.scalars(select(Debate.question).where(Debate.is_featured.is_(True)))).all())
    if items is not None:
        pool = list(items)
    else:
        pool = [q for q in load_questions() if q["question"] not in used] or load_questions()
        random.shuffle(pool)
    created: list[str] = []
    personas = list(Persona)
    for item in pool[:count]:
        a = random.choice(models)
        b = random.choice([m for m in models if m.key != a.key] or models)
        pa, pb = random.sample(personas, 2)
        outbox = Outbox()
        async with session_scope() as db:
            debate = Debate(question=item["question"], topic_category=item.get("category", "other"), mode=Mode.AVA.value,
                            timing=Timing.LIVE.value, status="opening", is_featured=True, word_limit=180,
                            source_post_id=source_post_id)
            db.add(debate)
            await db.flush()
            sides = {}
            for pos, model, persona in ((Position.FOR, a, pa), (Position.AGAINST, b, pb)):
                db.add(Side(debate_id=debate.id, position=pos.value, participant_type=ParticipantType.SWARM.value,
                            swarm_config={"model_key": model.key, "persona": persona.value}))
                sides[pos] = tx.SideState(pos, ParticipantType.SWARM)
            await db.flush()
            await db.refresh(debate, ["sides"])
            initial = tx.initial_transition(mode=Mode.AVA, timing=Timing.LIVE, created_by=None, sides=sides,
                                            word_limit=180, config=engine_config(Timing.LIVE), now=utcnow())
            outbox.extend((await apply_initial(db, debate, initial)).outbox)
            created.append(str(debate.id))
        await outbox.flush()
        log.info("featured_created", debate_id=created[-1], for_model=a.key, against_model=b.key)
    return created
