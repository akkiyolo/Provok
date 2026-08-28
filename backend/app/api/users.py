from sqlalchemy import select, func, or_
from backend.app.database.core import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.models.user import User
from backend.app.models.social import Follow, FollowType
from backend.app.models.debate import Participant
from fastapi import APIRouter, Depends, HTTPException
from backend.app.dependencies import get_current_user

router = APIRouter()

@router.get("/{username}")
async def get_user_profile(username: str, db: AsyncSession = Depends(get_db)):
    # 1. Fetch user
    stmt = select(User).where(func.lower(User.username) == username.lower())
    user = await db.scalar(stmt)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # 2. Stats
    # Followers
    followers_count = await db.scalar(select(func.count()).select_from(Follow).where(Follow.target_user_id == user.id))
    # Following
    following_count = await db.scalar(select(func.count()).select_from(Follow).where(Follow.follower_id == user.id, Follow.follow_type == FollowType.USER))
    # Debates participated
    debates_count = await db.scalar(select(func.count()).select_from(Participant).where(Participant.user_id == user.id))
    
    avatar_url = user.avatar_url
    if avatar_url and not avatar_url.startswith('http'):
        from backend.app.storage.s3 import storage_manager
        avatar_url = storage_manager.generate_presigned_url(avatar_url)

    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "bio": user.bio or "No bio provided.",
        "avatar_url": avatar_url,
        "stats": {
            "followers": followers_count or 0,
            "following": following_count or 0,
            "debates_participated": debates_count or 0,
            "debates_won": 0  # Placeholder, requires complex verdict logic
        }
    }

@router.post("/{username}/follow")
async def follow_user(username: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    stmt = select(User).where(func.lower(User.username) == username.lower())
    target_user = await db.scalar(stmt)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")
        
    existing = await db.scalar(select(Follow).where(Follow.follower_id == current_user.id, Follow.target_user_id == target_user.id))
    if existing:
        db.delete(existing)
        await db.commit()
        return {"status": "unfollowed"}
    else:
        new_follow = Follow(follower_id=current_user.id, follow_type=FollowType.USER, target_user_id=target_user.id)
        db.add(new_follow)
        await db.commit()
        return {"status": "followed"}

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
    
    presigned_url = storage_manager.generate_presigned_url(url)
    
    return {"message": "Avatar updated successfully", "avatar_url": presigned_url}
