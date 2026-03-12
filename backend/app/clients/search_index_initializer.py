"""
Azure AI Search index initializer.

Note: Azure AI Search indexes must be created via Azure Portal or the SDK.
This module provides compatibility and helper functions.
"""

import json
import os
from pathlib import Path
from app.clients.azure_search import get_azure_search_config
from app.utils.logging import get_logger

logger = get_logger(__name__)


def ensure_index(index_name: str = None) -> bool:
    """
    Verify Azure AI Search index exists.
    
    Note: Azure Search indexes cannot be auto-created via SearchClient.
    To create an index:
    1. Use Azure Portal (https://portal.azure.com)
    2. Or use SearchIndexClient from azure-search-documents SDK
    
    Args:
        index_name: index name (optional, uses config if not provided)
    
    Returns:
        bool: True if configuration is valid
        
    Raises:
        ValueError: if Azure Search configuration is invalid
    """
    try:
        config = get_azure_search_config()
        index_name = index_name or config["index_name"]
        
        logger.info(f"✓ Azure AI Search configuration verified")
        logger.info(f"  Endpoint: {config['endpoint']}")
        logger.info(f"  Index: {index_name}")
        logger.info(f"  Note: Ensure index exists in Azure Portal")
        
        return True
        
    except ValueError as e:
        logger.error(f"✗ Azure AI Search configuration invalid: {e}")
        raise


def create_index_via_sdk(client, index_name: str, fields_config: dict) -> bool:
    """
    Helper function to create Azure Search index via SDK.
    
    Example usage:
    ```python
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import SearchIndex
    from azure.core.credentials import AzureKeyCredential
    
    client = SearchIndexClient(endpoint, AzureKeyCredential(key))
    config = ESIndexConfig.get_full_index_config()
    from_dict = SearchIndex.from_dict({"name": "my-index", **config})
    create_index_via_sdk(client, "my-index", config)
    ```
    
    Args:
        client: SearchIndexClient instance
        index_name: Name for the index
        fields_config: Index configuration dict with fields
    
    Returns:
        bool: True if index created successfully
    """
    try:
        from azure.search.documents.indexes.models import SearchIndex
        
        index = SearchIndex(name=index_name, **fields_config)
        result = client.create_index(index)
        
        logger.info(f"✓ Index '{index_name}' created successfully via SDK")
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to create index via SDK: {e}")
        raise


def delete_index_via_sdk(client, index_name: str) -> bool:
    """
    Delete an Azure Search index via SDK.
    
    Args:
        client: SearchIndexClient instance
        index_name: Name of the index to delete
    
    Returns:
        bool: True if index deleted successfully
    """
    try:
        client.delete_index(index_name)
        logger.info(f"✓ Index '{index_name}' deleted successfully via SDK")
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to delete index via SDK: {e}")
        raise


def _auto_initialize():
    """auto initialize index verification (optional)"""
    try:
        ensure_index()
    except Exception as e:
        logger.warning(f"Auto-verification of index configuration failed: {e}")

# if you need to auto initialize when importing, uncomment the following line
# _auto_initialize()
