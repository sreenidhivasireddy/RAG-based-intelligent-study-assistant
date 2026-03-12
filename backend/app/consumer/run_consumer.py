#!/usr/bin/env python3
"""
Kafka Consumer Startup Script
Standalone Kafka consumer process for file parsing and vectorization tasks

Run with:
    python -m app.consumer.run_consumer
"""

import sys
import os
from pathlib import Path

# -------------------------------------------------------------------
# ✅ Ensure imports work
# -------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# -------------------------------------------------------------------
# ✅ Load .env explicitly (CRITICAL on Windows)
# -------------------------------------------------------------------
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../backend
ENV_PATH = PROJECT_ROOT / ".env"

if load_dotenv:
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=str(ENV_PATH), override=True)
    else:
        load_dotenv(override=True)

from app.services.parse_service import ParseService
from app.services.vectorize_service import VectorizationService
from app.services.azure_search_service import AzureSearchService
from app.clients.azure_openai_embedding_client import AzureOpenAIEmbeddingClient
from app.consumer.file_processing_consumer import FileProcessingConsumer

# ✅ IMPORTANT: azure_search must be the CLIENT FACTORY module
import app.clients.azure_search as azure_search

from app.utils.logging import get_logger

logger = get_logger(__name__)


def main():
    logger.info("=" * 80)
    logger.info("🚀 Starting File Processing Kafka Consumer")
    logger.info("=" * 80)

    kafka_bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "").strip()
    kafka_topic = os.getenv("KAFKA_FILE_PROCESSING_TOPIC", "").strip()

    logger.info(f"ENV: KAFKA_BOOTSTRAP_SERVERS      = {kafka_bootstrap or '(missing)'}")
    logger.info(f"ENV: KAFKA_FILE_PROCESSING_TOPIC = {kafka_topic or '(missing)'}")
    logger.info(f"ENV loaded from: {ENV_PATH if ENV_PATH.exists() else '(default dotenv search)'}")

    if not kafka_bootstrap:
        raise RuntimeError(
            "KAFKA_BOOTSTRAP_SERVERS is missing. "
            "Add it to backend/.env like: KAFKA_BOOTSTRAP_SERVERS=127.0.0.1:29092"
        )

    consumer = None

    try:
        # 1) Parse service
        logger.info("Initializing parse service...")
        parse_service = ParseService(chunk_size=500)

        # 2) Embeddings client
        logger.info("Initializing Azure OpenAI embedding client...")
        embedding_client = AzureOpenAIEmbeddingClient()
        if not embedding_client.is_configured():
            raise RuntimeError(
                "AZURE_OPENAI_API_KEY is not configured. Please set it in backend/.env."
            )

        # 3) Azure Search client + service  ✅ THIS IS WHAT YOU ASKED FOR
        logger.info("Initializing Azure AI Search service...")
        search_client = azure_search.get_azure_search_client()
        azure_search_service = AzureSearchService(search_client)

        # 4) Vectorization service
        logger.info("Initializing vectorization service...")
        vectorization_service = VectorizationService(
            embedding_client=embedding_client,
            search_service=azure_search_service
        )

        # 5) Consumer
        logger.info("Creating Kafka Consumer...")
        consumer = FileProcessingConsumer(
            parse_service=parse_service,
            vectorization_service=vectorization_service,
            max_retries=4,
            retry_backoff_seconds=3
        )

        logger.info("=" * 80)
        logger.info("✅ All services initialized successfully")
        logger.info("=" * 80)
        logger.info("Consumer is now listening for messages...")
        logger.info("Press Ctrl+C to stop")
        logger.info("=" * 80)

        consumer.start_consuming()

    except KeyboardInterrupt:
        logger.info("\n" + "=" * 80)
        logger.info("Received stop signal (Ctrl+C), shutting down gracefully...")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Fatal error occurred: {e}", exc_info=True)
        raise

    finally:
        logger.info("Cleaning up resources...")

        if consumer:
            try:
                consumer.close()
                logger.info("✓ Kafka Consumer closed")
            except Exception as e:
                logger.error(f"Error closing consumer: {e}")

        logger.info("=" * 80)
        logger.info("Consumer stopped")
        logger.info("=" * 80)


if __name__ == "__main__":
    main()
