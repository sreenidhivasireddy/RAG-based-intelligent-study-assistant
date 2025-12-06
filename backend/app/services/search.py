"""
Hybrid search service with multi-field support.
Implements KNN + BM25 hybrid search using Elasticsearch single query with RRF fusion.
Supports multi-field text indexing for Chinese and English content.
"""

from typing import List, Dict, Tuple, Optional
from elasticsearch import Elasticsearch
import time
import re

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
            # ML/DL frameworks and tools
            "PyTorch", "TensorFlow", "Keras", "API", "GPU", "CUDA",
            "Transformer", "BERT", "GPT", "Adam", "SGD", "ReLU",
            "CNN", "RNN", "LSTM", "ResNet", "VGG", "BatchNorm",
            "Dropout", "Softmax", "CrossEntropy", "MSE", "MAE",
            # NLP/Linguistics terms
            "NLP", "natural language processing", "context free grammar", "CFG", 
            "finite state machine", "FSM", "regular expression", "regex", 
            "parse tree", "syntax tree", "morphology", "tokenization", 
            "lemmatization", "stemming", "POS tagging", "named entity", "NER", 
            "dependency parsing", "constituency", "BNF", "Chomsky", 
            "n-gram", "bigram", "trigram", "word embedding", "word2vec",
            "TF-IDF", "bag of words", "language model", "seq2seq"
        ]
        
        # Check for technical terms (case-insensitive for phrases, case-sensitive for acronyms)
        query_lower = query.lower()
        has_technical = any(
            term.lower() in query_lower if len(term) > 3 else term in query
            for term in technical_terms
        )
        
        # Check for question patterns
        question_words = ["how", "what", "why", "when", "where", "which",
                         "如何", "什么", "为什么", "怎么", "哪个", "哪些"]
        is_question = any(word in query.lower() for word in question_words)
        
        # Check query length (longer queries often need semantic understanding)
        is_long = len(query) > 50
        
        # Dynamic adjustment with combined logic
        # 组合判断：同时考虑技术术语和问句特征
        if has_technical and (is_question or is_long):
            # 长句子/问句 + 专业术语 → 平衡但偏向 BM25
            # 例如: "How does context free grammar work?"
            logger.info(f"Auto-adjust: Technical question detected, balanced with BM25 bias (0.35/0.65)")
            return 0.35, 0.65
        elif has_technical:
            # 纯技术术语查询 → 重 BM25
            # 例如: "context free grammar"
            logger.info(f"Auto-adjust: Technical terms detected, boosting BM25 (0.2/0.8)")
            return 0.2, 0.8
        elif is_question or is_long:
            # 一般性问句/长查询 → 重 KNN (语义理解)
            # 例如: "How to improve model performance?"
            logger.info(f"Auto-adjust: Semantic query detected, boosting KNN (0.7/0.3)")
            return 0.7, 0.3
        else:
            # 默认平衡
            return 0.5, 0.5
    
    def _build_multifield_query(self, query: str) -> List[Dict]:
        """
        Build multi-field BM25 query clauses.
        
        Searches across:
        - text_content: Main field with Chinese analyzer (IK)
        - text_content.english: Sub-field with English stemming
        - text_content.standard: Sub-field with standard tokenizer
        
        Also adds phrase matching for multi-word queries to boost exact matches.
        
        Args:
            query: Search query text
            
        Returns:
            List of should clauses for bool query
        """
        field_boosts = search_config.get_field_boosts()
        
        # 过滤停用词后的查询 - 用于更精确的匹配
        filtered_query = self._filter_stopwords(query)
        filtered_word_count = len(filtered_query.split())
        
        # 根据查询长度调整匹配策略
        # 短查询（<5词）：严格匹配 50%
        # 长查询（≥5词）：宽松匹配，至少匹配 2 个关键词
        if filtered_word_count < 5:
            min_match = "50%"
        else:
            min_match = "2"  # 长查询只需匹配至少 2 个词
        
        logger.debug(f"Query length: {filtered_word_count} words, minimum_should_match: {min_match}")
        
        clauses = [
            # Chinese field (main field with IK analyzer)
            {
                "match": {
                    "text_content": {
                        "query": filtered_query,  # 使用过滤后的查询
                        "boost": field_boosts["chinese"],
                        "minimum_should_match": min_match
                    }
                }
            },
            # English field (with stemming)
            {
                "match": {
                    "text_content.english": {
                        "query": filtered_query,
                        "boost": field_boosts["english"],
                        "minimum_should_match": min_match
                    }
                }
            },
            # Standard field (fallback) - 使用原查询作为兜底
            {
                "match": {
                    "text_content.standard": {
                        "query": query,
                        "boost": field_boosts["standard"]
                    }
                }
            }
        ]
        
        # 添加短语匹配：如果过滤后的查询包含多个词，增加精确短语匹配提升
        filtered_words = filtered_query.split()
        if len(filtered_words) >= 2:
            # 短语匹配 - 大幅提升包含完整短语的文档
            clauses.append({
                "match_phrase": {
                    "text_content": {
                        "query": filtered_query,
                        "boost": 3.0,  # 短语匹配权重是普通匹配的3倍
                        "slop": 2      # 允许词之间有2个词的间隔
                    }
                }
            })
            clauses.append({
                "match_phrase": {
                    "text_content.english": {
                        "query": filtered_query,
                        "boost": 2.5,
                        "slop": 2
                    }
                }
            })
        
        return clauses
    
    def _build_single_field_query(self, query: str) -> List[Dict]:
        """
        Build single-field BM25 query clause (fallback when multi-field disabled).
        
        Args:
            query: Search query text
            
        Returns:
            List containing single match clause
        """
        # 过滤停用词
        filtered_query = self._filter_stopwords(query)
        filtered_word_count = len(filtered_query.split())
        
        # 根据查询长度调整匹配策略
        if filtered_word_count < 5:
            min_match = "50%"
        else:
            min_match = "2"
        
        clauses = [
            {
                "match": {
                    "text_content": {
                        "query": filtered_query,
                        "boost": 1.0,
                        "minimum_should_match": min_match
                    }
                }
            }
        ]
    
        # 添加短语匹配
        if filtered_word_count >= 2:
            clauses.append({
                "match_phrase": {
                    "text_content": {
                        "query": filtered_query,
                        "boost": 3.0,
                        "slop": 2
                    }
                }
            })
        
        return clauses
    
    def _get_plural_variants(self, query: str) -> List[str]:
        """
        Get plural/singular variants of terms in query for highlighting.
        
        Args:
            query: Query text
            
        Returns:
            List of plural/singular variants to highlight
        """
        variants = []
        words = re.findall(r'\b\w+\b', query)  # Extract words from query
        
        for word in words:
            if len(word) >= 2:  # Skip single characters
                if word.endswith('s') and len(word) > 2:
                    # Add singular form (remove 's')
                    variants.append(word[:-1])
                else:
                    # Add plural form (add 's')
                    variants.append(word + 's')
        
        return list(set(variants))  # Remove duplicates
    
    def _filter_stopwords(self, query: str) -> str:
        """
        Filter out common stop words from query for better highlighting.
        
        Args:
            query: Original query text
            
        Returns:
            Query with stop words removed
        """
        # Common English stop words that shouldn't be highlighted
        stop_words = {
            # Question words
            "how", "what", "why", "when", "where", "which", "who", "whom",
            # Common verbs
            "is", "are", "was", "were", "be", "been", "being",
            "do", "does", "did", "doing", "done",
            "have", "has", "had", "having",
            "can", "could", "will", "would", "shall", "should", "may", "might", "must",
            "work", "works", "working", "worked",
            # Articles and prepositions
            "a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by", "from",
            "about", "into", "through", "during", "before", "after", "above", "below",
            # Conjunctions
            "and", "or", "but", "if", "then", "else", "so", "because",
            # Pronouns
            "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
            "this", "that", "these", "those",
            # Others
            "not", "no", "yes", "all", "any", "some", "more", "most", "other", "such",
            # Additional common words
            "as"
        }
        
        # 移除标点符号并过滤停用词
        words = re.findall(r'\b\w+\b', query)  # 只提取单词，去除标点
        filtered = [w for w in words if w.lower() not in stop_words]
        
        return " ".join(filtered) if filtered else query
    
    def _build_highlight_config(self, query: str = None) -> Dict:
        """
        Build highlight configuration for search results.
        Only highlights meaningful terms (filters out stop words).
        
        Args:
            query: Original query for custom highlight query
        
        Returns:
            Dictionary containing highlight settings
        """
        highlight_config = {
            "fields": {
                "text_content": {
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"],
                    "fragment_size": search_config.HIGHLIGHT_FRAGMENT_SIZE,
                    "number_of_fragments": search_config.HIGHLIGHT_FRAGMENTS
                }
            }
        }
        
        # Add multi-field highlights if enabled
        if search_config.MULTIFIELD_ENABLED:
            highlight_config["fields"]["text_content.english"] = {
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
                "fragment_size": search_config.HIGHLIGHT_FRAGMENT_SIZE,
                "number_of_fragments": search_config.HIGHLIGHT_FRAGMENTS
            }
        
        # Use filtered query for highlighting (removes stop words)
        # Also add plural/singular variants (e.g., CFG → CFGs)
        if query:
            filtered_query = self._filter_stopwords(query)
            plural_variants = self._get_plural_variants(query)
            
            # Build highlight query with filtered terms + expanded abbreviations
            should_clauses = [
                {"match": {"text_content": filtered_query}},
                {"match": {"text_content.english": filtered_query}}
            ]
            
            # Add plural/singular variants
            for term in plural_variants:
                should_clauses.append({"match_phrase": {"text_content": term}})
                should_clauses.append({"match_phrase": {"text_content.english": term}})
            
            highlight_config["highlight_query"] = {
                "bool": {
                    "should": should_clauses
                    }
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
                        # RRF-style fusion scoring with phrase boost awareness
                        "source": """
                            // KNN: Cosine similarity (range: 0-2 after +1)
                            double knn_score = cosineSimilarity(params.query_vector, 'vector') + 1.0;
                            
                            // BM25: Multi-field best match score (includes phrase match boost)
                            double bm25_score = _score;
                            
                            // RRF-style fusion
                            // KNN contribution: direct weighted score
                            double knn_contribution = params.knn_weight * knn_score;
                            
                            // BM25 contribution: use log scaling to preserve phrase match advantage
                            // Higher BM25 scores (from phrase matches) will have proportionally more impact
                            double bm25_normalized = Math.log1p(bm25_score) / Math.log1p(params.rrf_k);
                            double bm25_contribution = params.bm25_weight * bm25_normalized;
                            
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
            "_source": ["file_md5", "chunk_id", "text_content", "model_version"]
        }
        
        # Add highlighting if enabled
        if search_config.HIGHLIGHT_ENABLED:
            search_body["highlight"] = self._build_highlight_config(query)
        
        # Add file filter if specified
        if file_md5_filter:
            search_body["query"]["script_score"]["query"]["bool"]["filter"].append({
                "term": {"file_md5": file_md5_filter}
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
                "file_md5": source.get("file_md5"),
                "chunk_id": source.get("chunk_id"),
                "text_content": source.get("text_content"),
                "score": hit["_score"],
                "highlights": highlights,
                "model_version": source.get("model_version")
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
            "_source": ["file_md5", "chunk_id", "text_content", "model_version"]
        }
        
        # Add file filter if specified
        if file_md5_filter:
            search_body["query"]["script_score"]["query"] = {
                "term": {"file_md5": file_md5_filter}
            }
        
        response = self.es.search(index=self.index_name, body=search_body)
        
        results = [
            {
                "file_md5": hit["_source"]["file_md5"],
                "chunk_id": hit["_source"]["chunk_id"],
                "text_content": hit["_source"]["text_content"],
                "score": hit["_score"],
                "highlights": [],
                "model_version": hit["_source"].get("model_version")
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
                        f"text_content^{field_boosts['chinese']}",
                        f"text_content.english^{field_boosts['english']}",
                        f"text_content.standard^{field_boosts['standard']}"
                    ],
                    "type": "best_fields",
                    "tie_breaker": field_boosts["tie_breaker"],
                    "operator": "or"
                }
            }
        else:
            query_clause = {
                "match": {
                    "text_content": {
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
            "_source": ["file_md5", "chunk_id", "text_content", "model_version"]
        }
        
        # Add highlighting
        if search_config.HIGHLIGHT_ENABLED:
            search_body["highlight"] = self._build_highlight_config(query)
        
        # Add file filter if specified
        if file_md5_filter:
            search_body["query"]["bool"]["filter"].append({
                "term": {"file_md5": file_md5_filter}
            })
        
        response = self.es.search(index=self.index_name, body=search_body)
        
        results = []
        for hit in response["hits"]["hits"]:
            highlights = []
            if "highlight" in hit:
                for field, frags in hit["highlight"].items():
                    highlights.extend(frags)
            
            results.append({
                "file_md5": hit["_source"]["file_md5"],
                "chunk_id": hit["_source"]["chunk_id"],
                "text_content": hit["_source"]["text_content"],
                "score": hit["_score"],
                "highlights": highlights,
                "model_version": hit["_source"].get("model_version")
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
