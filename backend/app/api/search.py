"""
Search API endpoints.
Provides REST APIs for hybrid search with multi-field support.
Uses Azure AI Search as backend.
"""

import os
from fastapi import APIRouter, HTTPException, Query
import time

from app.schemas.search import (
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchMetadata,
    SearchConfigResponse,
    IndexInfoResponse,
    AnalyzeRequest,
    AnalyzeResponse
)
from app.services.search import HybridSearchService
from app.services.azure_search_service import AzureSearchService
from app.clients.azure_search import get_azure_search_client 
from app.clients.azure_openai_embedding_client import AzureOpenAIEmbeddingClient
from app.core.search_config import search_config
from app.utils.logging import get_logger
from app.database import SessionLocal
from app.repositories.upload_repository import get_file_upload

router = APIRouter(prefix="/search", tags=["search"])
logger = get_logger(__name__)

# Initialize Azure Search client (may fail if env vars are missing)
try:
    azure_search_client = get_azure_search_client()
except Exception as e:
    logger.warning(f"Azure Search client not initialized: {e}")
    azure_search_client = None

# ==================== Search Endpoints ====================

@router.post("/", response_model=SearchResponse)
async def search_knowledge_base(request: SearchRequest):
    """
    Knowledge base search with multi-field support.
    
    Supports three search modes:
    - **hybrid**: Hybrid search (vector + full-text) - Recommended!
    - **knn**: Pure vector search (semantic)
    - **bm25**: Pure full-text search (exact match)
    
    Multi-field search:
    - textContent: Main field with multi-language support
    - textContent.english: Sub-field with English-specific analysis
    
    Weight priority:
    1. Request parameters (highest)
    2. .env configuration file
    3. Default values (0.5, 0.5)
    
    Example request:
    ```json
    {
      "query": "How to optimize PyTorch models?",
      "top_k": 5,
      "search_mode": "hybrid",
      "knn_weight": 0.6,
      "bm25_weight": 0.4,
      "auto_adjust": true,
      "use_multifield": true
    }
    ```
    """
    try:
        start_time = time.time()
        
        # Initialize search service
        embedding_client = AzureOpenAIEmbeddingClient()
        search_service = HybridSearchService(
            search_client=azure_search_client,
            embedding_client=embedding_client
        )
        
        # Execute search based on mode
        if request.search_mode == "hybrid":
            results, search_meta = search_service.hybrid_search(
                query=request.query,
                top_k=request.top_k,
                knn_weight=request.knn_weight,
                bm25_weight=request.bm25_weight,
                rrf_k=request.rrf_k,
                file_md5_filter=request.file_md5,
                auto_adjust=request.auto_adjust,
                use_multifield=request.use_multifield
            )
        elif request.search_mode == "knn":
            results, search_meta = search_service.knn_only_search(
                query=request.query,
                top_k=request.top_k,
                file_md5_filter=request.file_md5
            )
        elif request.search_mode == "bm25":
            results, search_meta = search_service.bm25_only_search(
                query=request.query,
                top_k=request.top_k,
                file_md5_filter=request.file_md5,
                use_multifield=request.use_multifield
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid search_mode: {request.search_mode}"
            )
        
        # Look up file names from MySQL
        file_name_cache = {}
        unique_md5s = set(r["file_md5"] for r in results if r.get("file_md5"))
        
        if unique_md5s:
            db = SessionLocal()
            try:
                for md5 in unique_md5s:
                    file_upload = get_file_upload(db, md5)
                    if file_upload:
                        file_name_cache[md5] = file_upload.file_name
            finally:
                db.close()
        
        # Normalize scores to 0-1 range (for display as 0-100%)
        # Azure Search scores typically range 0-1
        def normalize_score(raw_score: float) -> float:
            return min(raw_score, 1.0)
        
        # Convert to response format with file names and normalized scores.
        # Skip stale hits that no longer have a backing file record in MySQL.
        search_results = []
        for r in results:
            md5 = r.get("file_md5")
            if not md5:
                continue
            if md5 not in file_name_cache:
                continue
            search_results.append(
                SearchResult(
                    file_md5=md5,
                    file_name=file_name_cache.get(md5),
                    chunk_id=r["chunk_id"],
                    text_content=r.get("content", r.get("text_content", "")),
                    score=normalize_score(r["score"]),
                    highlights=r.get("highlights", []),
                    model_version=r.get("model_version")
                )
            )
        
        execution_time = (time.time() - start_time) * 1000
        
        # Build metadata
        metadata = SearchMetadata(**search_meta)
        
        return SearchResponse(
            query=request.query,
            total_results=len(search_results),
            results=search_results,
            search_mode=request.search_mode,
            metadata=metadata,
            execution_time_ms=execution_time
        )
        
    except Exception as e:
        logger.error(f"Search failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/compare")
async def compare_search_methods(
    query: str = Query(..., min_length=1, description="Search query"),
    top_k: int = Query(5, ge=1, le=20, description="Results per method"),
    use_multifield: bool = Query(True, description="Enable multi-field")
):
    """
    Compare three search methods (for debugging and optimization).
    
    Executes hybrid, pure vector, and pure full-text search simultaneously
    to compare their results.
    
    Example:
    ```
    GET /api/v1/search/compare?query=PyTorch optimizer&top_k=3
    ```
    """
    try:
        embedding_client = AzureOpenAIEmbeddingClient()
        search_service = HybridSearchService(
            search_client=azure_search_client,
            embedding_client=embedding_client
        )
        
        # Execute all three search methods
        hybrid_results, hybrid_meta = search_service.hybrid_search(
            query, top_k, use_multifield=use_multifield
        )
        knn_results, knn_meta = search_service.knn_only_search(query, top_k)
        bm25_results, bm25_meta = search_service.bm25_only_search(
            query, top_k, use_multifield=use_multifield
        )
        
        return {
            "query": query,
            "multifield_enabled": use_multifield,
            "hybrid": {
                "results": hybrid_results,
                "metadata": hybrid_meta
            },
            "knn_only": {
                "results": knn_results,
                "metadata": knn_meta
            },
            "bm25_only": {
                "results": bm25_results,
                "metadata": bm25_meta
            }
        }
    except Exception as e:
        logger.error(f"Comparison failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Configuration Endpoints ====================

@router.get("/config", response_model=SearchConfigResponse)
async def get_search_config():
    """
    Get current search configuration.
    
    Returns current effective search configuration including:
    - Hybrid search weights (knn, bm25, rrf_k)
    - Multi-field boost values
    - Result limits
    - Feature flags
    """
    config_summary = search_config.get_config_summary()
    return SearchConfigResponse(**config_summary)


@router.post("/config/weights")
async def update_search_weights(
    knn_weight: float = Query(None, ge=0, le=1, description="KNN weight"),
    bm25_weight: float = Query(None, ge=0, le=1, description="BM25 weight"),
    rrf_k: int = Query(None, ge=1, le=200, description="RRF constant")
):
    """
    Update hybrid search weights dynamically (runtime only).
    
    Note: Changes only take effect during current runtime.
    Modify .env file for permanent configuration.
    
    Example:
    ```
    POST /api/v1/search/config/weights?knn_weight=0.7&bm25_weight=0.3
    ```
    """
    try:
        search_config.update_weights(
            knn_weight=knn_weight,
            bm25_weight=bm25_weight,
            rrf_k=rrf_k
        )
        
        return {
            "code": 200,
            "message": "Weights updated successfully",
            "data": search_config.get_weights()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/config/field-boosts")
async def update_field_boosts(
    chinese_boost: float = Query(None, ge=0, le=10, description="Chinese field boost"),
    english_boost: float = Query(None, ge=0, le=10, description="English field boost"),
    standard_boost: float = Query(None, ge=0, le=10, description="Standard field boost"),
    tie_breaker: float = Query(None, ge=0, le=1, description="Tie breaker value")
):
    """
    Update multi-field boost values dynamically (runtime only).
    
    Field boosts control the importance of each text field in BM25 scoring:
    - chinese_boost: Chinese analyzer field (IK)
    - english_boost: English analyzer field (with stemming)
    - standard_boost: Standard tokenizer field (fallback)
    - tie_breaker: Contribution of non-best fields (0-1)
    
    Example:
    ```
    POST /api/v1/search/config/field-boosts?chinese_boost=1.2&english_boost=0.8
    ```
    """
    try:
        search_config.update_field_boosts(
            chinese_boost=chinese_boost,
            english_boost=english_boost,
            standard_boost=standard_boost,
            tie_breaker=tie_breaker
        )
        
        return {
            "code": 200,
            "message": "Field boosts updated successfully",
            "data": search_config.get_field_boosts()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== Index Management Endpoints ====================

@router.get("/index/info", response_model=IndexInfoResponse)
async def get_index_info():
    """
    Get Azure AI Search index information.
    
    Returns:
    - Index existing status
    - Document count
    - Index name
    """
    try:
        azure_service = AzureSearchService(azure_search_client)
        doc_count = azure_service.count_documents()
        
        return IndexInfoResponse(
            exists=True,  # If we got here, client initialized successfully
            index=search_config.ES_INDEX_NAME,
            doc_count=doc_count,
            store_size_mb=None,  # Not available via SearchClient
            ik_available=None,  # Not applicable to Azure Search
            error=None
        )
    except Exception as e:
        logger.error(f"Get index info failed: {e}")
        return IndexInfoResponse(
            exists=False,
            index=search_config.ES_INDEX_NAME,
            error=str(e)
        )


@router.post("/index/create")
async def create_index():
    """
    Note: Azure AI Search indexes must be created via Azure Portal or SearchIndexClient.
    
    This endpoint returns status information and guidance.
    
    To create an index:
    1. Use Azure Portal (https://portal.azure.com)
    2. Or use the azure-search-documents SDK's SearchIndexClient
    3. Create an index with the following fields:
       - id (Edm.String, key)
       - fileMd5 (Edm.String, filterable)
       - chunkId (Edm.Int32)
       - textContent (Edm.String, searchable)
       - vector (Collection(Edm.Single), dimensions=1536)
       - createdAt (Edm.DateTimeOffset)
       - modelVersion (Edm.String)
    """
    try:
        return {
            "code": 501,
            "message": "Azure AI Search index creation must be done via Azure Portal or SearchIndexClient",
            "data": {
                "endpoint": os.getenv("AZURE_SEARCH_ENDPOINT", "Not configured"),
                "index": search_config.ES_INDEX_NAME,
                "docs": "https://learn.microsoft.com/azure/search/search-create-index"
            }
        }
    except Exception as e:
        logger.error(f"Create index info failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/index/delete")
async def delete_index():
    """
    Azure AI Search indexes must be deleted via Azure Portal or the SDK.
    
    This endpoint is not supported for cloud-hosted Azure Search.
    To delete an index, use Azure Portal or SearchIndexClient.delete_index().
    """
    return {
        "code": 501,
        "message": "Azure AI Search index deletion must be done via Azure Portal or SDK"
    }


@router.post("/index/recreate")
async def recreate_index():
    """
    Azure AI Search indexes must be managed via Azure Portal or the SDK.
    
    To recreate an index:
    1. Delete via Azure Portal or SearchIndexClient
    2. Create new index with desired mapping
    
    See /search/index/create for guidance on creating indices.
    """
    return {
        "code": 501,
        "message": "Index recreation must be done via Azure Portal or SDK"
    }


# ==================== Debug Endpoints ====================

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_text(request: AnalyzeRequest):
    """
    Text analysis endpoint (Azure Search compatibility).
    
    Note: Azure Search doesn't expose analyzer details via SearchClient.
    This returns placeholder response. For actual analysis, use Azure Portal's
    analyzer testing feature.
    """
    try:
        return AnalyzeResponse(
            success=False,
            analyzer=request.analyzer,
            text=request.text,
            tokens=[],
            error="Text analysis not available via SearchClient. Use Azure Portal's analyzer testing instead."
        )
    except Exception as e:
        logger.error(f"Analyze failed: {e}")
        return AnalyzeResponse(
            success=False,
            analyzer=request.analyzer,
            text=request.text,
            tokens=[],
            error=str(e)
        )
