"""
Search-related data models.
Defines request and response schemas for search APIs.
Supports multi-field search with configurable field boosts.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
from datetime import datetime


class SearchRequest(BaseModel):
    """
    Search request model.
    
    Attributes:
        query: Search query text (1-500 characters)
        top_k: Number of results to return (1-100)
        search_mode: Search mode (hybrid/knn/bm25)
        knn_weight: Optional KNN weight override (0-1)
        bm25_weight: Optional BM25 weight override (0-1)
        rrf_k: Optional RRF constant override (1-200)
        file_md5: Optional file filter
        auto_adjust: Whether to auto-adjust weights
        use_multifield: Whether to use multi-field search
    """
    
    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Search query text"
    )
    
    top_k: int = Field(
        10,
        ge=1,
        le=100,
        description="Number of results to return"
    )
    
    search_mode: str = Field(
        "hybrid",
        description="Search mode: hybrid (KNN+BM25), knn (vector only), bm25 (keyword only)"
    )
    
    # Hybrid search weight overrides
    knn_weight: Optional[float] = Field(
        None,
        ge=0,
        le=1,
        description="KNN weight override (0-1)"
    )
    
    bm25_weight: Optional[float] = Field(
        None,
        ge=0,
        le=1,
        description="BM25 weight override (0-1)"
    )
    
    rrf_k: Optional[int] = Field(
        None,
        ge=1,
        le=200,
        description="RRF constant override"
    )
    
    # Filter options
    file_md5: Optional[str] = Field(
        None,
        description="Filter by specific file MD5"
    )
    
    # Feature flags
    auto_adjust: Optional[bool] = Field(
        None,
        description="Auto-adjust weights based on query features"
    )
    
    use_multifield: Optional[bool] = Field(
        None,
        description="Enable multi-field search (Chinese + English)"
    )
    
    @field_validator('search_mode')
    @classmethod
    def validate_search_mode(cls, v: str) -> str:
        """Validate search mode value."""
        allowed_modes = ["hybrid", "knn", "bm25"]
        if v not in allowed_modes:
            raise ValueError(f"search_mode must be one of {allowed_modes}")
        return v
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query": "How to optimize PyTorch models?",
                    "top_k": 5,
                    "search_mode": "hybrid",
                    "knn_weight": 0.5,
                    "bm25_weight": 0.5,
                    "use_multifield": True
                }
            ]
        }
    }


class SearchResult(BaseModel):
    """
    Single search result.
    
    Attributes:
        file_md5: Source file MD5 hash
        chunk_id: Text chunk ID within the file
        text_content: Content of the matched text chunk
        score: Relevance score (higher = more relevant)
        highlights: Highlighted text fragments with <mark> tags
        model_version: Embedding model version used
    """
    
    file_md5: str = Field(..., description="File MD5 hash")
    chunk_id: int = Field(..., description="Text chunk ID")
    text_content: str = Field(..., description="Content text")
    score: float = Field(..., description="Relevance score")
    highlights: List[str] = Field(default=[], description="Highlighted fragments")
    model_version: Optional[str] = Field(None, description="Embedding model version")


class SearchMetadata(BaseModel):
    """
    Search metadata containing configuration used.
    
    Attributes:
        knn_weight: KNN weight used
        bm25_weight: BM25 weight used
        rrf_k: RRF constant used
        auto_adjusted: Whether weights were auto-adjusted
        multifield_enabled: Whether multi-field search was used
        field_boosts: Field boost values if multi-field enabled
    """
    
    knn_weight: Optional[float] = Field(None, description="KNN weight used")
    bm25_weight: Optional[float] = Field(None, description="BM25 weight used")
    rrf_k: Optional[int] = Field(None, description="RRF constant used")
    auto_adjusted: Optional[bool] = Field(None, description="Whether auto-adjusted")
    multifield_enabled: Optional[bool] = Field(None, description="Multi-field enabled")
    field_boosts: Optional[Dict[str, float]] = Field(None, description="Field boost values")
    mode: Optional[str] = Field(None, description="Search mode (knn/bm25)")
    execution_time_ms: Optional[float] = Field(None, description="Execution time")


class SearchResponse(BaseModel):
    """
    Search response model.
    
    Attributes:
        query: Original search query
        total_results: Number of results returned
        results: List of search results
        search_mode: Search mode used
        metadata: Search configuration and metadata
        timestamp: Search timestamp
        execution_time_ms: Total execution time in milliseconds
    """
    
    query: str = Field(..., description="Original query")
    total_results: int = Field(..., description="Total result count")
    results: List[SearchResult] = Field(..., description="Search results")
    search_mode: str = Field(..., description="Search mode used")
    metadata: SearchMetadata = Field(..., description="Search metadata")
    timestamp: datetime = Field(default_factory=datetime.now, description="Search timestamp")
    execution_time_ms: Optional[float] = Field(None, description="Execution time (ms)")


class SearchConfigResponse(BaseModel):
    """
    Search configuration response.
    
    Attributes:
        index_name: Elasticsearch index name
        weights: Hybrid search weight configuration
        field_boosts: Multi-field boost configuration
        limits: Result limits
        features: Feature flags
    """
    
    index_name: str = Field(..., description="ES index name")
    weights: Dict[str, Any] = Field(..., description="Hybrid weights (knn, bm25, rrf_k)")
    field_boosts: Dict[str, Any] = Field(..., description="Field boost values")
    limits: Dict[str, int] = Field(..., description="Result limits")
    features: Dict[str, bool] = Field(..., description="Feature flags")


class IndexInfoResponse(BaseModel):
    """
    Index information response.
    
    Attributes:
        exists: Whether the index exists
        index: Index name
        doc_count: Number of documents
        store_size_mb: Storage size in MB
        ik_available: Whether IK plugin is available
    """
    
    exists: bool = Field(..., description="Index exists")
    index: str = Field(..., description="Index name")
    doc_count: Optional[int] = Field(None, description="Document count")
    store_size_mb: Optional[float] = Field(None, description="Storage size (MB)")
    ik_available: Optional[bool] = Field(None, description="IK plugin available")
    error: Optional[str] = Field(None, description="Error message if any")


class AnalyzeRequest(BaseModel):
    """
    Text analysis request (for debugging).
    
    Attributes:
        text: Text to analyze
        analyzer: Analyzer name
    """
    
    text: str = Field(..., min_length=1, max_length=1000, description="Text to analyze")
    analyzer: str = Field(
        "chinese_smart",
        description="Analyzer: chinese_smart, chinese_max, english, standard"
    )
    
    @field_validator('analyzer')
    @classmethod
    def validate_analyzer(cls, v: str) -> str:
        """Validate analyzer name."""
        allowed = ["chinese_smart", "chinese_max", "english", "standard", "ik_smart", "ik_max_word"]
        if v not in allowed:
            raise ValueError(f"analyzer must be one of {allowed}")
        return v


class AnalyzeResponse(BaseModel):
    """
    Text analysis response.
    
    Attributes:
        success: Whether analysis succeeded
        analyzer: Analyzer used
        text: Original text
        tokens: List of tokens
        error: Error message if failed
    """
    
    success: bool = Field(..., description="Analysis succeeded")
    analyzer: str = Field(..., description="Analyzer used")
    text: str = Field(..., description="Original text")
    tokens: Optional[List[str]] = Field(None, description="Tokens")
    error: Optional[str] = Field(None, description="Error message")
