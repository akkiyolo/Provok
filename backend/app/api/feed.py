"""PROVOK — Feed / Discovery API routes."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, desc
from backend.app.database.core import get_db
from backend.app.recommendation.engine import RecommendationEngine
from backend.app.dependencies import get_current_user_optional, get_current_user
from backend.app.models.user import User
from backend.app.models.debate import Debate, DebateStatus

router = APIRouter()


@router.get("/feed")
async def get_feed(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(20, le=100)
):
    """Personalized feed of debates for the logged-in user with Redis graceful fallback."""
    import json
    from backend.app.config import get_settings
    
    settings = get_settings()
    cached_feed = None
    try:
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(settings.redis_cache_url, decode_responses=True)
        cached_feed = await redis_client.get(f"user_feed:{current_user.id}")
        await redis_client.close()
    except Exception:
        pass
    
    if cached_feed:
        return {"debates": json.loads(cached_feed), "source": "cache"}
        
    # Fallback to computation
    engine = RecommendationEngine(db)
    debates = await engine.get_personalized_feed(user_id=current_user.id, limit=limit)
    
    return {"debates": debates, "source": "db"}


@router.get("/live")
async def get_live(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, le=100)
):
    """Get currently live/active debates."""
    query = (
        select(Debate)
        .options(selectinload(Debate.question))
        .where(Debate.status.in_([DebateStatus.LIVE, DebateStatus.READY, DebateStatus.WAITING]))
        .order_by(desc(Debate.viewer_count), desc(Debate.created_at))
        .limit(limit)
    )
    result = await db.scalars(query)
    
    formatted = []
    for d in result:
        formatted.append({
            "id": str(d.id),
            "title": d.question.text if d.question else "Live Topic",
            "status": d.status,
            "mode": d.mode,
            "current_round": d.current_round,
            "viewer_count": d.viewer_count or 0,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        })
    return {"debates": formatted}


@router.get("/explore")
async def get_explore(
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
    limit: int = Query(20, le=100)
):
    """Explore feed of trending and popular debates."""
    engine = RecommendationEngine(db)
    user_id = current_user.id if current_user else None
    debates = await engine.get_explore_feed(user_id=user_id, limit=limit)
    return {"debates": debates}
