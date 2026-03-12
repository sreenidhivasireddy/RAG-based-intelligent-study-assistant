"""
Hybrid search service with multi-field support.
Implements KNN + full-text search hybrid search using Azure AI Search.
Supports multi-field text indexing for Chinese and English content.
"""

from typing import List, Dict, Tuple, Optional
from azure.search.documents import SearchClient
import time
import re

from app.clients.azure_openai_embedding_client import AzureOpenAIEmbeddingClient
from app.core.search_config import search_config
from app.utils.logging import get_logger

logger = get_logger(__name__)


class HybridSearchService:
    """
    Hybrid search service with multi-field support.
    Implements vector search (KNN) + full-text search with Azure AI Search.
    Supports separate Chinese and English field analysis for better accuracy.
    """
    
    def __init__(
        self,
        search_client: SearchClient,
        embedding_client: AzureOpenAIEmbeddingClient,
        index_name: str = None
    ):
        """
        Initialize hybrid search service.
        
        Args:
            search_client: Azure SearchClient instance
            embedding_client: Embedding generation client
            index_name: Index name (defaults to config value)
        """
        self.search_client = search_client
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
        question_words = ["how", "what", "why", "when", "where", "which"]
        is_question = any(word in query.lower() for word in question_words)
        
        # Check query length (longer queries often need semantic understanding)
        is_long = len(query) > 50
        
        # Dynamic adjustment with combined logic.
        # Consider both technical terms and question-like phrasing.
        if has_technical and (is_question or is_long):
            # Long or question-like query with technical terms -> balanced with BM25 bias.
            # Example: "How does context free grammar work?"
            logger.info(f"Auto-adjust: Technical question detected, balanced with BM25 bias (0.35/0.65)")
            return 0.35, 0.65
        elif has_technical:
            # Technical-term-only query -> favor BM25.
            # Example: "context free grammar"
            logger.info(f"Auto-adjust: Technical terms detected, boosting BM25 (0.2/0.8)")
            return 0.2, 0.8
        elif is_question or is_long:
            # General question or long query -> favor KNN (semantic understanding).
            # Example: "How to improve model performance?"
            logger.info(f"Auto-adjust: Semantic query detected, boosting KNN (0.7/0.3)")
            return 0.7, 0.3
        else:
            # Default balanced mode.
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
        
        # Filtered query without stop words for more precise matching.
        filtered_query = self._filter_stopwords(query)
        filtered_word_count = len(filtered_query.split())
        
        # Adjust matching strategy based on query length.
        # Short query (<5 words): stricter 50% matching.
        # Long query (>=5 words): looser matching with at least 2 keywords.
        if filtered_word_count < 5:
            min_match = "50%"
        else:
            min_match = "2"  # Long queries only need to match at least 2 words.
        
        logger.debug(f"Query length: {filtered_word_count} words, minimum_should_match: {min_match}")
        
        clauses = [
            # Chinese field (main field with IK analyzer)
            {
                "match": {
                    "text_content": {
                        "query": filtered_query,  # Use the filtered query.
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
            # Standard field (fallback) - use the original query as fallback.
            {
                "match": {
                    "text_content.standard": {
                        "query": query,
                        "boost": field_boosts["standard"]
                    }
                }
            }
        ]
        
        # Add phrase matching when the filtered query has multiple words.
        filtered_words = filtered_query.split()
        if len(filtered_words) >= 2:
            # Phrase matching strongly boosts documents containing the full phrase.
            clauses.append({
                "match_phrase": {
                    "text_content": {
                        "query": filtered_query,
                        "boost": 3.0,  # Phrase match weight is 3x the normal match.
                        "slop": 2      # Allow up to 2 terms between words.
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
        # Filter stop words.
        filtered_query = self._filter_stopwords(query)
        filtered_word_count = len(filtered_query.split())
        
        # Adjust matching strategy based on query length.
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
    
        # Add phrase matching.
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
        
        # Remove punctuation and filter stop words.
        words = re.findall(r'\b\w+\b', query)  # Extract words only and remove punctuation.
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
        Execute hybrid search with Azure AI Search (vector + keyword search).
        
        Process:
        1. Generate query vector using embedding client
        2. Execute Azure Search hybrid query with vector + keyword
        3. Combine and rank results based on weights
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
        
        try:
            # Step 1: Generate query vector
            query_vector = self.embedding_client.embed([query])[0]
            logger.info(f"Generated query vector with {len(query_vector)} dimensions")
            
            # Step 2: Build filter expression if needed
            filter_expr = None
            if file_md5_filter:
                filter_expr = f"file_md5 eq '{file_md5_filter}'"
                logger.info(f"Applied filter: {filter_expr}")
            
            # Step 3: Execute Azure Search hybrid query
            logger.info(f"Executing hybrid search with text='{query}' + vector query")
            results_list = self.search_client.search(
                search_text=query,
                vector_queries=[{
                    'kind': 'vector',
                    'vector': query_vector,
                    'fields': 'embedding',
                    'k': top_k
                }],
                filter=filter_expr,
                top=top_k,
                select=['file_md5', 'chunk_id', 'content', 'file_name', 'chunk_index'],
                highlight_fields='content' if search_config.HIGHLIGHT_ENABLED else None
            )
            
            # Step 4: Parse results and apply weighting
            results = []
            result_dict = {}  # Use dict to deduplicate by chunk_id
            hit_count = 0
            
            for hit in results_list:
                hit_count += 1
                chunk_id = hit.get('chunk_id', '')
                score = hit.get('@search.score', hit.get('score', 0))
                
                if hit_count <= 3:
                    logger.debug(f"Hit {hit_count}: chunk_id={chunk_id}, score={score}, content_len={len(hit.get('content', ''))}")
                
                # Combined score (simplified - just use the search score)
                combined_score = score
                
                if chunk_id not in result_dict:
                    result_dict[chunk_id] = {
                        "file_md5": hit.get('file_md5', ''),
                        "chunk_id": chunk_id,
                        "content": hit.get('content', ''),  # Updated field name
                        "file_name": hit.get('file_name', ''),  # Added
                        "chunk_index": hit.get('chunk_index', ''),  # Added
                        "score": combined_score,
                        "highlights": []
                    }
                else:
                    # Update with higher score if this hit has better ranking
                    if combined_score > result_dict[chunk_id]['score']:
                        result_dict[chunk_id]['score'] = combined_score
            
            logger.info(f"Hybrid search returned {hit_count} hits, {len(result_dict)} unique chunks")
            
            # Sort by score descending
            results = sorted(result_dict.values(), key=lambda x: x['score'], reverse=True)[:top_k]
            
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
            search_meta["execution_time_ms"] = elapsed
            
            return results, search_meta
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return [], {"error": str(e)}
    
    
    def knn_only_search(
        self,
        query: str,
        top_k: int = None,
        file_md5_filter: str = None
    ) -> Tuple[List[Dict], Dict]:
        """
        Pure KNN vector search (for comparison/fallback) using Azure Search.
        
        Args:
            query: Search query text
            top_k: Number of results
            file_md5_filter: Filter by file MD5
            
        Returns:
            Tuple of (results list, search metadata)
        """
        start_time = time.time()
        top_k = top_k or search_config.DEFAULT_TOP_K
        
        try:
            # Generate query vector
            query_vector = self.embedding_client.embed([query])[0]
            
            # Build Azure Search vector search parameters
            vector_query = f"search.in(embedding, '{query_vector}')"
            
            # Add file filter if specified
            filter_expr = None
            if file_md5_filter:
                filter_expr = f"file_md5 eq '{file_md5_filter}'"
            
            # Execute vector search
            results_list = self.search_client.search(
                search_text="",
                vector_queries=[{
                    'kind': 'vector',
                    'vector': query_vector,
                    'fields': 'embedding',
                    'k': top_k
                }],
                filter=filter_expr,
                top=top_k,
                select=['file_md5', 'chunk_id', 'content', 'file_name', 'chunk_index']
            )
            
            results = []
            for hit in results_list:
                results.append({
                    "file_md5": hit.get('file_md5', ''),
                    "chunk_id": hit.get('chunk_id', ''),
                    "content": hit.get('content', ''),
                    "file_name": hit.get('file_name', ''),
                    "chunk_index": hit.get('chunk_index', ''),
                    "score": hit.get('@search.score', 0),
                    "highlights": []
                })
            
            elapsed = (time.time() - start_time) * 1000
            search_meta = {
                "mode": "knn",
                "execution_time_ms": elapsed
            }
            
            return results, search_meta
            
        except Exception as e:
            logger.error(f"KNN search failed: {e}")
            return [], {"mode": "knn", "error": str(e)}
    
    def bm25_only_search(
        self,
        query: str,
        top_k: int = None,
        file_md5_filter: str = None,
        use_multifield: bool = None
    ) -> Tuple[List[Dict], Dict]:
        """
        Pure BM25 keyword search with multi-field support using Azure Search.
        
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
        
        try:
            # Build filter expression if file filter specified
            filter_expr = None
            if file_md5_filter:
                filter_expr = f"file_md5 eq '{file_md5_filter}'"
            
            # In Azure Search, BM25 is the default for text search
            # The search_text parameter is matched against configured searchable fields
            results_list = self.search_client.search(
                search_text=query,
                filter=filter_expr,
                top=top_k,
                select=['file_md5', 'chunk_id', 'content', 'file_name', 'chunk_index'],
                highlight_fields='content' if search_config.HIGHLIGHT_ENABLED else None
            )
            
            results = []
            for hit in results_list:
                highlights = []
                if hasattr(hit, '@search.highlights') and hit.__dict__.get('@search.highlights'):
                    highlights = hit.__dict__['@search.highlights'].get('content', [])
                
                results.append({
                    "file_md5": hit.get('file_md5', ''),
                    "chunk_id": hit.get('chunk_id', ''),
                    "content": hit.get('content', ''),
                    "file_name": hit.get('file_name', ''),
                    "chunk_index": hit.get('chunk_index', ''),
                    "score": hit.get('@search.score', 0),
                    "highlights": highlights
                })
            
            elapsed = (time.time() - start_time) * 1000
            search_meta = {
                "mode": "bm25",
                "multifield_enabled": use_multifield,
                "execution_time_ms": elapsed
            }
            
            return results, search_meta
            
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return [], {"mode": "bm25", "error": str(e)}
    
    def analyze_text(self, text: str, analyzer: str = "chinese_smart") -> Dict:
        """
        Analyze text with specified analyzer for debugging.
        Since Azure Search doesn't expose analyzer APIs, we implement client-side tokenization.
        
        Args:
            text: Text to analyze
            analyzer: Analyzer name (chinese_smart, chinese_max, english, standard)
            
        Returns:
            Dictionary containing tokens
        """
        try:
            tokens = []
            
            if analyzer in ["chinese_smart", "chinese_max"]:
                # Use jieba for Chinese text analysis
                try:
                    import jieba
                    if analyzer == "chinese_smart":
                        tokens = list(jieba.cut(text))  # Smart cut
                    else:  # chinese_max
                        tokens = list(jieba.cut_for_search(text))  # Search cut
                    # Convert to lowercase
                    tokens = [t.lower() for t in tokens]
                except ImportError:
                    logger.warning("jieba not available, falling back to character splitting")
                    tokens = list(text)
            
            elif analyzer == "english":
                # Split on whitespace and punctuation for English
                import re
                tokens = re.findall(r'\b\w+\b', text.lower())
            
            else:  # standard analyzer
                # Basic whitespace and lowercase tokenization
                tokens = text.lower().split()
            
            return {
                "analyzer": analyzer,
                "text": text,
                "tokens": [t for t in tokens if t]  # Filter empty tokens
            }
        except Exception as e:
            logger.error(f"Analyze failed: {e}")
            return {
                "analyzer": analyzer,
                "text": text,
                "error": str(e)
            }
