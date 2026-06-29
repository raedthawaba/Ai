import redis
import logging
import asyncio
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class RedisStreamsClient:
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.redis_client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        logger.info(f"RedisStreamsClient initialized for {host}:{port}/{db}")

    async def add_message(self, stream_name: str, message_data: Dict[str, Any]) -> str:
        """Adds a message to a Redis Stream."""
        try:
            message_id = self.redis_client.xadd(stream_name, message_data)
            logger.info(f"Added message to stream \'{stream_name}\' with ID: {message_id}")
            return message_id
        except Exception as e:
            logger.error(f"Error adding message to Redis Stream \'{stream_name}\': {e}")
            raise

    async def read_messages(self, stream_name: str, consumer_group: str, consumer_name: str, count: int = 10, block: int = 5000) -> List[Dict[str, Any]]:
        """Reads messages from a Redis Stream using a consumer group."""
        try:
            # Ensure consumer group exists
            try:
                self.redis_client.xgroup_create(stream_name, consumer_group, id=">", mkstream=True)
            except redis.exceptions.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise
            
            messages = self.redis_client.xreadgroup(
                consumer_group, consumer_name, {stream_name: ">"}, count=count, block=block
            )
            
            processed_messages = []
            for stream, msgs in messages:
                for msg_id, msg_data in msgs:
                    processed_messages.append({"id": msg_id, "data": msg_data})
                    # Acknowledge the message
                    self.redis_client.xack(stream_name, consumer_group, msg_id)
            
            logger.info(f"Read {len(processed_messages)} messages from stream \'{stream_name}\' for consumer \'{consumer_name}\'")
            return processed_messages
        except Exception as e:
            logger.error(f"Error reading messages from Redis Stream \'{stream_name}\': {e}")
            raise

print("Redis Streams integration example created.")
