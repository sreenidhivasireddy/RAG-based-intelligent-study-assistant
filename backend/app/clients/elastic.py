"""
Elasticsearch client initialization.

Provides a reusable Elasticsearch connection for search and vector storage.
"""

import os
from elasticsearch import Elasticsearch
from dotenv import load_dotenv
import urllib3
from app.utils.logging import get_logger

# Load environment variables
load_dotenv()

# Initialize logger
logger = get_logger(__name__)

# Configuration
ES_HOST = os.getenv("ES_HOST", "localhost")
ES_PORT = int(os.getenv("ES_PORT", 9200))
ES_SCHEME = os.getenv("ES_SCHEME", "https")
ES_USERNAME = os.getenv("ES_USERNAME")
ES_PASSWORD = os.getenv("ES_PASSWORD")
ES_URL = f"{ES_SCHEME}://{ES_HOST}:{ES_PORT}"
ES_INDEX = os.getenv("ES_INDEX", "knowledge_base")

# single instance global client instance (same style as MinIO)
es_client = None

try:
    # disable SSL warnings
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # create global singleton client
    es_client = Elasticsearch(
        hosts=[{"host": ES_HOST, "port": ES_PORT, "scheme": ES_SCHEME}],
        basic_auth=(ES_USERNAME, ES_PASSWORD),
        verify_certs=False,
        ssl_show_warn=False,
        request_timeout=30,
    )
    
    # test connection
    if es_client.ping():
        logger.info(f"Elasticsearch connected ({ES_URL})")
    else:
        logger.warning(f"Elasticsearch ping failed ({ES_URL})")
        es_client = None
        
except Exception as e:
    logger.error(f"Failed to initialize Elasticsearch client: {e}")
    es_client = None


def get_client() -> Elasticsearch:
    """
    get Elasticsearch client
    
    Returns:
        Elasticsearch client instance
        
    Raises:
        RuntimeError: if ES is not initialized
    """
    if es_client is None:
        raise RuntimeError("Elasticsearch client not initialized")
    return es_client