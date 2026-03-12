# backend/app/clients/azure_search.py
"""
Azure AI Search client factory.
Provides a singleton SearchClient + a getter.

Used by:
- app.api.search
- app.consumer.run_consumer
"""

import os
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

from app.utils.logging import get_logger

logger = get_logger(__name__)

load_dotenv()

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "").strip()
AZURE_SEARCH_ADMIN_KEY = os.getenv("AZURE_SEARCH_ADMIN_KEY", "").strip()
AZURE_SEARCH_INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX", "").strip()

azure_search_client: SearchClient | None = None


def get_azure_search_client() -> SearchClient:
    """
    Return a singleton SearchClient.
    """
    global azure_search_client

    if azure_search_client is not None:
        return azure_search_client

    if not AZURE_SEARCH_ENDPOINT or not AZURE_SEARCH_ADMIN_KEY or not AZURE_SEARCH_INDEX_NAME:
        raise RuntimeError(
            "Azure AI Search env vars missing. Please set in backend/.env:\n"
            "AZURE_SEARCH_ENDPOINT=https://<service>.search.windows.net\n"
            "AZURE_SEARCH_ADMIN_KEY=<admin_key>\n"
            "AZURE_SEARCH_INDEX_NAME=<index_name>"
        )

    azure_search_client = SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=AZURE_SEARCH_INDEX_NAME,
        credential=AzureKeyCredential(AZURE_SEARCH_ADMIN_KEY),
    )

    logger.info("✓ Azure AI Search client initialized")
    logger.info(f"  Endpoint: {AZURE_SEARCH_ENDPOINT}")
    logger.info(f"  Index: {AZURE_SEARCH_INDEX_NAME}")

    return azure_search_client


def get_azure_search_config() -> dict:
    """
    Return Azure Search configuration as a dict.
    Used by helper modules that need endpoint/index info without
    instantiating the full client.
    """
    if not AZURE_SEARCH_ENDPOINT or not AZURE_SEARCH_ADMIN_KEY or not AZURE_SEARCH_INDEX_NAME:
        raise ValueError("Azure AI Search env vars missing: AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_ADMIN_KEY, AZURE_SEARCH_INDEX")

    return {
        "endpoint": AZURE_SEARCH_ENDPOINT,
        "admin_key": AZURE_SEARCH_ADMIN_KEY,
        "index_name": AZURE_SEARCH_INDEX_NAME,
    }