"""
Redis Repository - handles temporary cache operations and updates in streamlit.
"""

import json
from typing import List
from app.schemas.message import Message
from app.clients.redis import redis_client

class RedisRepository:
    def __init__(self, client=None):
        if client is None:
            if redis_client is None:
                raise RuntimeError("Redis client not initialized")
            client = redis_client
        self.client = client


    def get_conversation_history(self, conversation_id: str) -> List[Message]:
        json_str = self.client.get(f"conversation:{conversation_id}")
        if not json_str:
            return []
        try:
            data = json.loads(json_str)
            return [Message(**item) for item in data]
        except (json.JSONDecodeError, TypeError) as exc:
            raise RuntimeError("Failed to parse conversation history") from exc

    def save_conversation_history(
        self, conversation_id: str, messages: List[Message], ttl_days: int = 7
    ) -> None:
        payload = json.dumps([msg.__dict__ for msg in messages], ensure_ascii=False)
        # set the expiration time (seconds)
        self.client.setex(
            f"conversation:{conversation_id}",
            ttl_days * 24 * 60 * 60,
            payload,
        )