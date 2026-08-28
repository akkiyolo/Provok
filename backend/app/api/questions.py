"""PROVOK — Questions API routes."""
from fastapi import APIRouter

router = APIRouter()


@router.post("/")
async def create_question():
    return {"message": "Create question — Phase 3"}


@router.get("/{question_id}")
async def get_question(question_id: str):
    return {"message": f"Question {question_id} — Phase 3"}
