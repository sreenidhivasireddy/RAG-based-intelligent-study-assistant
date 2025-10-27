"""
Kafka client initialization.
Provides a reusable producer instance for sending async messages.
"""

import os
from kafka import KafkaProducer
from dotenv import load_dotenv

from app.utils.logging import get_logger

# Load environment variables
load_dotenv()

# Initialize logger
logger = get_logger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

try:
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: str(v).encode("utf-8")
    )
    logger.info(f"Connected to Kafka successfully ({KAFKA_BOOTSTRAP_SERVERS})")
except Exception as e:
    logger.error(f"Failed to connect to Kafka: {e}")
    producer = None
