# python-backend/app/services/elasticsearch_service.py

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from typing import List
from app.models.es_document import EsDocument
from app.clients.elastic import ES_INDEX
import logging

logger = logging.getLogger(__name__)

class ElasticsearchService:
    """Elasticsearch operation wrapper service"""
    
    def __init__(self, es_client: Elasticsearch):
        self.es = es_client
        # Keep index name aligned with global ES configuration
        self.index_name = ES_INDEX
    
    def bulk_index(self, documents: List[EsDocument]) -> None:
        """
        Bulk index documents to Elasticsearch
        
        Args:
            documents: List of EsDocument objects
        """
        try:
            logger.info(f"Bulk indexing documents to ES, document count: {len(documents)}")
            
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
                logger.error(f"Bulk indexing部分失败: {len(failed)} 个文档")
                for item in failed:
                    logger.error(f"Document indexing failed: {item}")
                raise RuntimeError("Bulk indexing部分失败")
            
            logger.info(f"Bulk indexing成功完成，文档数量: {success}")
            
        except Exception as e:
            logger.error(f"Bulk indexing failed: {e}")
            raise RuntimeError("Bulk indexing failed") from e
    
    def delete_by_file_md5(self, file_md5: str) -> None:
        """
        Delete document by file_md5
        
        Args:
            file_md5: file fingerprint
        """
        try:
            query = {
                "query": {
                    "term": {
                        "file_md5": file_md5
                    }
                }
            }
            self.es.delete_by_query(index=self.index_name, body=query)
            logger.info(f"Successfully deleted document, file_md5: {file_md5}")
            
        except Exception as e:
            logger.error(f"Deleting document failed: {e}")
            raise RuntimeError("Deleting document failed") from e