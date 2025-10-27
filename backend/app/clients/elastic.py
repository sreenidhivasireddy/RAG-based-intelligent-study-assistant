"""
Elasticsearch client initialization.
Provides a reusable Elasticsearch connection for search and vector storage.
"""

import os
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

from app.utils.logging import get_logger

# Load environment variables
load_dotenv()

# Initialize logger
logger = get_logger(__name__)

ES_HOST = os.getenv("ES_HOST", "localhost")
ES_PORT = int(os.getenv("ES_PORT", 9200))
ES_SCHEME = os.getenv("ES_SCHEME", "http")
ES_USERNAME = os.getenv("ES_USERNAME")
ES_PASSWORD = os.getenv("ES_PASSWORD")

# Build connection URL
ES_URL = f"{ES_SCHEME}://{ES_HOST}:{ES_PORT}"

try:
    if ES_USERNAME and ES_PASSWORD:
        es_client = Elasticsearch(
            [ES_URL],
            basic_auth=(ES_USERNAME, ES_PASSWORD),
            verify_certs=False
        )
    else:
        es_client = Elasticsearch([ES_URL], verify_certs=False)

    # Test connection
    if es_client.ping():
        logger.info(f"Connected to Elasticsearch successfully ({ES_URL})")
    else:
        logger.warning(f"Elasticsearch connection established, but ping failed ({ES_URL})")
except Exception as e:
    logger.error(f"Failed to connect to Elasticsearch: {e}")
    es_client = None
