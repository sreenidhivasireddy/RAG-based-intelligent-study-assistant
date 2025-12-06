"""
Multi-field search integration test.
Tests the complete multi-field search functionality with Elasticsearch.

Requirements:
    - Elasticsearch 9.x running
    - IK Analysis plugin installed (optional but recommended)

Usage:
    1. Start ES: ./elasticsearch-9.2.0/bin/elasticsearch
    2. Run: python tests/test_multifield_search.py
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elasticsearch import Elasticsearch


# ==================== Configuration ====================

ES_HOST = os.getenv("ES_HOST", "localhost")
ES_PORT = os.getenv("ES_PORT", "9200")
ES_USER = os.getenv("ES_USER", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "your_password")
TEST_INDEX = "test_multifield_index"


def get_es_client():
    """Create ES client (no auth for local testing)"""
    return Elasticsearch(
        [f"http://{ES_HOST}:{ES_PORT}"]
    )


# ==================== Test Functions ====================

def test_es_connection(es: Elasticsearch) -> bool:
    """Test Elasticsearch connection"""
    print("=" * 60)
    print("Step 1: Test ES Connection")
    print("=" * 60)
    
    try:
        info = es.info()
        print(f"✅ ES connected successfully!")
        print(f"   Version: {info['version']['number']}")
        print(f"   Cluster: {info['cluster_name']}")
        return True
    except Exception as e:
        print(f"❌ ES connection failed: {e}")
        return False


def test_ik_plugin(es: Elasticsearch) -> bool:
    """Test if IK plugin is installed"""
    print()
    print("=" * 60)
    print("Step 2: Test IK Plugin")
    print("=" * 60)
    
    try:
        # Test ik_smart tokenizer
        response = es.indices.analyze(
            body={
                "tokenizer": "ik_smart",
                "text": "深度学习模型优化"
            }
        )
        tokens = [t["token"] for t in response["tokens"]]
        print(f"✅ IK plugin available!")
        print(f"   ik_smart tokens: {tokens}")
        
        # Test ik_max_word tokenizer
        response = es.indices.analyze(
            body={
                "tokenizer": "ik_max_word",
                "text": "深度学习模型优化"
            }
        )
        tokens = [t["token"] for t in response["tokens"]]
        print(f"   ik_max_word tokens: {tokens}")
        
        return True
    except Exception as e:
        print(f"⚠️ IK plugin not available: {e}")
        print(f"   Will use standard analyzer as fallback")
        return False


def create_multifield_index(es: Elasticsearch, use_ik: bool) -> bool:
    """Create test index with multi-field mapping"""
    print()
    print("=" * 60)
    print("Step 3: Create Multi-field Index")
    print("=" * 60)
    
    # Delete if exists
    if es.indices.exists(index=TEST_INDEX):
        es.indices.delete(index=TEST_INDEX)
        print(f"   Deleted existing index: {TEST_INDEX}")
    
    # Build mapping based on IK availability
    if use_ik:
        mapping = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "chinese_smart": {
                            "type": "custom",
                            "tokenizer": "ik_smart",
                            "filter": ["lowercase"]
                        },
                        "chinese_max": {
                            "type": "custom",
                            "tokenizer": "ik_max_word",
                            "filter": ["lowercase"]
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    "fileMd5": {"type": "keyword"},
                    "chunkId": {"type": "integer"},
                    "textContent": {
                        "type": "text",
                        "analyzer": "chinese_max",
                        "search_analyzer": "chinese_smart",
                        "fields": {
                            "english": {
                                "type": "text",
                                "analyzer": "english"
                            },
                            "standard": {
                                "type": "text",
                                "analyzer": "standard"
                            }
                        }
                    },
                    "vector": {
                        "type": "dense_vector",
                        "dims": 768,
                        "index": True,
                        "similarity": "cosine"
                    }
                }
            }
        }
    else:
        # Fallback mapping without IK
        mapping = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "mappings": {
                "properties": {
                    "fileMd5": {"type": "keyword"},
                    "chunkId": {"type": "integer"},
                    "textContent": {
                        "type": "text",
                        "analyzer": "standard",
                        "fields": {
                            "english": {
                                "type": "text",
                                "analyzer": "english"
                            }
                        }
                    },
                    "vector": {
                        "type": "dense_vector",
                        "dims": 768,
                        "index": True,
                        "similarity": "cosine"
                    }
                }
            }
        }
    
    try:
        es.indices.create(index=TEST_INDEX, body=mapping)
        print(f"✅ Created index: {TEST_INDEX}")
        print(f"   IK enabled: {use_ik}")
        return True
    except Exception as e:
        print(f"❌ Failed to create index: {e}")
        return False


def insert_test_data(es: Elasticsearch):
    """Insert test documents"""
    print()
    print("=" * 60)
    print("Step 4: Insert Test Data")
    print("=" * 60)
    
    # Test documents with mixed Chinese and English
    test_docs = [
        {
            "fileMd5": "file001",
            "chunkId": 1,
            "textContent": "PyTorch is a deep learning framework. It provides tensors and automatic differentiation.",
            "vector": [0.1] * 768
        },
        {
            "fileMd5": "file001",
            "chunkId": 2,
            "textContent": "To optimize PyTorch models, you can use Adam optimizer or SGD optimizer.",
            "vector": [0.15] * 768
        },
        {
            "fileMd5": "file002",
            "chunkId": 1,
            "textContent": "深度学习是人工智能的一个分支，使用神经网络进行模型训练。",
            "vector": [0.2] * 768
        },
        {
            "fileMd5": "file002",
            "chunkId": 2,
            "textContent": "PyTorch 提供了强大的自动微分功能，方便深度学习模型的训练和优化。",
            "vector": [0.25] * 768
        },
        {
            "fileMd5": "file003",
            "chunkId": 1,
            "textContent": "The optimization process involves adjusting model parameters to minimize loss.",
            "vector": [0.3] * 768
        },
        {
            "fileMd5": "file003",
            "chunkId": 2,
            "textContent": "使用 Adam optimizer 可以实现自适应学习率优化，适合训练深度神经网络。",
            "vector": [0.35] * 768
        },
    ]
    
    for doc in test_docs:
        es.index(index=TEST_INDEX, body=doc)
    
    es.indices.refresh(index=TEST_INDEX)
    count = es.count(index=TEST_INDEX)["count"]
    print(f"✅ Inserted {count} test documents")


def test_analyzer_comparison(es: Elasticsearch, use_ik: bool):
    """Compare different analyzers"""
    print()
    print("=" * 60)
    print("Step 5: Compare Analyzers")
    print("=" * 60)
    
    test_texts = [
        "PyTorch 深度学习模型优化",
        "optimization techniques for neural networks",
        "使用 Adam optimizer 训练模型"
    ]
    
    analyzers = ["standard", "english"]
    if use_ik:
        analyzers.extend(["chinese_smart", "chinese_max"])
    
    for text in test_texts:
        print(f"\nText: '{text}'")
        print("-" * 50)
        
        for analyzer in analyzers:
            try:
                if analyzer in ["chinese_smart", "chinese_max"]:
                    response = es.indices.analyze(
                        index=TEST_INDEX,
                        body={"analyzer": analyzer, "text": text}
                    )
                else:
                    response = es.indices.analyze(
                        body={"analyzer": analyzer, "text": text}
                    )
                tokens = [t["token"] for t in response["tokens"]]
                print(f"  {analyzer:15}: {tokens}")
            except Exception as e:
                print(f"  {analyzer:15}: Error - {e}")


def test_multifield_search(es: Elasticsearch):
    """Test multi-field BM25 search"""
    print()
    print("=" * 60)
    print("Step 6: Multi-field BM25 Search")
    print("=" * 60)
    
    queries = [
        "PyTorch optimizer",
        "深度学习 优化",
        "optimization neural network",
        "Adam 训练"
    ]
    
    for query in queries:
        print(f"\nQuery: '{query}'")
        print("-" * 50)
        
        # Multi-match across all fields
        search_body = {
            "size": 3,
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "textContent^1.0",
                        "textContent.english^0.8",
                        "textContent.standard^0.5"
                    ],
                    "type": "best_fields",
                    "tie_breaker": 0.3
                }
            },
            "highlight": {
                "fields": {
                    "textContent": {},
                    "textContent.english": {}
                }
            }
        }
        
        try:
            response = es.search(index=TEST_INDEX, body=search_body)
            hits = response["hits"]["hits"]
            
            print(f"  Results: {len(hits)}")
            for i, hit in enumerate(hits):
                score = hit["_score"]
                content = hit["_source"]["textContent"][:50]
                print(f"  [{i+1}] Score: {score:.4f} | {content}...")
                
                if "highlight" in hit:
                    for field, frags in hit["highlight"].items():
                        print(f"      Highlight ({field}): {frags[0][:60]}...")
        except Exception as e:
            print(f"  ❌ Search failed: {e}")


def test_english_stemming(es: Elasticsearch):
    """Test English stemming functionality"""
    print()
    print("=" * 60)
    print("Step 7: English Stemming Test")
    print("=" * 60)
    
    # Search for "optimizing" should match "optimization", "optimizer", etc.
    test_cases = [
        ("optimizing", ["optimization", "optimizer", "optimize"]),
        ("running", ["run", "runs", "ran"]),
        ("learning", ["learn", "learned", "learner"])
    ]
    
    for search_term, expected_matches in test_cases:
        print(f"\nSearch term: '{search_term}'")
        
        # Search using English analyzer field
        search_body = {
            "size": 5,
            "query": {
                "match": {
                    "textContent.english": search_term
                }
            }
        }
        
        try:
            response = es.search(index=TEST_INDEX, body=search_body)
            hits = response["hits"]["hits"]
            
            if hits:
                print(f"  ✅ Found {len(hits)} results")
                for hit in hits[:2]:
                    content = hit["_source"]["textContent"][:60]
                    print(f"     → {content}...")
            else:
                print(f"  ⚠️ No results found")
        except Exception as e:
            print(f"  ❌ Error: {e}")


def test_hybrid_search(es: Elasticsearch):
    """Test hybrid search with script_score"""
    print()
    print("=" * 60)
    print("Step 8: Hybrid Search (KNN + Multi-field BM25)")
    print("=" * 60)
    
    query = "PyTorch 深度学习"
    query_vector = [0.12] * 768
    
    search_body = {
        "size": 5,
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
                            },
                            {
                                "match": {
                                    "textContent.english": {
                                        "query": query,
                                        "boost": 0.8
                                    }
                                }
                            }
                        ],
                        "minimum_should_match": 0
                    }
                },
                "script": {
                    "source": """
                        double knn_score = cosineSimilarity(params.query_vector, 'vector') + 1.0;
                        double bm25_score = _score;
                        double knn_contrib = params.knn_weight * knn_score;
                        double bm25_contrib = params.bm25_weight * (bm25_score / (params.rrf_k + bm25_score));
                        return knn_contrib + bm25_contrib;
                    """,
                    "params": {
                        "query_vector": query_vector,
                        "knn_weight": 0.5,
                        "bm25_weight": 0.5,
                        "rrf_k": 60
                    }
                }
            }
        }
    }
    
    try:
        response = es.search(index=TEST_INDEX, body=search_body)
        hits = response["hits"]["hits"]
        
        print(f"Query: '{query}'")
        print(f"Weights: KNN=0.5, BM25=0.5, RRF_k=60")
        print(f"Results: {len(hits)}")
        print("-" * 50)
        
        for i, hit in enumerate(hits):
            content = hit["_source"]["textContent"][:60]
            print(f"[{i+1}] Hybrid Score: {hit['_score']:.4f}")
            print(f"    Content: {content}...")
            print()
        
        print("✅ Hybrid search works!")
    except Exception as e:
        print(f"❌ Hybrid search failed: {e}")


def cleanup(es: Elasticsearch):
    """Delete test index"""
    print()
    print("=" * 60)
    print("Cleanup")
    print("=" * 60)
    
    if es.indices.exists(index=TEST_INDEX):
        es.indices.delete(index=TEST_INDEX)
        print(f"✅ Deleted test index: {TEST_INDEX}")


def main():
    """Run all tests"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 12 + "MULTI-FIELD SEARCH TESTS" + " " * 22 + "║")
    print("║" + " " * 8 + "(Chinese IK + English Stemming)" + " " * 18 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    # Connect to ES
    es = get_es_client()
    
    if not test_es_connection(es):
        print("\n❌ Cannot proceed without ES connection")
        return
    
    # Check IK plugin
    ik_available = test_ik_plugin(es)
    
    try:
        # Run tests
        if not create_multifield_index(es, use_ik=ik_available):
            return
        
        insert_test_data(es)
        test_analyzer_comparison(es, use_ik=ik_available)
        test_multifield_search(es)
        test_english_stemming(es)
        test_hybrid_search(es)
        
        print()
        print("=" * 60)
        print("✅ ALL MULTI-FIELD TESTS COMPLETED!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        print()
        cleanup_choice = input("Delete test index? [y/N]: ").strip().lower()
        if cleanup_choice == 'y':
            cleanup(es)
        else:
            print(f"   Test index '{TEST_INDEX}' kept for inspection")


if __name__ == "__main__":
    main()

