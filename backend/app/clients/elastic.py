"""
Elasticsearch client initialization.
Provides a reusable Elasticsearch connection for search and vector storage.
"""

import os
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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
        print(f"✅ Connected to Elasticsearch successfully ({ES_URL})")
    else:
        print(f"⚠️ Elasticsearch connection established, but ping failed ({ES_URL})")
except Exception as e:
    print(f"❌ Failed to connect to Elasticsearch: {e}")
    es_client = None
