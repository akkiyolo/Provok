import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from backend.app.websockets.manager import manager
from backend.app.dependencies import get_current_user
from backend.app.models.user import User

router = APIRouter()

@router.websocket("/{debate_id}")
async def debate_websocket(websocket: WebSocket, debate_id: str):
    await manager.connect(websocket, debate_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
                continue

            try:
                msg = json.loads(data)
                msg_type = msg.get("type")
                if msg_type == "ping":
                    await websocket.send_text("pong")
                elif msg_type == "reaction":
                    emoji = msg.get("emoji", "🔥")
                    side = msg.get("side", "")
                    await manager.publish_event(
                        debate_id=debate_id,
                        event_type="audience_reaction",
                        payload={"emoji": emoji, "side": side}
                    )
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket, debate_id)
