"""
Azure AI Search index configuration.
Defines index schema for Azure AI Search with multi-field text analysis support.

Note: This configuration is for reference. To create the index in Azure AI Search:
1. Use Azure Portal (https://portal.azure.com)
2. Or use the azure-search-documents SDK's SearchIndexClient
"""

import os
from typing import Dict, Any


class ESIndexConfig:
    """
    Azure AI Search index configuration class.
    Provides index mapping and settings for multi-field text search.
    """
    
    # Index name from environment or default
    INDEX_NAME: str = os.getenv("AZURE_SEARCH_INDEX", "rag-index")
    
    # Vector dimensions (Azure OpenAI text-embedding-3-small: 1536, or ada: 1536)
    VECTOR_DIMS: int = 1536
    
    @classmethod
    def get_index_mapping(cls) -> Dict[str, Any]:
        """
        Get index mapping for Azure AI Search.
        
        This is reference documentation. To create this index:
        1. Use Azure Portal (https://portal.azure.com)
        2. Or use SearchIndexClient from azure-search-documents SDK
        
        Field structure:
            - id (Edm.String, Key) - Document ID
            - fileMd5 (Edm.String, Filterable) - File fingerprint
            - chunkId (Edm.Int32) - Chunk identifier
            - textContent (Edm.String, Searchable) - Main searchable content
            - vector (Collection(Edm.Single)) - Vector embeddings (1536 dims)
            - modelVersion (Edm.String) - Model version used for embeddings
            - createdAt (Edm.DateTimeOffset) - Creation timestamp
        
        Returns:
            Dictionary containing field definitions
        """
        return {
            "fields": [
                {
                    "name": "id",
                    "type": "Edm.String",
                    "key": True,
                    "retrievable": True
                },
                {
                    "name": "fileMd5",
                    "type": "Edm.String",
                    "filterable": True,
                    "retrievable": True
                },
                {
                    "name": "chunkId",
                    "type": "Edm.Int32",
                    "retrievable": True
                },
                {
                    "name": "textContent",
                    "type": "Edm.String",
                    "searchable": True,
                    "retrievable": True,
                    "analyzer": "standard.lucene"
                },
                {
                    "name": "vector",
                    "type": "Collection(Edm.Single)",
                    "searchable": True,
                    "queryable": True,
                    "retrievable": True,
                    "dimensions": cls.VECTOR_DIMS,
                    "vectorSearchConfiguration": "vectorConfig"
                },
                {
                    "name": "modelVersion",
                    "type": "Edm.String",
                    "filterable": True,
                    "retrievable": True
                },
                {
                    "name": "createdAt",
                    "type": "Edm.DateTimeOffset",
                    "filterable": True,
                    "retrievable": True
                }
            ]
        }
    
    @classmethod
    def get_vector_search_config(cls) -> Dict[str, Any]:
        """
        Get vector search configuration for Azure AI Search.
        
        Returns:
            Dictionary containing vector search settings
        """
        return {
            "algorithmConfigurations": [
                {
                    "name": "vectorConfig",
                    "kind": "hnsw",
                    "parameters": {
                        "m": 4,
                        "efConstruction": 400,
                        "efSearch": 500,
                        "metric": "cosine"
                    }
                }
            ]
        }
    
    @classmethod
    def get_full_index_config(cls) -> Dict[str, Any]:
        """
        Get complete index creation JSON for Azure AI Search.
        
        Use this to create the index via Azure Portal or SDK:
        ```python
        from azure.search.documents.indexes import SearchIndexClient
        from azure.search.documents.indexes.models import SearchIndex
        
        config = ESIndexConfig.get_full_index_config()
        index = SearchIndex(name="your-index-name", **config)
        client.create_index(index)
        ```
        
        Returns:
            Dictionary containing full index configuration
        """
        return {
            **cls.get_index_mapping(),
            "vectorSearch": cls.get_vector_search_config()
        }
    
    @classmethod
    def get_setup_instructions(cls) -> str:
        """
        Get instructions for setting up Azure AI Search index.
        
        Returns:
            Formatted instruction string
        """
        return f"""
Azure AI Search Index Setup Instructions
==========================================

Option 1: Using Azure Portal
1. Go to https://portal.azure.com
2. Navigate to your Azure AI Search service
3. Click "Indexes" → "Create Index"
4. Add the following fields:
   - id (Required, Key field, type: String)
   - fileMd5 (String, Filterable)
   - chunkId (Int32)
   - textContent (String, Searchable)
   - vector (Collection of Single, {cls.VECTOR_DIMS} dimensions)
   - modelVersion (String)
   - createdAt (DateTimeOffset, Filterable)

Option 2: Using Python SDK
```python
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import SearchIndex

config = {cls.__module__}.get_full_index_config()
index = SearchIndex(name="{cls.INDEX_NAME}", **config)
client = SearchIndexClient(endpoint, credential)
client.create_index(index)
```

Configuration:
- Index name: {cls.INDEX_NAME}
- Vector dimensions: {cls.VECTOR_DIMS}
- Vector algorithm: HNSW (Hierarchical Navigable Small World)
- Similarity metric: Cosine
"""


# Export configuration instance
es_index_config = ESIndexConfig()