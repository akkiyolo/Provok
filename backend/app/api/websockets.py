from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from backend.app.websockets.manager import manager
from backend.app.dependencies import get_current_user
from backend.app.models.user import User

router = APIRouter()

@router.websocket("/{debate_id}")
async def debate_websocket(websocket: WebSocket, debate_id: str):
    # In a real app, we'd validate the token here. For simplicity in websockets, we might pass it in query string.
    # We will just accept the connection for the room.
    await manager.connect(websocket, debate_id)
    try:
        while True:
            # We don't expect much from the client directly over WS,
            # mostly they use REST APIs to submit actions, and listen here for updates.
            # But we can handle pings/presence here.
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, debate_id)
