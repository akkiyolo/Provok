"""PROVOK — Embedding background tasks."""
from backend.app.workers.celery_app import celery_app


@celery_app.task(name="embedding.process_file", bind=True, max_retries=2)
def process_file_embeddings(self, file_id: str):
    """Extract text, chunk, and embed uploaded files. Phase 5."""
    pass
