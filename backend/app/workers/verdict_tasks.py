"""PROVOK — Verdict background tasks."""
import asyncio
from backend.app.workers.celery_app import celery_app
from backend.app.verdict.generator import generate_verdict_async

@celery_app.task(name="verdict.generate", bind=True, max_retries=2)
def generate_verdict(self, debate_id: str):
    """Generate verdict after debate completion. Phase 7."""
    asyncio.run(generate_verdict_async(debate_id))
