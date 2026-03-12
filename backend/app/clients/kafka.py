"""
Kafka client initialization.
Provides producer and consumer factory methods.
"""

import os
import json
from typing import Optional
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError
from dotenv import load_dotenv
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Load environment variables (prefer backend/.env)
load_dotenv()

def _parse_bootstrap_servers() -> list[str]:
    raw = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092")
    return [s.strip() for s in raw.split(",") if s.strip()]

KAFKA_BOOTSTRAP_SERVERS = _parse_bootstrap_servers()
KAFKA_FILE_PROCESSING_TOPIC = os.getenv("KAFKA_FILE_PROCESSING_TOPIC", "file-processing-topic1")
KAFKA_DLT_TOPIC = os.getenv("KAFKA_DLT_TOPIC", "file-processing-dlt")
KAFKA_CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "file-processing-group")
KAFKA_SECURITY_PROTOCOL = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")  # default

class KafkaConfig:
    """Kafka configuration and factory class"""

    PRODUCER_CONFIG = {
        "bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS,
        "security_protocol": KAFKA_SECURITY_PROTOCOL,
        "value_serializer": lambda v: json.dumps(v).encode("utf-8"),
        "key_serializer": lambda k: str(k).encode("utf-8") if k else None,
        "acks": "all",
        "retries": 3,
        "linger_ms": 10,
        "compression_type": "gzip",
        "request_timeout_ms": 30000,
        "api_version_auto_timeout_ms": 30000,
    }

    CONSUMER_CONFIG = {
        "bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS,
        "security_protocol": KAFKA_SECURITY_PROTOCOL,
        "group_id": KAFKA_CONSUMER_GROUP,
        "auto_offset_reset": "latest",
        "enable_auto_commit": True,
        "auto_commit_interval_ms": 1000,
        "value_deserializer": lambda v: json.loads(v.decode("utf-8")),
        "key_deserializer": lambda k: k.decode("utf-8") if k else None,
        "max_poll_records": 10,

        "session_timeout_ms": 30000,
        "heartbeat_interval_ms": 10000,

        "request_timeout_ms": 60000,          # ✅ MUST be > session_timeout_ms
        "api_version_auto_timeout_ms": 30000,
    }

    _producer_instance: Optional[KafkaProducer] = None

    @classmethod
    def get_producer(cls, force_new: bool = False) -> KafkaProducer:
        if force_new or cls._producer_instance is None:
            try:
                logger.info(f"Connecting Kafka Producer to: {KAFKA_BOOTSTRAP_SERVERS}")
                cls._producer_instance = KafkaProducer(**cls.PRODUCER_CONFIG)
                logger.info("✓ Kafka Producer connected")
            except KafkaError as e:
                logger.error(f"✗ Failed to connect Kafka Producer: {e}")
                raise
        return cls._producer_instance

    @classmethod
    def create_consumer(cls, topics: list) -> KafkaConsumer:
        try:
            logger.info(f"Connecting Kafka Consumer to: {KAFKA_BOOTSTRAP_SERVERS}")
            consumer = KafkaConsumer(*topics, **cls.CONSUMER_CONFIG)
            logger.info(f"✓ Kafka Consumer created: topics={topics}, group={KAFKA_CONSUMER_GROUP}")
            return consumer
        except KafkaError as e:
            logger.error(f"✗ Failed to create Kafka consumer: {e}")
            raise

    @classmethod
    def close_producer(cls):
        if cls._producer_instance:
            cls._producer_instance.flush()
            cls._producer_instance.close()
            cls._producer_instance = None
            logger.info("Kafka Producer closed")

    @staticmethod
    def get_file_processing_topic() -> str:
        return KAFKA_FILE_PROCESSING_TOPIC

    @staticmethod
    def get_dlt_topic() -> str:
        return KAFKA_DLT_TOPIC