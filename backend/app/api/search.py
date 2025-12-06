"""
Search API endpoints.
Provides REST APIs for hybrid search with multi-field support.
"""

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
from app.services.es_service import ElasticsearchService
from app.clients.elastic import es_client
from app.clients.gemini_embedding_client import GeminiEmbeddingClient
from app.core.search_config import search_config
from app.utils.logging import get_logger

router = APIRouter(prefix="/search", tags=["search"])
logger = get_logger(__name__)


# ==================== Search Endpoints ====================

@router.post("/", response_model=SearchResponse)
async def search_knowledge_base(request: SearchRequest):
    """
    Knowledge base search with multi-field support.
    
    Supports three search modes:
    - **hybrid**: Hybrid search (KNN + BM25) with RRF fusion - Recommended!
    - **knn**: Pure vector search (semantic)
    - **bm25**: Pure keyword search (exact match)
    
    Multi-field search:
    - Chinese field: IK analyzer (smart/max_word)
    - English field: English analyzer with stemming
    - Standard field: Basic tokenization (fallback)
    
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
        embedding_client = GeminiEmbeddingClient()
        search_service = HybridSearchService(
            es_client=es_client,
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
        
        # Convert to response format
        search_results = [
            SearchResult(
                file_md5=r["file_md5"],
                chunk_id=r["chunk_id"],
                text_content=r["text_content"],
                score=r["score"],
                highlights=r.get("highlights", []),
                model_version=r.get("model_version")
            )
            for r in results
        ]
        
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
    
    Executes hybrid, pure KNN, and pure BM25 simultaneously
    to compare their results.
    
    Example:
    ```
    GET /api/v1/search/compare?query=PyTorch optimizer&top_k=3
    ```
    """
    try:
        embedding_client = GeminiEmbeddingClient()
        search_service = HybridSearchService(
            es_client=es_client,
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
    Get Elasticsearch index information.
    
    Returns:
    - Index existence status
    - Document count
    - Storage size
    - IK plugin availability
    """
    try:
        es_service = ElasticsearchService(es_client)
        info = es_service.get_index_info()
        
        # Check IK availability
        ik_available = es_service._check_ik_plugin()
        
        return IndexInfoResponse(
            exists=info.get("exists", False),
            index=info.get("index", search_config.ES_INDEX_NAME),
            doc_count=info.get("doc_count"),
            store_size_mb=info.get("store_size_mb"),
            ik_available=ik_available,
            error=info.get("error")
        )
    except Exception as e:
        logger.error(f"Get index info failed: {e}")
        return IndexInfoResponse(
            exists=False,
            index=search_config.ES_INDEX_NAME,
            error=str(e)
        )


@router.post("/index/create")
async def create_index(
    use_ik: bool = Query(True, description="Use IK analyzer for Chinese")
):
    """
    Create Elasticsearch index with multi-field mapping.
    
    Creates index with:
    - Chinese field (IK analyzer if available)
    - English field (with stemming)
    - Standard field (fallback)
    - Vector field (768 dimensions)
    
    Args:
        use_ik: Whether to use IK analyzer (requires IK plugin)
    """
    try:
        es_service = ElasticsearchService(es_client)
        result = es_service.create_index(use_ik=use_ik)
        
        return {
            "code": 200 if result["success"] else 400,
            "message": result["message"],
            "data": result
        }
    except Exception as e:
        logger.error(f"Create index failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/index/delete")
async def delete_index():
    """
    Delete Elasticsearch index (WARNING: destroys all data).
    
    Use with caution - this operation cannot be undone.
    """
    try:
        es_service = ElasticsearchService(es_client)
        result = es_service.delete_index()
        
        return {
            "code": 200 if result["success"] else 400,
            "message": result["message"]
        }
    except Exception as e:
        logger.error(f"Delete index failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index/recreate")
async def recreate_index(
    use_ik: bool = Query(True, description="Use IK analyzer for Chinese")
):
    """
    Recreate Elasticsearch index (WARNING: destroys all data).
    
    Deletes existing index and creates a new one with fresh mapping.
    Use when you need to update the index mapping.
    """
    try:
        es_service = ElasticsearchService(es_client)
        result = es_service.recreate_index(use_ik=use_ik)
        
        return {
            "code": 200 if result["success"] else 400,
            "message": result["message"],
            "data": result
        }
    except Exception as e:
        logger.error(f"Recreate index failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Debug Endpoints ====================

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_text(request: AnalyzeRequest):
    """
    Analyze text with specified analyzer (for debugging).
    
    Test how different analyzers tokenize text:
    - chinese_smart / ik_smart: Chinese coarse-grained
    - chinese_max / ik_max_word: Chinese fine-grained
    - english: English with stemming
    - standard: Basic tokenization
    
    Example:
    ```json
    {
      "text": "PyTorch 深度学习优化",
      "analyzer": "chinese_smart"
    }
    ```
    """
    try:
        es_service = ElasticsearchService(es_client)
        result = es_service.test_analyzer(
            text=request.text,
            analyzer=request.analyzer
        )
        
        return AnalyzeResponse(**result)
    except Exception as e:
        logger.error(f"Analyze failed: {e}")
        return AnalyzeResponse(
            success=False,
            analyzer=request.analyzer,
            text=request.text,
            error=str(e)
        )
