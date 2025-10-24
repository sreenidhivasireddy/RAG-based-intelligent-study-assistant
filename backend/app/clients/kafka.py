"""
Kafka producer client for sending asynchronous tasks to Kafka topics.
Used to trigger document parsing and vectorization pipelines.
"""

from kafka import KafkaProducer
import json
import os

# Load Kafka configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# Initialize global Kafka producer
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)

def send_message(topic: str, message: dict):
    """
    Send a JSON message to the specified Kafka topic.

    Args:
        topic (str): Kafka topic name
        message (dict): Message payload
    """
    try:
        producer.send(topic, message)
        producer.flush()
        print(f"✅ Kafka message sent to topic [{topic}]: {message}")
    except Exception as e:
        print(f"❌ Failed to send message to Kafka: {e}")
