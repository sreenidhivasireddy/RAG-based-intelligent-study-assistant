"""
Azure AI Search operation wrapper service.
Provides index management, bulk indexing, and document operations.
Replaces ElasticsearchService for Azure AI Search.
"""

from azure.search.documents import SearchClient
from typing import List, Dict, Optional, Any
import logging

from app.models.es_document import EsDocument

logger = logging.getLogger(__name__)


class AzureSearchService:
    """
    Azure AI Search operation wrapper service.
    Handles index management and document operations.
    Provides compatibility layer for operations previously done with Elasticsearch.
    """

    def __init__(self, search_client: SearchClient, index_name: str = None):
        self.search_client = search_client
        self.index_name = index_name or search_client._index_name

    # ---------------------------
    # ✅ NEW: Type coercion helper
    # ---------------------------
    def _is_vector_field(self, key: str, value: Any) -> bool:
        """
        Heuristic: treat fields containing 'vector' as embedding vectors.
        Keeps them as List[float] so Azure Search vector fields don't break.
        """
        if not isinstance(key, str):
            return False
        if "vector" not in key.lower():
            return False
        if isinstance(value, list) and value and isinstance(value[0], (int, float)):
            return True
        return False

    def _coerce_value(self, key: str, value: Any) -> Any:
        """
        Coerce values so Azure Search doesn't reject type mismatches.
        Main goal: avoid sending ints to Edm.String fields.
        """
        # Preserve vector fields as-is (list of floats)
        if self._is_vector_field(key, value):
            return value

        # None is fine
        if value is None:
            return None

        # Dict: recurse
        if isinstance(value, dict):
            return {k: self._coerce_value(str(k), v) for k, v in value.items()}

        # List: recurse (but preserve list-of-floats vectors handled above)
        if isinstance(value, list):
            return [self._coerce_value(key, v) for v in value]

        # ✅ Convert primitives that commonly cause schema mismatch
        # If your index expects Edm.String (common), this prevents errors like "literal '1'"
        if isinstance(value, (int, float, bool)):
            return str(value)

        # Everything else (strings, etc.) pass through
        return value

    def _coerce_document(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply coercion to all fields and remap field names to match Azure Search schema.
        Maps Python field names to Azure Search schema field names.
        """
        # First coerce all values
        coerced = {}
        for k, v in doc.items():
            key = str(k)
            coerced[key] = self._coerce_value(key, v)
        
        # Then remap field names to match Azure Search schema
        # Remove any fields not in schema and rename as needed
        field_mapping = {
            'text_content': 'content',  # old field name to new
            'vector': 'embedding',      # old field name to new
            'model_version': None,      # drop this field (not in schema)
        }
        
        remapped = {}
        for k, v in coerced.items():
            # Check if this field needs to be renamed
            if k in field_mapping:
                new_key = field_mapping[k]
                if new_key is not None:  # skip if mapped to None (drop field)
                    remapped[new_key] = v
            else:
                # Keep field as-is if not in mapping
                remapped[k] = v
        
        return remapped

    def bulk_index(self, documents: List[EsDocument]) -> Dict:
        """
        Bulk index documents to Azure AI Search.
        """
        try:
            logger.info(f"Bulk indexing {len(documents)} documents to Azure Search")

            actions = []
            for doc in documents:
                doc_dict = doc.to_es_dict()

                # Azure Search requires 'id' field as Edm.String
                base = {
                    "id": str(doc.id),
                    **doc_dict
                }

                # ✅ Coerce types to avoid Edm.String mismatch (like int 1)
                safe_doc = self._coerce_document(base)

                actions.append(safe_doc)

            results = self.search_client.upload_documents(actions)

            succeeded = sum(1 for r in results if r.succeeded)
            failed = sum(1 for r in results if not r.succeeded)

            logger.info(f"🔍 BULK RESULT:")
            logger.info(f"   success = {succeeded}")
            logger.info(f"   failed = {failed}")

            if failed > 0:
                logger.error(f"Bulk indexing partially failed: {failed} documents")
                failed_docs = [r for r in results if not r.succeeded]
                for item in failed_docs:
                    logger.error(f"Document indexing failed: {item}")
                return {
                    "success": False,
                    "indexed": succeeded,
                    "failed": failed,
                    "errors": [str(r) for r in failed_docs]
                }

            logger.info(f"Bulk indexing completed: {succeeded} documents")
            return {"success": True, "indexed": succeeded, "failed": 0}

        except Exception as e:
            logger.error(f"Bulk indexing failed: {e}")
            raise RuntimeError(f"Bulk indexing failed: {e}") from e

    def delete_by_file_md5(self, file_md5: str) -> Dict:
        try:
            # Support both common schema variants used in this project.
            filter_queries = [
                f"file_md5 eq '{file_md5}'",
                f"fileMd5 eq '{file_md5}'",
            ]
            doc_ids = set()

            for filter_query in filter_queries:
                try:
                    search_results = self.search_client.search(
                        search_text="*",
                        filter=filter_query,
                        select=["id"],
                        top=10000
                    )
                    for result in search_results:
                        doc_id = result.get("id")
                        if doc_id:
                            doc_ids.add(str(doc_id))
                except Exception as sub_err:
                    logger.warning(
                        "Delete query failed for filter '%s': %s",
                        filter_query,
                        sub_err
                    )

            deleted_count = len(doc_ids)
            if deleted_count > 0:
                delete_actions = [{"id": doc_id} for doc_id in doc_ids]
                self.search_client.delete_documents(delete_actions)
                logger.info(f"Deleted {deleted_count} documents for file_md5: {file_md5}")
            else:
                logger.info(f"No documents found for file_md5: {file_md5}")

            return {"success": True, "deleted": deleted_count, "file_md5": file_md5}

        except Exception as e:
            logger.error(f"Delete by file_md5 failed: {e}")
            raise RuntimeError(f"Delete by file_md5 failed: {e}") from e

    def count_documents(self, file_md5: str = None) -> int:
        try:
            if file_md5:
                filter_query = f"fileMd5 eq '{file_md5}'"
                response = self.search_client.search(
                    search_text="*",
                    filter=filter_query,
                    select=["id"],
                    top=1
                )
            else:
                response = self.search_client.search(
                    search_text="*",
                    select=["id"],
                    top=1
                )

            return getattr(response, "_total_count", 0) or 0

        except Exception as e:
            logger.error(f"Count documents failed: {e}")
            return 0

    def search(self, query: str = None, top_k: int = 5, vector: list = None, filter_expr: str = None, select: list = None) -> List[Dict]:
        """
        Simple search wrapper returning documents and metadata.
        If `vector` is provided, performs a KNN vector search; otherwise uses text search.
        Returns list of dicts: {id, file_md5, chunk_id, content, file_name, chunk_index, score}
        """
        try:
            select = select or ["id", "file_md5", "chunk_id", "content", "file_name", "chunk_index"]

            if vector is not None:
                logger.info(f"Executing vector search (k={top_k})")
                results_iter = self.search_client.search(
                    search_text="",
                    vector_queries=[{
                        'kind': 'vector',
                        'vector': vector,
                        'fields': 'embedding',
                        'k': top_k
                    }],
                    filter=filter_expr,
                    top=top_k,
                    select=select
                )
            else:
                logger.info(f"Executing text search (top={top_k}) query='{(query or '')[:80]}'")
                results_iter = self.search_client.search(
                    search_text=query or "",
                    filter=filter_expr,
                    top=top_k,
                    select=select
                )

            results = []
            for hit in results_iter:
                results.append({
                    "id": hit.get("id"),
                    "file_md5": hit.get("file_md5"),
                    "chunk_id": hit.get("chunk_id"),
                    "content": hit.get("content"),
                    "file_name": hit.get("file_name"),
                    "chunk_index": hit.get("chunk_index"),
                    "score": hit.get("@search.score", 0)
                })

            logger.info(f"Search returned {len(results)} documents")
            return results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def create_index_if_not_exists(self, index_config: Dict) -> bool:
        logger.warning(
            "Index creation must be done via Azure Portal or Azure SDK's SearchIndexClient. "
            "SearchClient cannot create indices. Please ensure the index exists before proceeding."
        )
        return False
