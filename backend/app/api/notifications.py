"""PROVOK — Notifications API routes."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def get_notifications():
    return {"message": "Notifications — Phase 8"}
