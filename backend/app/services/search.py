"""
Hybrid search service with multi-field support.
Implements KNN + BM25 hybrid search using Elasticsearch single query with RRF fusion.
Supports multi-field text indexing for Chinese and English content.
"""

from typing import List, Dict, Tuple, Optional
from elasticsearch import Elasticsearch
import time

from app.clients.gemini_embedding_client import GeminiEmbeddingClient
from app.core.search_config import search_config
from app.utils.logging import get_logger

logger = get_logger(__name__)


class HybridSearchService:
    """
    Hybrid search service with multi-field support.
    Implements vector search (KNN) + full-text search (BM25) with RRF fusion.
    Supports separate Chinese and English field analysis for better accuracy.
    """
    
    def __init__(
        self,
        es_client: Elasticsearch,
        embedding_client: GeminiEmbeddingClient,
        index_name: str = None
    ):
        """
        Initialize hybrid search service.
        
        Args:
            es_client: Elasticsearch client instance
            embedding_client: Embedding generation client
            index_name: Index name (defaults to config value)
        """
        self.es = es_client
        self.embedding_client = embedding_client
        self.index_name = index_name or search_config.ES_INDEX_NAME
        
        logger.info(f"HybridSearchService initialized with index: {self.index_name}")
    
    def _auto_adjust_weights(self, query: str) -> Tuple[float, float]:
        """
        Auto-adjust KNN/BM25 weights based on query features.
        
        Strategy:
        - Technical terms detected → Boost BM25 (precise matching)
        - Question/long query → Boost KNN (semantic understanding)
        - Default → Balanced
        
        Args:
            query: Query text
            
        Returns:
            Tuple of (knn_weight, bm25_weight)
        """
        # Technical terms that need precise matching
        technical_terms = [
            "PyTorch", "TensorFlow", "Keras", "API", "GPU", "CUDA",
            "Transformer", "BERT", "GPT", "Adam", "SGD", "ReLU",
            "CNN", "RNN", "LSTM", "ResNet", "VGG", "BatchNorm",
            "Dropout", "Softmax", "CrossEntropy", "MSE", "MAE"
        ]
        
        # Check for technical terms (case-sensitive for proper nouns)
        has_technical = any(term in query for term in technical_terms)
        
        # Check for question patterns
        question_words = ["how", "what", "why", "when", "where", "which",
                         "如何", "什么", "为什么", "怎么", "哪个", "哪些"]
        is_question = any(word in query.lower() for word in question_words)
        
        # Check query length (longer queries often need semantic understanding)
        is_long = len(query) > 50
        
        # Dynamic adjustment
        if has_technical:
            logger.info(f"Auto-adjust: Technical terms detected, boosting BM25")
            return 0.3, 0.7
        elif is_question or is_long:
            logger.info(f"Auto-adjust: Semantic query detected, boosting KNN")
            return 0.7, 0.3
        else:
            return 0.5, 0.5
    
    def _build_multifield_query(self, query: str) -> List[Dict]:
        """
        Build multi-field BM25 query clauses.
        
        Searches across:
        - textContent: Main field with Chinese analyzer (IK)
        - textContent.english: Sub-field with English stemming
        - textContent.standard: Sub-field with standard tokenizer
        
        Args:
            query: Search query text
            
        Returns:
            List of should clauses for bool query
        """
        field_boosts = search_config.get_field_boosts()
        
        clauses = [
            # Chinese field (main field with IK analyzer)
            {
                "match": {
                    "textContent": {
                        "query": query,
                        "boost": field_boosts["chinese"]
                    }
                }
            },
            # English field (with stemming)
            {
                "match": {
                    "textContent.english": {
                        "query": query,
                        "boost": field_boosts["english"]
                    }
                }
            },
            # Standard field (fallback)
            {
                "match": {
                    "textContent.standard": {
                        "query": query,
                        "boost": field_boosts["standard"]
                    }
                }
            }
        ]
        
        return clauses
    
    def _build_single_field_query(self, query: str) -> List[Dict]:
        """
        Build single-field BM25 query clause (fallback when multi-field disabled).
        
        Args:
            query: Search query text
            
        Returns:
            List containing single match clause
        """
        return [
            {
                "match": {
                    "textContent": {
                        "query": query,
                        "boost": 1.0
                    }
                }
            }
        ]
    
    def _build_highlight_config(self) -> Dict:
        """
        Build highlight configuration for search results.
        
        Returns:
            Dictionary containing highlight settings
        """
        highlight_config = {
            "fields": {
                "textContent": {
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"],
                    "fragment_size": search_config.HIGHLIGHT_FRAGMENT_SIZE,
                    "number_of_fragments": search_config.HIGHLIGHT_FRAGMENTS
                }
            }
        }
        
        # Add multi-field highlights if enabled
        if search_config.MULTIFIELD_ENABLED:
            highlight_config["fields"]["textContent.english"] = {
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
                "fragment_size": search_config.HIGHLIGHT_FRAGMENT_SIZE,
                "number_of_fragments": search_config.HIGHLIGHT_FRAGMENTS
            }
        
        return highlight_config
    
    def hybrid_search(
        self,
        query: str,
        top_k: int = None,
        knn_weight: float = None,
        bm25_weight: float = None,
        rrf_k: int = None,
        file_md5_filter: str = None,
        auto_adjust: bool = None,
        use_multifield: bool = None
    ) -> Tuple[List[Dict], Dict]:
        """
        Execute hybrid search with multi-field support.
        
        Process:
        1. Generate query vector using embedding client
        2. Build ES query with multi-field BM25 + KNN
        3. Use script_score to fuse results with RRF-style scoring
        4. Return merged and ranked results
        
        Args:
            query: Search query text
            top_k: Number of results (defaults to config)
            knn_weight: KNN weight override (None uses config)
            bm25_weight: BM25 weight override (None uses config)
            rrf_k: RRF constant override (None uses config)
            file_md5_filter: Filter by specific file MD5
            auto_adjust: Enable auto weight adjustment
            use_multifield: Enable multi-field search (None uses config)
            
        Returns:
            Tuple of (results list, search metadata dict)
        """
        start_time = time.time()
        
        # Apply default values from config
        top_k = top_k or search_config.DEFAULT_TOP_K
        auto_adjust = auto_adjust if auto_adjust is not None else search_config.AUTO_ADJUST_WEIGHTS
        use_multifield = use_multifield if use_multifield is not None else search_config.MULTIFIELD_ENABLED
        
        # Handle weight auto-adjustment
        if auto_adjust and knn_weight is None and bm25_weight is None:
            knn_weight, bm25_weight = self._auto_adjust_weights(query)
        else:
            knn_weight = knn_weight if knn_weight is not None else search_config.KNN_WEIGHT
            bm25_weight = bm25_weight if bm25_weight is not None else search_config.BM25_WEIGHT
        
        rrf_k = rrf_k if rrf_k is not None else search_config.RRF_K
        
        logger.info(
            f"Hybrid search: query='{query[:50]}...', "
            f"weights=(KNN:{knn_weight}, BM25:{bm25_weight}), "
            f"multifield={use_multifield}"
        )
        
        # Step 1: Generate query vector
        query_vector = self.embedding_client.embed([query])[0]
        
        # Step 2: Build BM25 query clauses (multi-field or single-field)
        if use_multifield:
            bm25_clauses = self._build_multifield_query(query)
        else:
            bm25_clauses = self._build_single_field_query(query)
        
        # Step 3: Build complete ES query with script_score fusion
        search_body = {
            "size": top_k,
            "query": {
                "script_score": {
                    "query": {
                        "bool": {
                            "should": bm25_clauses,
                            "minimum_should_match": 0,  # Allow pure vector matches
                            "filter": []
                        }
                    },
                    "script": {
                        # RRF-style fusion scoring
                        "source": """
                            // KNN: Cosine similarity (range: 0-2 after +1)
                            double knn_score = cosineSimilarity(params.query_vector, 'vector') + 1.0;
                            
                            // BM25: Multi-field best match score
                            double bm25_score = _score;
                            
                            // RRF-style fusion
                            // KNN contribution: direct weighted score
                            double knn_contribution = params.knn_weight * knn_score;
                            
                            // BM25 contribution: normalized to prevent dominance
                            double bm25_contribution = params.bm25_weight * (bm25_score / (params.rrf_k + bm25_score));
                            
                            // Final combined score
                            return knn_contribution + bm25_contribution;
                        """,
                        "params": {
                            "query_vector": query_vector,
                            "knn_weight": knn_weight,
                            "bm25_weight": bm25_weight,
                            "rrf_k": rrf_k
                        }
                    }
                }
            },
            "_source": ["fileMd5", "chunkId", "textContent", "modelVersion"]
        }
        
        # Add highlighting if enabled
        if search_config.HIGHLIGHT_ENABLED:
            search_body["highlight"] = self._build_highlight_config()
        
        # Add file filter if specified
        if file_md5_filter:
            search_body["query"]["script_score"]["query"]["bool"]["filter"].append({
                "term": {"fileMd5": file_md5_filter}
            })
        
        # Step 4: Execute search
        response = self.es.search(index=self.index_name, body=search_body)
        
        # Step 5: Parse results
        results = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            
            # Collect highlights from all fields
            highlights = []
            if "highlight" in hit:
                for field, frags in hit["highlight"].items():
                    highlights.extend(frags)
            
            result = {
                "file_md5": source.get("fileMd5"),
                "chunk_id": source.get("chunkId"),
                "text_content": source.get("textContent"),
                "score": hit["_score"],
                "highlights": highlights,
                "model_version": source.get("modelVersion")
            }
            results.append(result)
        
        # Build search metadata
        field_boosts = search_config.get_field_boosts() if use_multifield else None
        search_meta = {
            "knn_weight": knn_weight,
            "bm25_weight": bm25_weight,
            "rrf_k": rrf_k,
            "auto_adjusted": auto_adjust,
            "multifield_enabled": use_multifield,
            "field_boosts": field_boosts
        }
        
        elapsed = (time.time() - start_time) * 1000
        logger.info(f"Hybrid search completed: {len(results)} results in {elapsed:.2f}ms")
        
        return results, search_meta
    
    def knn_only_search(
        self,
        query: str,
        top_k: int = None,
        file_md5_filter: str = None
    ) -> Tuple[List[Dict], Dict]:
        """
        Pure KNN vector search (for comparison/fallback).
        
        Args:
            query: Search query text
            top_k: Number of results
            file_md5_filter: Filter by file MD5
            
        Returns:
            Tuple of (results list, search metadata)
        """
        start_time = time.time()
        top_k = top_k or search_config.DEFAULT_TOP_K
        
        # Generate query vector
        query_vector = self.embedding_client.embed([query])[0]
        
        # Build KNN-only query
        search_body = {
            "size": top_k,
            "query": {
                "script_score": {
                    "query": {"match_all": {}},
                    "script": {
                        "source": "cosineSimilarity(params.query_vector, 'vector') + 1.0",
                        "params": {"query_vector": query_vector}
                    }
                }
            },
            "_source": ["fileMd5", "chunkId", "textContent", "modelVersion"]
        }
        
        # Add file filter if specified
        if file_md5_filter:
            search_body["query"]["script_score"]["query"] = {
                "term": {"fileMd5": file_md5_filter}
            }
        
        response = self.es.search(index=self.index_name, body=search_body)
        
        results = [
            {
                "file_md5": hit["_source"]["fileMd5"],
                "chunk_id": hit["_source"]["chunkId"],
                "text_content": hit["_source"]["textContent"],
                "score": hit["_score"],
                "highlights": [],
                "model_version": hit["_source"].get("modelVersion")
            }
            for hit in response["hits"]["hits"]
        ]
        
        elapsed = (time.time() - start_time) * 1000
        search_meta = {
            "mode": "knn",
            "execution_time_ms": elapsed
        }
        
        return results, search_meta
    
    def bm25_only_search(
        self,
        query: str,
        top_k: int = None,
        file_md5_filter: str = None,
        use_multifield: bool = None
    ) -> Tuple[List[Dict], Dict]:
        """
        Pure BM25 keyword search with multi-field support.
        
        Args:
            query: Search query text
            top_k: Number of results
            file_md5_filter: Filter by file MD5
            use_multifield: Enable multi-field search
            
        Returns:
            Tuple of (results list, search metadata)
        """
        start_time = time.time()
        top_k = top_k or search_config.DEFAULT_TOP_K
        use_multifield = use_multifield if use_multifield is not None else search_config.MULTIFIELD_ENABLED
        
        # Build BM25 query
        if use_multifield:
            # Multi-match across all text fields
            field_boosts = search_config.get_field_boosts()
            query_clause = {
                "multi_match": {
                    "query": query,
                    "fields": [
                        f"textContent^{field_boosts['chinese']}",
                        f"textContent.english^{field_boosts['english']}",
                        f"textContent.standard^{field_boosts['standard']}"
                    ],
                    "type": "best_fields",
                    "tie_breaker": field_boosts["tie_breaker"],
                    "operator": "or"
                }
            }
        else:
            query_clause = {
                "match": {
                    "textContent": {
                        "query": query,
                        "operator": "or"
                    }
                }
            }
        
        search_body = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": [query_clause],
                    "filter": []
                }
            },
            "_source": ["fileMd5", "chunkId", "textContent", "modelVersion"]
        }
        
        # Add highlighting
        if search_config.HIGHLIGHT_ENABLED:
            search_body["highlight"] = self._build_highlight_config()
        
        # Add file filter if specified
        if file_md5_filter:
            search_body["query"]["bool"]["filter"].append({
                "term": {"fileMd5": file_md5_filter}
            })
        
        response = self.es.search(index=self.index_name, body=search_body)
        
        results = []
        for hit in response["hits"]["hits"]:
            highlights = []
            if "highlight" in hit:
                for field, frags in hit["highlight"].items():
                    highlights.extend(frags)
            
            results.append({
                "file_md5": hit["_source"]["fileMd5"],
                "chunk_id": hit["_source"]["chunkId"],
                "text_content": hit["_source"]["textContent"],
                "score": hit["_score"],
                "highlights": highlights,
                "model_version": hit["_source"].get("modelVersion")
            })
        
        elapsed = (time.time() - start_time) * 1000
        search_meta = {
            "mode": "bm25",
            "multifield_enabled": use_multifield,
            "execution_time_ms": elapsed
        }
        
        return results, search_meta
    
    def analyze_text(self, text: str, analyzer: str = "chinese_smart") -> Dict:
        """
        Analyze text with specified analyzer (for debugging).
        
        Args:
            text: Text to analyze
            analyzer: Analyzer name (chinese_smart, chinese_max, english, standard)
            
        Returns:
            Dictionary containing tokens
        """
        try:
            response = self.es.indices.analyze(
                index=self.index_name,
                body={
                    "analyzer": analyzer,
                    "text": text
                }
            )
            return {
                "analyzer": analyzer,
                "text": text,
                "tokens": [token["token"] for token in response["tokens"]]
            }
        except Exception as e:
            logger.error(f"Analyze failed: {e}")
            return {
                "analyzer": analyzer,
                "text": text,
                "error": str(e)
            }
