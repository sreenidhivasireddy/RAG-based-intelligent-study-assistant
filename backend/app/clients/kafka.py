"""
Kafka client initialization.
Provides producer and consumer factory methods.
"""

import os
import json
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError
from dotenv import load_dotenv
from typing import Optional
from app.utils.logging import get_logger

# Load environment variables
load_dotenv()

# Initialize logger
logger = get_logger(__name__)

# Kafka configuration from environment
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092").split(",")
KAFKA_FILE_PROCESSING_TOPIC = os.getenv("KAFKA_FILE_PROCESSING_TOPIC", "file-processing-topic1")
KAFKA_DLT_TOPIC = os.getenv("KAFKA_DLT_TOPIC", "file-processing-dlt")
KAFKA_CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "file-processing-group")


class KafkaConfig:
    """Kafka configuration and factory class"""
    
    # Producer configuration (matching Java settings)
    PRODUCER_CONFIG = {
        'bootstrap_servers': KAFKA_BOOTSTRAP_SERVERS, # clarify where is the Kafka Broker
        'value_serializer': lambda v: json.dumps(v).encode('utf-8'),  # serialize the value to JSON
        'key_serializer': lambda k: k.encode('utf-8') if k else None, #control the key serialization(partition key)
        'acks': 'all',  # waiting for all replicas to confirm the message
        'retries': 3,   # retry 3 times if the message is not acknowledged
        # 'enable_idempotence': True,  # kafka-python not support it
        'max_in_flight_requests_per_connection': 5, # 5 requests per connection
        'compression_type': 'gzip',  # compression type
        'linger_ms': 10,  # batch send delay
        'request_timeout_ms': 30000,
    }
    
    # Consumer configuration
    CONSUMER_CONFIG = {
        'bootstrap_servers': KAFKA_BOOTSTRAP_SERVERS,
        'group_id': KAFKA_CONSUMER_GROUP, # identify which consumer group to consume the message
        'auto_offset_reset': 'latest',  # start from the latest message
        'enable_auto_commit': True, # commit the offset to the broker automatically
        'auto_commit_interval_ms': 1000,
        'value_deserializer': lambda v: json.loads(v.decode('utf-8')), # deserialize bytes to python object
        'key_deserializer': lambda k: k.decode('utf-8') if k else None, # bytes to string
        'max_poll_records': 10, # max number of records to fetch in one poll
        'session_timeout_ms': 30000,
    }
    
    _producer_instance: Optional[KafkaProducer] = None
    
    @classmethod
    def get_producer(cls, force_new: bool = False) -> KafkaProducer:
        """
        Get or create a Kafka producer instance.
        
        Args:
            force_new: If True, create a new producer instead of reusing
            
        Returns:
            KafkaProducer instance
        """
        if force_new or cls._producer_instance is None:
            try:
                cls._producer_instance = KafkaProducer(**cls.PRODUCER_CONFIG)
                logger.info(
                    f"✓ Kafka Producer connected: {KAFKA_BOOTSTRAP_SERVERS}"
                )
            except KafkaError as e:
                logger.error(f"✗ Failed to connect to Kafka: {e}")
                raise
        
        return cls._producer_instance
    
    @classmethod
    def create_consumer(cls, topics: list) -> KafkaConsumer:
        """
        Create a new Kafka consumer instance.
        
        Args:
            topics: List of topics to subscribe to
            
        Returns:
            KafkaConsumer instance
        """
        try:
            consumer = KafkaConsumer(*topics, **cls.CONSUMER_CONFIG)
            logger.info(
                f"✓ Kafka Consumer created: topics={topics}, "
                f"group={KAFKA_CONSUMER_GROUP}"
            )
            return consumer
        except KafkaError as e:
            logger.error(f"✗ Failed to create Kafka consumer: {e}")
            raise
    
    @classmethod
    def close_producer(cls):
        """Close the global producer instance"""
        if cls._producer_instance:
            cls._producer_instance.flush()
            cls._producer_instance.close()
            cls._producer_instance = None
            logger.info("Kafka Producer closed")
    
    @staticmethod
    def get_file_processing_topic() -> str:
        """Get file processing topic name"""
        return KAFKA_FILE_PROCESSING_TOPIC
    
    @staticmethod
    def get_dlt_topic() -> str:
        """Get dead letter topic name"""
        return KAFKA_DLT_TOPIC


# Optional: test Kafka connection manually when needed
def test_kafka_connection():
    """Test Kafka connection (call manually if needed)"""
    try:
        producer = KafkaConfig.get_producer()
        logger.info("Kafka connection test passed ✓")
        return True
    except Exception as e:
        logger.error(f"Kafka connection test failed ✗: {e}")
        return False