"""
Redis connection test
Tests Redis connectivity and basic operations
"""
import os
import sys
import redis
import logging
from pathlib import Path
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load .env from project root
project_root = Path(__file__).parent.parent.parent
env_path = project_root / '.env'
if env_path.exists():
    load_dotenv(env_path)
    logger.info(f"Loaded .env from: {env_path}")
else:
    logger.warning(f".env not found at: {env_path}")

# Get Redis configuration from environment
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

try:
    # Test connection
    logger.info(f"Testing Redis connection: {REDIS_HOST}:{REDIS_PORT}")
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, socket_connect_timeout=2)
    
    # Test ping
    r.ping()
    logger.info("✅ Redis ping successful")
    
    # Test basic operations
    r.set("test_key", "hello redis")
    val = r.get("test_key").decode()
    assert val == "hello redis", f"Expected 'hello redis', got '{val}'"
    logger.info(f"✅ Redis read/write test passed, value = {val}")
    
    # Cleanup
    r.delete("test_key")
    logger.info("✅ Redis connection test completed successfully")
    
except redis.ConnectionError as e:
    logger.error(f"❌ Redis connection failed: {e}")
    logger.error(f"   Make sure Redis is running on {REDIS_HOST}:{REDIS_PORT}")
    logger.error(f"   Start Redis: brew services start redis")
    sys.exit(1)
except Exception as e:
    logger.error(f"❌ Redis test failed: {e}")
    sys.exit(1)
