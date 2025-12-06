#!/usr/bin/env python3
"""
Kafka Consumer Startup Script
独立运行的 Kafka Consumer 进程，用于处理文件解析和向量化任务

运行方式：
    python -m app.consumer.run_consumer

或后台运行：
    nohup python -m app.consumer.run_consumer > logs/consumer.log 2>&1 &
"""

import sys
from pathlib import Path

# 确保能导入 app 模块
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.parse_service import ParseService
from app.services.vectorize_service import VectorizationService
from app.services.es_service import ElasticsearchService
from app.clients.gemini_embedding_client import GeminiEmbeddingClient
from app.consumer.file_processing_consumer import FileProcessingConsumer
import app.clients.elastic as es
from app.utils.logging import get_logger

logger = get_logger(__name__)


def main():
    """
    main function to start the Kafka Consumer
    """
    logger.info("=" * 80)
    logger.info("🚀 Starting File Processing Kafka Consumer")
    logger.info("=" * 80)
    
    consumer = None
    
    try:
        # 1. initialize the parse service
        logger.info("Initializing parse service...")
        parse_service = ParseService(chunk_size=500)
        
        # 3. initialize the embedding client
        logger.info("Initializing Gemini embedding client...")
        if not GeminiEmbeddingClient.is_configured():
            raise RuntimeError(
                "GEMINI_API_KEY is not configured. "
                "Please set the GEMINI_API_KEY environment variable in .env file."
            )
        embedding_client = GeminiEmbeddingClient()
        
        # 4. initialize the Elasticsearch service
        logger.info("Initializing Elasticsearch service...")
        es_client = es.get_client()
        es_service = ElasticsearchService(es_client)
        
        # 5. 初始化向量化服务
        logger.info("Initializing vectorization service...")
        vectorization_service = VectorizationService(
            embedding_client=embedding_client,
            elasticsearch_service=es_service
        )
        
        # 6. create the Kafka Consumer
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
        
        # 7. start the consumption loop (blocking run)
        consumer.start_consuming()
        
    except KeyboardInterrupt:
        logger.info("\n" + "=" * 80)
        logger.info("Received stop signal (Ctrl+C), shutting down gracefully...")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Fatal error occurred: {e}", exc_info=True)
        raise
        
    finally:
        # cleanup the resources
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

