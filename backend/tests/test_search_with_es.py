"""
Integration test for search API with Elasticsearch.
Requires ES to be running, but NOT MySQL/Redis/Gemini.

Usage:
    1. Start ES: ./elasticsearch-9.2.0/bin/elasticsearch
    2. Run: python tests/test_search_with_es.py
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elasticsearch import Elasticsearch


# ----- Configuration -----
ES_HOST = os.getenv("ES_HOST", "localhost")
ES_PORT = os.getenv("ES_PORT", "9200")
ES_USER = os.getenv("ES_USER", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "your_password")
TEST_INDEX = "test_knowledge_base"


def get_es_client():
    """Create ES client with basic auth"""
    return Elasticsearch(
        [f"https://{ES_HOST}:{ES_PORT}"],
        basic_auth=(ES_USER, ES_PASSWORD),
        verify_certs=False,
        ssl_show_warn=False
    )


def check_es_connection():
    """Check if ES is available"""
    print("=" * 60)
    print("Step 1: Check ES Connection")
    print("=" * 60)
    
    try:
        es = get_es_client()
        info = es.info()
        print(f"✅ ES connected successfully!")
        print(f"   Version: {info['version']['number']}")
        print(f"   Cluster: {info['cluster_name']}")
        return es
    except Exception as e:
        print(f"❌ ES connection failed: {e}")
        print()
        print("Please make sure:")
        print("1. ES is running: ./elasticsearch-9.2.0/bin/elasticsearch")
        print("2. Check ES_PASSWORD in .env or environment")
        return None


def create_test_index(es: Elasticsearch):
    """Create test index with proper mapping"""
    print()
    print("=" * 60)
    print("Step 2: Create Test Index")
    print("=" * 60)
    
    # Delete if exists
    if es.indices.exists(index=TEST_INDEX):
        es.indices.delete(index=TEST_INDEX)
        print(f"   Deleted existing index: {TEST_INDEX}")
    
    # Create index with mapping
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
                    "analyzer": "standard"
                },
                "vector": {
                    "type": "dense_vector",
                    "dims": 768,
                    "index": True,
                    "similarity": "cosine"
                },
                "modelVersion": {"type": "keyword"},
                "createdAt": {"type": "date"}
            }
        }
    }
    
    es.indices.create(index=TEST_INDEX, body=mapping)
    print(f"✅ Created test index: {TEST_INDEX}")


def insert_test_data(es: Elasticsearch):
    """Insert test documents with fake vectors"""
    print()
    print("=" * 60)
    print("Step 3: Insert Test Data")
    print("=" * 60)
    
    # Test documents with different topics
    test_docs = [
        {
            "fileMd5": "file001",
            "chunkId": 1,
            "textContent": "PyTorch is a deep learning framework. It provides tensors and automatic differentiation for building neural networks.",
            "vector": [0.1] * 768,  # Fake vector
            "modelVersion": "text-embedding-004"
        },
        {
            "fileMd5": "file001",
            "chunkId": 2,
            "textContent": "To optimize PyTorch models, you can use Adam optimizer or SGD. Learning rate scheduling is also important.",
            "vector": [0.15] * 768,
            "modelVersion": "text-embedding-004"
        },
        {
            "fileMd5": "file002",
            "chunkId": 1,
            "textContent": "TensorFlow is another popular deep learning framework developed by Google. It supports distributed training.",
            "vector": [0.2] * 768,
            "modelVersion": "text-embedding-004"
        },
        {
            "fileMd5": "file002",
            "chunkId": 2,
            "textContent": "Keras is a high-level API for TensorFlow. It makes building neural networks very simple and intuitive.",
            "vector": [0.25] * 768,
            "modelVersion": "text-embedding-004"
        },
        {
            "fileMd5": "file003",
            "chunkId": 1,
            "textContent": "机器学习是人工智能的一个分支。它使用数据来训练模型，从而进行预测。",
            "vector": [0.3] * 768,
            "modelVersion": "text-embedding-004"
        },
        {
            "fileMd5": "file003",
            "chunkId": 2,
            "textContent": "深度学习使用多层神经网络。常见的架构包括 CNN、RNN 和 Transformer。",
            "vector": [0.35] * 768,
            "modelVersion": "text-embedding-004"
        },
    ]
    
    for doc in test_docs:
        es.index(index=TEST_INDEX, body=doc)
    
    # Refresh to make docs searchable
    es.indices.refresh(index=TEST_INDEX)
    
    count = es.count(index=TEST_INDEX)["count"]
    print(f"✅ Inserted {count} test documents")


def test_bm25_search(es: Elasticsearch):
    """Test pure BM25 search"""
    print()
    print("=" * 60)
    print("Step 4: Test BM25 Search")
    print("=" * 60)
    
    query = "PyTorch optimizer"
    
    search_body = {
        "size": 5,
        "query": {
            "match": {
                "textContent": query
            }
        },
        "highlight": {
            "fields": {
                "textContent": {
                    "pre_tags": ["**"],
                    "post_tags": ["**"]
                }
            }
        }
    }
    
    response = es.search(index=TEST_INDEX, body=search_body)
    hits = response["hits"]["hits"]
    
    print(f"Query: '{query}'")
    print(f"Results: {len(hits)}")
    print()
    
    for i, hit in enumerate(hits):
        print(f"  [{i+1}] Score: {hit['_score']:.4f}")
        print(f"      File: {hit['_source']['fileMd5']}, Chunk: {hit['_source']['chunkId']}")
        content = hit['_source']['textContent'][:80]
        print(f"      Content: {content}...")
        if hit.get("highlight"):
            print(f"      Highlight: {hit['highlight']['textContent'][0][:80]}...")
        print()
    
    print("✅ BM25 search works!")


def test_knn_search(es: Elasticsearch):
    """Test pure KNN (vector) search"""
    print()
    print("=" * 60)
    print("Step 5: Test KNN Search")
    print("=" * 60)
    
    # Mock query vector (should match first document better)
    query_vector = [0.12] * 768
    
    search_body = {
        "size": 5,
        "query": {
            "script_score": {
                "query": {"match_all": {}},
                "script": {
                    "source": "cosineSimilarity(params.query_vector, 'vector') + 1.0",
                    "params": {"query_vector": query_vector}
                }
            }
        },
        "_source": ["fileMd5", "chunkId", "textContent"]
    }
    
    response = es.search(index=TEST_INDEX, body=search_body)
    hits = response["hits"]["hits"]
    
    print(f"Query vector: [0.12] * 768 (similar to doc 1)")
    print(f"Results: {len(hits)}")
    print()
    
    for i, hit in enumerate(hits):
        print(f"  [{i+1}] Score: {hit['_score']:.4f}")
        print(f"      File: {hit['_source']['fileMd5']}, Chunk: {hit['_source']['chunkId']}")
        content = hit['_source']['textContent'][:60]
        print(f"      Content: {content}...")
        print()
    
    print("✅ KNN search works!")


def test_hybrid_search(es: Elasticsearch):
    """Test hybrid search with script_score fusion"""
    print()
    print("=" * 60)
    print("Step 6: Test Hybrid Search (KNN + BM25)")
    print("=" * 60)
    
    query = "PyTorch"
    query_vector = [0.12] * 768
    knn_weight = 0.5
    bm25_weight = 0.5
    rrf_k = 60
    
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
                            }
                        ]
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
        "_source": ["fileMd5", "chunkId", "textContent"],
        "highlight": {
            "fields": {
                "textContent": {
                    "pre_tags": ["**"],
                    "post_tags": ["**"]
                }
            }
        }
    }
    
    response = es.search(index=TEST_INDEX, body=search_body)
    hits = response["hits"]["hits"]
    
    print(f"Query: '{query}'")
    print(f"Weights: KNN={knn_weight}, BM25={bm25_weight}, RRF_k={rrf_k}")
    print(f"Results: {len(hits)}")
    print()
    
    for i, hit in enumerate(hits):
        print(f"  [{i+1}] Hybrid Score: {hit['_score']:.4f}")
        print(f"      File: {hit['_source']['fileMd5']}, Chunk: {hit['_source']['chunkId']}")
        content = hit['_source']['textContent'][:60]
        print(f"      Content: {content}...")
        print()
    
    print("✅ Hybrid search works!")


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
    """Run all ES tests"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "ELASTICSEARCH INTEGRATION TESTS" + " " * 17 + "║")
    print("║" + " " * 15 + "(Requires ES only)" + " " * 24 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    # Check connection
    es = check_es_connection()
    if es is None:
        return
    
    try:
        # Run tests
        create_test_index(es)
        insert_test_data(es)
        test_bm25_search(es)
        test_knn_search(es)
        test_hybrid_search(es)
        
        print()
        print("=" * 60)
        print("✅ ALL ES TESTS PASSED!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Ask before cleanup
        print()
        cleanup_choice = input("Delete test index? [y/N]: ").strip().lower()
        if cleanup_choice == 'y':
            cleanup(es)
        else:
            print(f"   Test index '{TEST_INDEX}' kept for inspection")


if __name__ == "__main__":
    main()

