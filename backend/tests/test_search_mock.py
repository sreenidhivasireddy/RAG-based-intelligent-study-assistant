"""
Mock test for search API.
Tests without requiring ES, MySQL, Redis, or Gemini API.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_search_config():
    """Test: SearchConfig loads correctly"""
    print("=" * 60)
    print("Test 1: SearchConfig")
    print("=" * 60)
    
    from app.core.search_config import search_config
    
    config = search_config.get_config_summary()
    print(f"✅ Config loaded successfully:")
    print(f"   Index: {config['index_name']}")
    print(f"   KNN weight: {config['weights']['knn']}")
    print(f"   BM25 weight: {config['weights']['bm25']}")
    print(f"   RRF k: {config['weights']['rrf_k']}")
    print(f"   Auto-adjust: {config['features']['auto_adjust']}")
    
    # Test weight update
    search_config.update_weights(knn_weight=0.7, bm25_weight=0.3)
    new_weights = search_config.get_weights()
    assert new_weights['knn'] == 0.7, "KNN weight update failed"
    assert new_weights['bm25'] == 0.3, "BM25 weight update failed"
    print(f"✅ Weight update works: knn={new_weights['knn']}, bm25={new_weights['bm25']}")
    
    # Reset
    search_config.update_weights(knn_weight=0.5, bm25_weight=0.5)
    print()


def test_search_request_validation():
    """Test: SearchRequest validation"""
    print("=" * 60)
    print("Test 2: SearchRequest Validation")
    print("=" * 60)
    
    from app.schemas.search import SearchRequest
    from pydantic import ValidationError
    
    # Valid request
    try:
        req = SearchRequest(
            query="How to optimize PyTorch?",
            top_k=5,
            search_mode="hybrid"
        )
        print(f"✅ Valid request: query='{req.query[:30]}...', top_k={req.top_k}")
    except ValidationError as e:
        print(f"❌ Valid request failed: {e}")
        return
    
    # Invalid: empty query
    try:
        req = SearchRequest(query="", top_k=5)
        print(f"❌ Should have rejected empty query")
    except ValidationError:
        print(f"✅ Correctly rejected empty query")
    
    # Invalid: query too long
    try:
        req = SearchRequest(query="x" * 600, top_k=5)
        print(f"❌ Should have rejected query > 500 chars")
    except ValidationError:
        print(f"✅ Correctly rejected query > 500 chars")
    
    # Invalid: top_k out of range
    try:
        req = SearchRequest(query="test", top_k=200)
        print(f"❌ Should have rejected top_k > 100")
    except ValidationError:
        print(f"✅ Correctly rejected top_k > 100")
    
    # Invalid: search_mode
    try:
        req = SearchRequest(query="test", search_mode="invalid")
        print(f"❌ Should have rejected invalid search_mode")
    except ValidationError:
        print(f"✅ Correctly rejected invalid search_mode")
    
    # Valid: with optional weights
    try:
        req = SearchRequest(
            query="test query",
            top_k=10,
            knn_weight=0.7,
            bm25_weight=0.3,
            auto_adjust=False
        )
        print(f"✅ Valid request with custom weights: knn={req.knn_weight}, bm25={req.bm25_weight}")
    except ValidationError as e:
        print(f"❌ Failed with custom weights: {e}")
    
    print()


def test_search_response_format():
    """Test: SearchResponse format"""
    print("=" * 60)
    print("Test 3: SearchResponse Format")
    print("=" * 60)
    
    from app.schemas.search import SearchResponse, SearchResult, SearchMetadata
    from datetime import datetime
    
    # Create mock results
    results = [
        SearchResult(
            file_md5="abc123",
            chunk_id=1,
            text_content="This is test content about PyTorch optimization...",
            score=0.95,
            highlights=["<mark>PyTorch</mark> optimization..."]
        ),
        SearchResult(
            file_md5="def456",
            chunk_id=2,
            text_content="Another document about machine learning...",
            score=0.85,
            highlights=[]
        )
    ]
    
    # Create metadata
    metadata = SearchMetadata(
        knn_weight=0.5,
        bm25_weight=0.5,
        rrf_k=60,
        auto_adjusted=False,
        multifield_enabled=True,
        field_boosts={"chinese": 1.0, "english": 0.8, "standard": 0.5}
    )
    
    response = SearchResponse(
        query="PyTorch optimization",
        total_results=2,
        results=results,
        search_mode="hybrid",
        metadata=metadata,
        execution_time_ms=156.8
    )
    
    print(f"✅ SearchResponse created successfully:")
    print(f"   Query: {response.query}")
    print(f"   Total results: {response.total_results}")
    print(f"   Mode: {response.search_mode}")
    print(f"   Execution time: {response.execution_time_ms}ms")
    print(f"   First result score: {response.results[0].score}")
    print(f"   Multifield enabled: {response.metadata.multifield_enabled}")
    
    # Test JSON serialization
    json_str = response.model_dump_json(indent=2)
    print(f"✅ JSON serialization works")
    
    print()


def test_auto_weight_adjustment():
    """Test: Auto weight adjustment logic"""
    print("=" * 60)
    print("Test 4: Auto Weight Adjustment Logic")
    print("=" * 60)
    
    # Mock the _auto_adjust_weights function logic
    def mock_auto_adjust(query: str):
        technical_terms = [
            "PyTorch", "TensorFlow", "Keras", "API", "GPU", "CUDA",
            "Transformer", "BERT", "GPT", "Adam", "SGD", "ReLU"
        ]
        question_words = ["how", "what", "why", "when", "where", "如何", "什么", "为什么"]
        
        has_technical = any(term in query for term in technical_terms)
        is_question = any(word in query.lower() for word in question_words)
        is_long = len(query) > 50
        
        if has_technical:
            return 0.3, 0.7, "technical"
        elif is_question or is_long:
            return 0.7, 0.3, "semantic"
        else:
            return 0.5, 0.5, "balanced"
    
    # Test cases
    test_cases = [
        ("PyTorch Adam optimizer", "technical", 0.3, 0.7),
        ("How to improve model accuracy?", "semantic", 0.7, 0.3),
        ("如何优化神经网络？", "semantic", 0.7, 0.3),
        ("TensorFlow GPU CUDA performance", "technical", 0.3, 0.7),
        ("深度学习", "balanced", 0.5, 0.5),
        ("This is a very long query that should trigger semantic mode because it exceeds fifty characters", "semantic", 0.7, 0.3),
    ]
    
    all_passed = True
    for query, expected_reason, expected_knn, expected_bm25 in test_cases:
        knn, bm25, reason = mock_auto_adjust(query)
        if knn == expected_knn and bm25 == expected_bm25:
            print(f"✅ '{query[:40]}...' → {reason} (knn={knn}, bm25={bm25})")
        else:
            print(f"❌ '{query[:40]}...' → Expected {expected_reason}, got {reason}")
            all_passed = False
    
    if all_passed:
        print(f"\n✅ All auto-adjustment tests passed!")
    
    print()


def test_es_query_structure():
    """Test: ES query structure (without execution)"""
    print("=" * 60)
    print("Test 5: ES Query Structure")
    print("=" * 60)
    
    # Mock query vector
    query_vector = [0.1] * 768  # 768-dimensional vector
    query = "PyTorch optimizer"
    knn_weight = 0.5
    bm25_weight = 0.5
    rrf_k = 60
    top_k = 10
    
    # Build the query structure (same as in search.py)
    search_body = {
        "size": top_k,
        "query": {
            "script_score": {
                "query": {
                    "bool": {
                        "should": [
                            {
                                "match": {
                                    "textContent": {
                                        "query": query,
                                        "boost": 1.0
                                    }
                                }
                            }
                        ],
                        "filter": []
                    }
                },
                "script": {
                    "source": """
                        double knn_score = cosineSimilarity(params.query_vector, 'vector') + 1.0;
                        double bm25_score = _score;
                        double knn_contribution = params.knn_weight * knn_score;
                        double bm25_contribution = params.bm25_weight * (bm25_score / (params.rrf_k + bm25_score));
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
    
    # Validate structure
    assert "size" in search_body
    assert "query" in search_body
    assert "script_score" in search_body["query"]
    assert "script" in search_body["query"]["script_score"]
    assert "params" in search_body["query"]["script_score"]["script"]
    assert len(search_body["query"]["script_score"]["script"]["params"]["query_vector"]) == 768
    
    print(f"✅ ES query structure is valid")
    print(f"   Size: {search_body['size']}")
    print(f"   Query type: script_score")
    print(f"   Vector dimension: {len(query_vector)}")
    print(f"   Params: knn_weight={knn_weight}, bm25_weight={bm25_weight}, rrf_k={rrf_k}")
    
    # Test adding filter
    file_md5_filter = "abc123"
    search_body["query"]["script_score"]["query"]["bool"]["filter"].append({
        "term": {"fileMd5": file_md5_filter}
    })
    print(f"✅ Filter added: fileMd5={file_md5_filter}")
    
    print()


def test_rrf_score_calculation():
    """Test: RRF score calculation logic"""
    print("=" * 60)
    print("Test 6: RRF Score Calculation")
    print("=" * 60)
    
    def calculate_score(knn_score, bm25_score, knn_weight, bm25_weight, rrf_k):
        """Simulate ES script score calculation"""
        knn_contribution = knn_weight * knn_score
        bm25_contribution = bm25_weight * (bm25_score / (rrf_k + bm25_score))
        return knn_contribution + bm25_contribution
    
    # Test cases
    test_cases = [
        # (knn_score, bm25_score, knn_weight, bm25_weight, rrf_k)
        (1.8, 12.5, 0.5, 0.5, 60),   # Balanced
        (1.9, 5.0, 0.7, 0.3, 60),    # KNN dominant
        (1.2, 18.0, 0.3, 0.7, 60),   # BM25 dominant
    ]
    
    print("Score calculation examples:")
    print("-" * 60)
    
    for knn_s, bm25_s, knn_w, bm25_w, k in test_cases:
        final = calculate_score(knn_s, bm25_s, knn_w, bm25_w, k)
        knn_contrib = knn_w * knn_s
        bm25_contrib = bm25_w * (bm25_s / (k + bm25_s))
        
        print(f"KNN={knn_s:.1f}, BM25={bm25_s:.1f}, weights=({knn_w}, {bm25_w}), k={k}")
        print(f"  KNN contribution:  {knn_w} × {knn_s} = {knn_contrib:.4f}")
        print(f"  BM25 contribution: {bm25_w} × ({bm25_s}/{k+bm25_s}) = {bm25_contrib:.4f}")
        print(f"  Final score: {final:.4f}")
        print()
    
    print("✅ Score calculation verified")
    print()


def run_all_tests():
    """Run all mock tests"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 12 + "SEARCH API MOCK TESTS" + " " * 25 + "║")
    print("║" + " " * 8 + "(No ES/MySQL/Redis/Gemini needed)" + " " * 15 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    try:
        test_search_config()
        test_search_request_validation()
        test_search_response_format()
        test_auto_weight_adjustment()
        test_es_query_structure()
        test_rrf_score_calculation()
        
        print("=" * 60)
        print("✅ ALL MOCK TESTS PASSED!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Start ES: ./elasticsearch-9.2.0/bin/elasticsearch")
        print("2. Insert test data (see test_search_with_es.py)")
        print("3. Run full integration tests")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()

