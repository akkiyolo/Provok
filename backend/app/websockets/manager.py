import json
import logging
from typing import Dict, Set
from fastapi import WebSocket
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Maps debate_id to a set of active WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.redis: Redis = None

    async def connect(self, websocket: WebSocket, debate_id: str):
        await websocket.accept()
        if debate_id not in self.active_connections:
            self.active_connections[debate_id] = set()
        self.active_connections[debate_id].add(websocket)
        logger.info(f"Client connected to debate {debate_id}")

    def disconnect(self, websocket: WebSocket, debate_id: str):
        if debate_id in self.active_connections:
            self.active_connections[debate_id].discard(websocket)
            if not self.active_connections[debate_id]:
                del self.active_connections[debate_id]
        logger.info(f"Client disconnected from debate {debate_id}")

    async def broadcast_to_room(self, debate_id: str, message: dict):
        """Broadcast directly to connected websockets on this server instance."""
        if debate_id in self.active_connections:
            for connection in list(self.active_connections[debate_id]):
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending message to {connection}: {e}")
                    self.disconnect(connection, debate_id)

    async def start_redis_listener(self, redis_client: Redis):
        """Start listening to Redis pubsub for messages from other workers/instances."""
        self.redis = redis_client
        pubsub = self.redis.pubsub()
        await pubsub.subscribe("debate_events")
        
        logger.info("Started Redis Pub/Sub listener for websockets")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    debate_id = data.get("debate_id")
                    if debate_id:
                        await self.broadcast_to_room(debate_id, data)
        except Exception as e:
            logger.error(f"Redis Pub/Sub listener error: {e}")

    async def publish_event(self, debate_id: str, event_type: str, payload: dict):
        """Publish an event to Redis so all workers can broadcast it."""
        if not self.redis:
            # No Redis — broadcast directly to local connections only
            await self.broadcast_to_room(debate_id, {
                "debate_id": debate_id,
                "event_type": event_type,
                "payload": payload
            })
            return

        message = {
            "debate_id": debate_id,
            "event_type": event_type,
            "payload": payload
        }
        try:
            await self.redis.publish("debate_events", json.dumps(message))
        except Exception:
            # Redis is down — fall back to local broadcast
            logger.debug("Redis unavailable, broadcasting locally")
            await self.broadcast_to_room(debate_id, message)

manager = ConnectionManager()
