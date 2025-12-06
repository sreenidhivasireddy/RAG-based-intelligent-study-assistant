"""
Test script for hybrid search functionality.
Run this after starting the server to verify search is working.
"""

import requests
import json

BASE_URL = "http://localhost:8000/api/v1"


def test_search_config():
    """Test: Get search configuration"""
    print("=" * 60)
    print("Test 1: Get Search Configuration")
    print("=" * 60)
    
    response = requests.get(f"{BASE_URL}/search/config")
    
    if response.status_code == 200:
        config = response.json()
        print("✅ Configuration retrieved successfully")
        print(json.dumps(config, indent=2))
    else:
        print(f"❌ Failed with status code: {response.status_code}")
        print(response.text)
    
    print()


def test_hybrid_search():
    """Test: Basic hybrid search"""
    print("=" * 60)
    print("Test 2: Basic Hybrid Search")
    print("=" * 60)
    
    payload = {
        "query": "How to optimize PyTorch models?",
        "top_k": 5,
        "search_mode": "hybrid"
    }
    
    response = requests.post(f"{BASE_URL}/search/", json=payload)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Search completed successfully")
        print(f"   Query: {data['query']}")
        print(f"   Results: {data['total_results']}")
        print(f"   Execution time: {data['execution_time_ms']:.2f}ms")
        print(f"   Weights used: {data['weights_used']}")
        
        if data['results']:
            print(f"\n   Top result:")
            print(f"   Score: {data['results'][0]['score']:.4f}")
            print(f"   Text: {data['results'][0]['text_content'][:100]}...")
    else:
        print(f"❌ Failed with status code: {response.status_code}")
        print(response.text)
    
    print()


def test_custom_weights():
    """Test: Search with custom weights"""
    print("=" * 60)
    print("Test 3: Custom Weights")
    print("=" * 60)
    
    payload = {
        "query": "PyTorch Adam optimizer",
        "top_k": 3,
        "search_mode": "hybrid",
        "knn_weight": 0.3,
        "bm25_weight": 0.7,
        "auto_adjust": False
    }
    
    response = requests.post(f"{BASE_URL}/search/", json=payload)
    
    if response.status_code == 200:
        data = response.json()
        weights = data["weights_used"]
        print(f"✅ Custom weights applied")
        print(f"   KNN weight: {weights['knn_weight']}")
        print(f"   BM25 weight: {weights['bm25_weight']}")
        print(f"   RRF k: {weights['rrf_k']}")
        print(f"   Results: {data['total_results']}")
    else:
        print(f"❌ Failed with status code: {response.status_code}")
    
    print()


def test_auto_adjust():
    """Test: Auto weight adjustment"""
    print("=" * 60)
    print("Test 4: Auto Weight Adjustment")
    print("=" * 60)
    
    # Test with technical terms
    payload1 = {
        "query": "PyTorch GPU CUDA",
        "top_k": 3,
        "search_mode": "hybrid",
        "auto_adjust": True
    }
    
    response1 = requests.post(f"{BASE_URL}/search/", json=payload1)
    
    if response1.status_code == 200:
        data1 = response1.json()
        print(f"✅ Technical query auto-adjustment:")
        print(f"   Query: {data1['query']}")
        print(f"   Weights: {data1['weights_used']}")
    
    # Test with question
    payload2 = {
        "query": "How to improve deep learning model performance?",
        "top_k": 3,
        "search_mode": "hybrid",
        "auto_adjust": True
    }
    
    response2 = requests.post(f"{BASE_URL}/search/", json=payload2)
    
    if response2.status_code == 200:
        data2 = response2.json()
        print(f"\n✅ Question query auto-adjustment:")
        print(f"   Query: {data2['query']}")
        print(f"   Weights: {data2['weights_used']}")
    
    print()


def test_compare_modes():
    """Test: Compare search modes"""
    print("=" * 60)
    print("Test 5: Compare Search Modes")
    print("=" * 60)
    
    query = "deep learning optimization"
    
    response = requests.get(
        f"{BASE_URL}/search/compare",
        params={"query": query, "top_k": 3}
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Comparison completed")
        print(f"   Query: {data['query']}")
        print(f"   Hybrid results: {len(data['hybrid']['results'])} documents")
        print(f"   KNN results: {len(data['knn_only'])} documents")
        print(f"   BM25 results: {len(data['bm25_only'])} documents")
        print(f"   Hybrid weights: {data['hybrid']['weights']}")
    else:
        print(f"❌ Failed with status code: {response.status_code}")
    
    print()


def test_runtime_weight_update():
    """Test: Runtime weight update"""
    print("=" * 60)
    print("Test 6: Runtime Weight Update")
    print("=" * 60)
    
    # Update weights
    response = requests.post(
        f"{BASE_URL}/search/config/weights",
        params={
            "knn_weight": 0.7,
            "bm25_weight": 0.3
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Weights updated at runtime")
        print(f"   New weights: {data['data']}")
        
        # Verify by checking config
        config_response = requests.get(f"{BASE_URL}/search/config")
        if config_response.status_code == 200:
            config = config_response.json()
            print(f"   Verified: {config['weights']}")
    else:
        print(f"❌ Failed with status code: {response.status_code}")
    
    print()


if __name__ == "__main__":
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "HYBRID SEARCH FUNCTIONALITY TEST" + " " * 15 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    try:
        test_search_config()
        test_hybrid_search()
        test_custom_weights()
        test_auto_adjust()
        test_compare_modes()
        test_runtime_weight_update()
        
        print("=" * 60)
        print("✅ ALL TESTS COMPLETED")
        print("=" * 60)
        
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to server")
        print("   Please make sure the server is running:")
        print("   cd backend && ./start_server.sh")
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")

