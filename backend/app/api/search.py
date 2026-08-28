"""PROVOK — Search API routes."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def search(q: str = ""):
    return {"message": f"Search for '{q}' — Phase 8"}
