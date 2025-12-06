"""
Elasticsearch index configuration.
Defines index mapping with multi-field text analysis for Chinese and English.

Requirements:
    - Elasticsearch 9.x
    - IK Analysis plugin (for Chinese tokenization)
    
Installation:
    ./elasticsearch-9.2.0/bin/elasticsearch-plugin install \
        https://github.com/infinilabs/analysis-ik/releases/download/v9.2.0/elasticsearch-analysis-ik-9.2.0.zip
"""

import os
from typing import Dict, Any


class ESIndexConfig:
    """
    Elasticsearch index configuration class.
    Provides index mapping and settings for multi-field text search.
    """
    
    # Index name from environment or default
    INDEX_NAME: str = os.getenv("ES_INDEX_NAME", "knowledge_base")
    
    # Vector dimensions (Gemini text-embedding-004)
    VECTOR_DIMS: int = 768
    
    @classmethod
    def get_index_settings(cls) -> Dict[str, Any]:
        """
        Get index settings with custom analyzers.
        
        Returns:
            Dictionary containing index settings
        """
        return {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    # Chinese analyzer using IK plugin (smart mode)
                    "chinese_smart": {
                        "type": "custom",
                        "tokenizer": "ik_smart",
                        "filter": ["lowercase"]
                    },
                    # Chinese analyzer using IK plugin (max word mode)
                    "chinese_max": {
                        "type": "custom",
                        "tokenizer": "ik_max_word",
                        "filter": ["lowercase"]
                    }
                }
            }
        }
    
    @classmethod
    def get_index_mapping(cls) -> Dict[str, Any]:
        """
        Get index mapping with multi-field configuration.
        
        Field structure:
            - textContent: Main field with IK Chinese analyzer
                - textContent.english: Sub-field with English stemming
                - textContent.standard: Sub-field with standard tokenizer
        
        Returns:
            Dictionary containing index mapping
        """
        return {
            "properties": {
                # Metadata fields
                "fileMd5": {
                    "type": "keyword",
                    "doc_values": True
                },
                "chunkId": {
                    "type": "integer"
                },
                "modelVersion": {
                    "type": "keyword"
                },
                "createdAt": {
                    "type": "date"
                },
                
                # Multi-field text content
                "textContent": {
                    "type": "text",
                    "analyzer": "chinese_max",       # Index: fine-grained Chinese
                    "search_analyzer": "chinese_smart",  # Search: coarse-grained Chinese
                    "fields": {
                        # English sub-field with stemming
                        "english": {
                            "type": "text",
                            "analyzer": "english"   # Built-in English analyzer with stemming
                        },
                        # Standard sub-field as fallback
                        "standard": {
                            "type": "text",
                            "analyzer": "standard"  # Basic tokenization
                        }
                    }
                },
                
                # Dense vector for KNN search
                "vector": {
                    "type": "dense_vector",
                    "dims": cls.VECTOR_DIMS,
                    "index": True,
                    "similarity": "cosine"
                }
            }
        }
    
    @classmethod
    def get_full_index_config(cls) -> Dict[str, Any]:
        """
        Get complete index configuration (settings + mapping).
        
        Returns:
            Dictionary containing full index configuration
        """
        return {
            "settings": cls.get_index_settings(),
            "mappings": cls.get_index_mapping()
        }
    
    @classmethod
    def get_fallback_mapping(cls) -> Dict[str, Any]:
        """
        Get fallback mapping without IK plugin (uses standard analyzer).
        Use this if IK plugin is not installed.
        
        Returns:
            Dictionary containing fallback index mapping
        """
        return {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "mappings": {
                "properties": {
                    "fileMd5": {"type": "keyword"},
                    "chunkId": {"type": "integer"},
                    "modelVersion": {"type": "keyword"},
                    "createdAt": {"type": "date"},
                    "textContent": {
                        "type": "text",
                        "analyzer": "standard",
                        "fields": {
                            "english": {
                                "type": "text",
                                "analyzer": "english"
                            }
                        }
                    },
                    "vector": {
                        "type": "dense_vector",
                        "dims": cls.VECTOR_DIMS,
                        "index": True,
                        "similarity": "cosine"
                    }
                }
            }
        }


# Export configuration instance
es_index_config = ESIndexConfig()

