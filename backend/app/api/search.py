"""PROVOK — Search API routes."""
from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.core import get_db
from backend.app.models.debate import Debate, Question, DebateStatus
from backend.app.models.user import User

router = APIRouter()


@router.get("/")
async def search(
    q: str = Query(..., min_length=1, max_length=100),
    type: Optional[str] = Query(None, pattern="^(debates|users|all)$"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    """
    Search across debates, questions, and users using ILIKE.
    Returns categorized results.
    """
    if not q.strip():
        return {"results": [], "query": q, "total": 0}

    search_term = f"%{q.strip()}%"
    results = []

    # Search debates (via their Question text and debate title)
    if type in (None, "all", "debates"):
        debate_query = (
            select(Debate, Question)
            .join(Question, Debate.question_id == Question.id)
            .where(
                or_(
                    func.lower(Question.text).like(func.lower(search_term)),
                )
            )
            .where(Debate.visibility == "PUBLIC")
            .order_by(Debate.created_at.desc())
            .limit(limit)
        )
        debate_rows = await db.execute(debate_query)
        for debate, question in debate_rows:
            results.append({
                "type": "debate",
                "id": str(debate.id),
                "title": question.text,
                "status": debate.status.value if hasattr(debate.status, 'value') else str(debate.status),
                "mode": debate.mode.value if hasattr(debate.mode, 'value') else str(debate.mode),
                "current_round": debate.current_round,
                "viewer_count": debate.viewer_count,
                "url": f"/debate/{debate.id}",
                "created_at": debate.created_at.isoformat() if debate.created_at else None,
            })

    # Search users
    if type in (None, "all", "users"):
        user_query = (
            select(User)
            .where(
                or_(
                    func.lower(User.username).like(func.lower(search_term)),
                    func.lower(User.display_name).like(func.lower(search_term)),
                )
            )
            .limit(limit)
        )
        users = await db.scalars(user_query)
        for user in users:
            results.append({
                "type": "user",
                "id": str(user.id),
                "username": user.username,
                "display_name": user.display_name or user.username,
                "avatar_url": user.avatar_url,
                "url": f"/profile/{user.username}",
            })

    return {
        "results": results,
        "query": q,
        "total": len(results),
    }
