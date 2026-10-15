"""all AI models on Amazon Bedrock: switch off Groq, Gemini and direct Anthropic

Rows stay (past debates, LLM call logs and the model leaderboard still name them); they're just disabled.
GPT-OSS 120B, which debated through Groq, now debates through Bedrock, and unfinished debates move over.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-15 19:30:00+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same model (or family) on Bedrock, for debates that are still running.
MOVES = {"groq_gpt_oss": "bedrock_gpt_oss", "groq_qwen": "bedrock_qwen", "gemini_flash": "bedrock_qwen"}


def upgrade() -> None:
    op.execute("UPDATE model_registry SET enabled = false WHERE litellm_id NOT LIKE 'bedrock/%'")
    op.execute("UPDATE model_registry SET tier = 'standard', selectable = true, display_name = 'GPT-OSS 120B' "
               "WHERE key = 'bedrock_gpt_oss'")
    for old, new in MOVES.items():
        op.execute(
            f"UPDATE sides SET swarm_config = jsonb_set(swarm_config, '{{model_key}}', '\"{new}\"') "
            f"WHERE swarm_config->>'model_key' = '{old}' AND debate_id IN "
            "(SELECT id FROM debates WHERE status NOT IN ('completed', 'abandoned', 'cancelled'))"
            f" AND EXISTS (SELECT 1 FROM model_registry WHERE key = '{new}')"
        )


def downgrade() -> None:
    # Re-enabling providers is an admin decision (keys, budget): flip them back in /admin → Models.
    op.execute("UPDATE model_registry SET tier = 'utility', selectable = false, display_name = 'GPT-OSS 120B (Bedrock)' "
               "WHERE key = 'bedrock_gpt_oss'")
