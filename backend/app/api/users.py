"""PROVOK — Users API routes."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/{username}")
async def get_user_profile(username: str):
    return {"message": f"Profile for {username} — Phase 8"}


@router.post("/{user_id}/follow")
async def follow_user(user_id: str):
    return {"message": "Follow endpoint — Phase 8"}

from fastapi import UploadFile, File, Depends, HTTPException
from backend.app.dependencies import get_current_user
from backend.app.models.user import User
from backend.app.storage.s3 import storage_manager
from backend.app.database.core import get_db
from sqlalchemy.ext.asyncio import AsyncSession

@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload a new avatar to S3 and update the user's profile."""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
        
    # Read file content safely for synchronous boto3 upload
    import asyncio
    
    # Run the blocking upload in a separate thread to prevent event loop blocking
    url = await asyncio.to_thread(
        storage_manager.upload_file,
        file.file,
        file.filename,
        file.content_type
    )
    
    if not url:
        raise HTTPException(status_code=500, detail="Failed to upload image to S3")
        
    # Update user in DB
    current_user.avatar_url = url
    db.add(current_user)
    await db.commit()
    
    return {"message": "Avatar updated successfully", "avatar_url": url}
