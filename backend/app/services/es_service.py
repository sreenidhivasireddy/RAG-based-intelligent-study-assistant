"""
Elasticsearch operation wrapper service.
Provides index management, bulk indexing, and document operations.
Supports multi-field indexing with Chinese (IK) and English analyzers.
"""

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from typing import List, Dict, Optional
import logging

from app.models.es_document import EsDocument
from app.clients.elastic import ES_INDEX
import logging

logger = logging.getLogger(__name__)


class ElasticsearchService:
    """
    Elasticsearch operation wrapper service.
    Handles index management and document operations.
    """
    
    def __init__(self, es_client: Elasticsearch, index_name: str = None):
        """
        Initialize Elasticsearch service.
        
        Args:
            es_client: Elasticsearch client instance
            index_name: Index name (defaults to config value)
        """
        self.es = es_client
        # Keep index name aligned with global ES configuration
        self.index_name = ES_INDEX
    
    def bulk_index(self, documents: List[EsDocument]) -> None:
        """
        Bulk index documents to Elasticsearch.
        
        Args:
            documents: List of EsDocument objects
            
        Returns:
            Dictionary containing indexing result
        """
        try:
            logger.info(f"Bulk indexing {len(documents)} documents to ES")
            
            # Build bulk operations
            actions = [
                {
                    "_index": self.index_name,
                    "_id": doc.id,
                    "_source": doc.to_es_dict()
                }
                for doc in documents
            ]
            
            # Execute bulk operations
            # Use refresh=True for immediate visibility without waiting for all replicas
            success, failed = bulk(self.es, actions, raise_on_error=False, refresh=True)
            print("🔍 BULK RESULT:")
            print("   success =", success)
            print("   failed =", failed)

            
            if failed:
                logger.error(f"Bulk indexing partially failed: {len(failed)} documents")
                for item in failed:
                    logger.error(f"Document indexing failed: {item}")
                return {
                    "success": False,
                    "indexed": success,
                    "failed": len(failed),
                    "errors": failed
                }
            
            logger.info(f"Bulk indexing completed: {success} documents")
            return {
                "success": True,
                "indexed": success,
                "failed": 0
            }
            
        except Exception as e:
            logger.error(f"Bulk indexing failed: {e}")
            raise RuntimeError(f"Bulk indexing failed: {e}") from e
    
    def delete_by_file_md5(self, file_md5: str) -> Dict:
        """
        Delete all documents by file MD5.
        
        Args:
            file_md5: File fingerprint
            
        Returns:
            Dictionary containing deletion result
        """
        try:
            query = {
                "query": {
                    "term": {
                        "file_md5": file_md5
                    }
                }
            }
            
            response = self.es.delete_by_query(index=self.index_name, body=query)
            deleted = response.get("deleted", 0)
            
            logger.info(f"Deleted {deleted} documents for file_md5: {file_md5}")
            return {
                "success": True,
                "deleted": deleted,
                "file_md5": file_md5
            }
            
        except Exception as e:
            logger.error(f"Delete by file_md5 failed: {e}")
            raise RuntimeError(f"Delete by file_md5 failed: {e}") from e
    
    def count_documents(self, file_md5: str = None) -> int:
        """
        Count documents in index.
        
        Args:
            file_md5: Optional filter by file MD5
            
        Returns:
            Document count
        """
        try:
            if file_md5:
                query = {"query": {"term": {"file_md5": file_md5}}}
            else:
                query = {"query": {"match_all": {}}}
            
            response = self.es.count(index=self.index_name, body=query)
            return response["count"]
            
        except Exception as e:
            logger.error(f"Count documents failed: {e}")
            return 0
    
    # ==================== Analyzer Testing ====================
    
    def test_analyzer(self, text: str, analyzer: str = "chinese_smart") -> Dict:
        """
        Test analyzer on given text (for debugging).
        
        Args:
            text: Text to analyze
            analyzer: Analyzer name
            
        Returns:
            Dictionary containing tokens
        """
        try:
            # Try index-specific analyzer first
            try:
                response = self.es.indices.analyze(
                    index=self.index_name,
                    body={
                        "analyzer": analyzer,
                        "text": text
                    }
                )
            except Exception:
                # Fall back to global analyzer
                response = self.es.indices.analyze(
                    body={
                        "analyzer": analyzer,
                        "text": text
                    }
                )
            
            return {
                "success": True,
                "analyzer": analyzer,
                "text": text,
                "tokens": [t["token"] for t in response["tokens"]]
            }
            
        except Exception as e:
            return {
                "success": False,
                "analyzer": analyzer,
                "text": text,
                "error": str(e)
            }
