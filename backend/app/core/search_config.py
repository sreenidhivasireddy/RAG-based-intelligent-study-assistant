"""
Search configuration management.
Reads search-related configurations from environment variables.
Supports multi-field indexing with Chinese and English analyzers.
"""

import os
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()


class SearchConfig:
    """
    Search configuration class.
    Manages all search-related settings including weights and parameters.
    Supports multi-field search with separate Chinese and English field boosts.
    """
    
    # ==================== Elasticsearch Configuration ====================
    ES_INDEX_NAME: str = os.getenv("ES_INDEX_NAME", "knowledge_base")
    
    # ==================== Hybrid Search Weights (KNN vs BM25) ====================
    KNN_WEIGHT: float = float(os.getenv("SEARCH_KNN_WEIGHT", "0.5"))
    BM25_WEIGHT: float = float(os.getenv("SEARCH_BM25_WEIGHT", "0.5"))
    
    # RRF (Reciprocal Rank Fusion) parameter
    RRF_K: int = int(os.getenv("SEARCH_RRF_K", "60"))
    
    # ==================== Multi-field Boost Configuration ====================
    # Field boost weights for BM25 multi-field search
    # Higher boost = more importance in scoring
    CHINESE_FIELD_BOOST: float = float(os.getenv("SEARCH_CHINESE_BOOST", "1.0"))
    ENGLISH_FIELD_BOOST: float = float(os.getenv("SEARCH_ENGLISH_BOOST", "0.8"))
    STANDARD_FIELD_BOOST: float = float(os.getenv("SEARCH_STANDARD_BOOST", "0.5"))
    
    # Multi-match tie breaker (0-1)
    # Controls how much other fields contribute to the score
    TIE_BREAKER: float = float(os.getenv("SEARCH_TIE_BREAKER", "0.3"))
    
    # Enable/disable multi-field search
    MULTIFIELD_ENABLED: bool = os.getenv("SEARCH_MULTIFIELD_ENABLED", "true").lower() == "true"
    
    # ==================== Search Result Configuration ====================
    DEFAULT_TOP_K: int = int(os.getenv("SEARCH_DEFAULT_TOP_K", "10"))
    MAX_TOP_K: int = int(os.getenv("SEARCH_MAX_TOP_K", "100"))
    
    # Search mode: hybrid, knn, bm25
    DEFAULT_MODE: str = os.getenv("SEARCH_DEFAULT_MODE", "hybrid")
    
    # ==================== Auto-adjust Configuration ====================
    AUTO_ADJUST_WEIGHTS: bool = os.getenv("SEARCH_AUTO_ADJUST_WEIGHTS", "true").lower() == "true"
    
    # ==================== Highlight Configuration ====================
    HIGHLIGHT_ENABLED: bool = os.getenv("SEARCH_HIGHLIGHT_ENABLED", "true").lower() == "true"
    HIGHLIGHT_FRAGMENT_SIZE: int = int(os.getenv("SEARCH_HIGHLIGHT_FRAGMENT_SIZE", "150"))
    HIGHLIGHT_FRAGMENTS: int = int(os.getenv("SEARCH_HIGHLIGHT_FRAGMENTS", "3"))
    
    # ==================== Methods ====================
    
    @classmethod
    def get_weights(cls) -> Dict[str, float]:
        """
        Get current hybrid search weight configuration.
        
        Returns:
            Dictionary containing knn_weight, bm25_weight, and rrf_k
        """
        return {
            "knn": cls.KNN_WEIGHT,
            "bm25": cls.BM25_WEIGHT,
            "rrf_k": cls.RRF_K
        }
    
    @classmethod
    def get_field_boosts(cls) -> Dict[str, float]:
        """
        Get multi-field boost configuration.
        
        Returns:
            Dictionary containing field boost values
        """
        return {
            "chinese": cls.CHINESE_FIELD_BOOST,
            "english": cls.ENGLISH_FIELD_BOOST,
            "standard": cls.STANDARD_FIELD_BOOST,
            "tie_breaker": cls.TIE_BREAKER
        }
    
    @classmethod
    def update_weights(
        cls, 
        knn_weight: float = None, 
        bm25_weight: float = None, 
        rrf_k: int = None
    ):
        """
        Update hybrid search weights at runtime (temporary, resets on restart).
        
        Args:
            knn_weight: KNN weight (0-1)
            bm25_weight: BM25 weight (0-1)
            rrf_k: RRF constant (1-200)
        """
        if knn_weight is not None:
            cls.KNN_WEIGHT = knn_weight
        if bm25_weight is not None:
            cls.BM25_WEIGHT = bm25_weight
        if rrf_k is not None:
            cls.RRF_K = rrf_k
    
    @classmethod
    def update_field_boosts(
        cls,
        chinese_boost: float = None,
        english_boost: float = None,
        standard_boost: float = None,
        tie_breaker: float = None
    ):
        """
        Update field boost weights at runtime (temporary, resets on restart).
        
        Args:
            chinese_boost: Chinese field boost (0-10)
            english_boost: English field boost (0-10)
            standard_boost: Standard field boost (0-10)
            tie_breaker: Tie breaker value (0-1)
        """
        if chinese_boost is not None:
            cls.CHINESE_FIELD_BOOST = chinese_boost
        if english_boost is not None:
            cls.ENGLISH_FIELD_BOOST = english_boost
        if standard_boost is not None:
            cls.STANDARD_FIELD_BOOST = standard_boost
        if tie_breaker is not None:
            cls.TIE_BREAKER = tie_breaker
    
    @classmethod
    def get_config_summary(cls) -> Dict:
        """
        Get complete configuration summary.
        
        Returns:
            Dictionary containing all configuration details
        """
        return {
            "index_name": cls.ES_INDEX_NAME,
            "weights": {
                "knn": cls.KNN_WEIGHT,
                "bm25": cls.BM25_WEIGHT,
                "rrf_k": cls.RRF_K
            },
            "field_boosts": {
                "chinese": cls.CHINESE_FIELD_BOOST,
                "english": cls.ENGLISH_FIELD_BOOST,
                "standard": cls.STANDARD_FIELD_BOOST,
                "tie_breaker": cls.TIE_BREAKER
            },
            "limits": {
                "default_top_k": cls.DEFAULT_TOP_K,
                "max_top_k": cls.MAX_TOP_K
            },
            "features": {
                "multifield": cls.MULTIFIELD_ENABLED,
                "auto_adjust": cls.AUTO_ADJUST_WEIGHTS,
                "highlight": cls.HIGHLIGHT_ENABLED
            }
        }


# Export configuration instance
search_config = SearchConfig()
