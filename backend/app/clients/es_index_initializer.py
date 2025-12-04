"""
Elasticsearch index initializer.

Ensures the knowledge base index exists with proper mappings.
"""

import json
import os
from pathlib import Path
from app.clients.elastic import get_client, ES_INDEX
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Index configuration
INDEX_NAME = ES_INDEX  # reuse ES configuration index name
MAPPING_FILE = Path(__file__).parent.parent / 'es_mappings' / 'knowledge_base.json'


def ensure_index(index_name: str = None, mapping_file: str = None) -> bool:
    """
    ensure ES index exists, if not create it
    
    Args:
        index_name: index name, default use INDEX_NAME in configuration
        mapping_file: mapping file path, default use MAPPING_FILE
    
    Returns:
        bool: index is ready
        
    Raises:
        RuntimeError: if cannot connect to Elasticsearch
    """
    index_name = index_name or INDEX_NAME
    mapping_file = mapping_file or MAPPING_FILE
    
    try:
        # reuse global ES client
        es = get_client()
        
        # test connection
        if not es.ping():
            raise RuntimeError(f"Cannot connect to Elasticsearch")
        
        # check if index exists
        if es.indices.exists(index=index_name):
            logger.info(f"Index '{index_name}' already exists")
            return True
        
        # read mapping file
        if not os.path.exists(mapping_file):
            logger.warning(f"Mapping file not found: {mapping_file}")
            # create default index (no custom mapping)
            es.indices.create(index=index_name)
            logger.info(f"Created index '{index_name}' with default mapping")
            return True
        
        # load mapping
        with open(mapping_file, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
        
        # create index
        es.indices.create(index=index_name, body=mapping)
        logger.info(f"Created index '{index_name}' with custom mapping")
        return True
        
    except RuntimeError as e:
        logger.error(f"Failed to ensure index: {e}")
        raise
    except Exception as e:
        logger.error(f"Error ensuring index '{index_name}': {e}")
        raise RuntimeError(f"Failed to ensure index: {e}")


def delete_index(index_name: str = None) -> bool:
    """
    delete index (for testing or reset)
    
    Args:
        index_name: index name
        
    Returns:
        bool: whether index is deleted successfully
    """
    index_name = index_name or INDEX_NAME
    
    try:
        es = get_client()
        
        if es.indices.exists(index=index_name):
            es.indices.delete(index=index_name)
            logger.info(f"Deleted index '{index_name}'")
            return True
        else:
            logger.warning(f"Index '{index_name}' does not exist")
            return False
            
    except Exception as e:
        logger.error(f"Error deleting index '{index_name}': {e}")
        return False


def recreate_index(index_name: str = None, mapping_file: str = None) -> bool:
    """
    recreate index (delete and rebuild)
    
    Args:
        index_name: index name
        mapping_file: mapping file path
        
    Returns:
        bool: whether index is recreated successfully
    """
    index_name = index_name or INDEX_NAME
    
    logger.info(f"Recreating index '{index_name}'...")
    delete_index(index_name)
    return ensure_index(index_name, mapping_file)


# optional: auto initialize index when importing
def _auto_initialize():
    """auto initialize index (optional)"""
    try:
        ensure_index()
    except Exception as e:
        logger.warning(f"Auto-initialization of index failed: {e}")

# if you need to auto initialize when importing, uncomment the following line
# _auto_initialize()