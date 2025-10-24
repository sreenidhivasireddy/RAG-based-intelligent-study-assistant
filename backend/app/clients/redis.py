"""
Redis client initialization module.
Provides a global Redis connection for caching and upload progress tracking.

Usage:
    from app.clients.redis_client import redis_client
    redis_client.set("test_key", "hello")
    print(redis_client.get("test_key"))
"""

import os
import redis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

try:
    # Initialize global Redis client
    redis_client = redis.StrictRedis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True  # Automatically decode bytes to strings
    )
    # Test connection
    redis_client.ping()
    print(f"✅ Connected to Redis successfully ({REDIS_HOST}:{REDIS_PORT}, DB={REDIS_DB})")
except Exception as e:
    print(f"❌ Failed to connect to Redis: {e}")
    redis_client = None
