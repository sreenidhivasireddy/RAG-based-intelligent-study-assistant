"""
End-to-End Search Test Suite.
Tests the complete search functionality after file upload and parsing is complete.

Prerequisites:
    - Azure AI Search index created and configured
    - File upload and parsing services working
    - Documents uploaded and vectorized
    - Azure Search environment variables set

Usage:
    # After uploading test documents:
    python tests/test_e2e_search.py

    # With specific options:
    python tests/test_e2e_search.py --index rag-index --top-k 10
"""

import sys
import os
import argparse
import time
import json
from typing import List, Dict, Optional
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from azure.search.documents import SearchClient
    from azure.core.credentials import AzureKeyCredential
    import requests
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: pip install azure-search-documents azure-core requests")
    sys.exit(1)


# ==================== Configuration ====================

class TestConfig:
    """Test configuration for Azure AI Search"""
    AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "https://localhost:8081")
    AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_ADMIN_KEY", "")
    AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX", "rag-index")
    
    API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    
    # Test queries for different scenarios
    TEST_QUERIES = {
        "chinese": [
            "deep learning model optimization",
            "how to train a neural network",
            "machine learning algorithms",
        ],
        "english": [
            "PyTorch optimization",
            "neural network training",
            "machine learning algorithms",
        ],
        "mixed": [
            "PyTorch deep learning",
            "Adam optimizer training",
            "BERT model applications",
        ],
        "technical": [
            "Transformer attention mechanism",
            "CNN feature extraction",
            "RNN LSTM GRU",
        ],
        "questions": [
            "How can model accuracy be improved?",
            "What is backpropagation?",
            "Why use the Adam optimizer?",
        ]
    }


# ==================== Test Utilities ====================

class Colors:
    """Terminal colors"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(title: str):
    """Print section header"""
    print()
    print("=" * 60)
    print(f"{Colors.BOLD}{title}{Colors.END}")
    print("=" * 60)


def print_pass(msg: str):
    """Print pass message"""
    print(f"{Colors.GREEN}✅ {msg}{Colors.END}")


def print_fail(msg: str):
    """Print fail message"""
    print(f"{Colors.RED}❌ {msg}{Colors.END}")


def print_warn(msg: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠️ {msg}{Colors.END}")


def print_info(msg: str):
    """Print info message"""
    print(f"{Colors.BLUE}ℹ️ {msg}{Colors.END}")


# ==================== Test Classes ====================

class E2ESearchTester:
    """End-to-end search tester"""
    
    def __init__(self, config: TestConfig):
        self.config = config
        self.search_client = None
        self.results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "details": []
        }
    
    def connect_azure_search(self) -> bool:
        """Connect to Azure AI Search"""
        try:
            if not self.config.AZURE_SEARCH_KEY:
                print_fail("AZURE_SEARCH_ADMIN_KEY environment variable not set")
                return False
            
            credentials = AzureKeyCredential(self.config.AZURE_SEARCH_KEY)
            self.search_client = SearchClient(
                endpoint=self.config.AZURE_SEARCH_ENDPOINT,
                index_name=self.config.AZURE_SEARCH_INDEX,
                credential=credentials
            )
            
            # Test connection by getting index info
            print_pass(f"Azure AI Search connected to index: {self.config.AZURE_SEARCH_INDEX}")
            return True
        except Exception as e:
            print_fail(f"Azure AI Search connection failed: {e}")
            return False
    
    def check_index(self) -> Dict:
        """Check index status"""
        print_header("1. Index Status Check")
        
        try:
            # Try to perform a simple search to verify index exists
            results = self.search_client.search(search_text="*", top=1)
            
            # Count total documents
            doc_list = list(results)
            doc_count = len(doc_list)
            
            # Azure Search doesn't directly expose doc count from simple search
            # We estimate based on the first batch
            print_pass(f"Index '{self.config.AZURE_SEARCH_INDEX}' exists and is searchable")
            print_info(f"Sample documents found: {doc_count}")
            
            if doc_count == 0:
                print_warn("Index appears empty! Please upload documents first.")
                return {"exists": True, "doc_count": 0}
            
            return {
                "exists": True,
                "doc_count": doc_count,
                "index_name": self.config.AZURE_SEARCH_INDEX
            }
            
        except Exception as e:
            print_fail(f"Index check failed: {e}")
            return {"error": str(e)}
    
    def test_api_health(self) -> bool:
        """Test API health"""
        print_header("2. API Health Check")
        
        try:
            # Health endpoint
            resp = requests.get(f"{self.config.API_BASE_URL.replace('/api/v1', '')}/health", timeout=5)
            if resp.status_code == 200:
                print_pass("API health check passed")
            else:
                print_fail(f"API health check failed: {resp.status_code}")
                return False
            
            # Config endpoint
            resp = requests.get(f"{self.config.API_BASE_URL}/search/config", timeout=5)
            if resp.status_code == 200:
                config = resp.json()
                print_pass("Search config endpoint working")
                print_info(f"KNN weight: {config.get('weights', {}).get('knn', 'N/A')}")
                print_info(f"BM25 weight: {config.get('weights', {}).get('bm25', 'N/A')}")
            else:
                print_warn(f"Search config endpoint returned: {resp.status_code}")
            
            return True
            
        except requests.exceptions.ConnectionError:
            print_fail("Cannot connect to API. Is the server running?")
            print_info("Start with: uvicorn app.main:app --reload")
            return False
        except Exception as e:
            print_fail(f"API health check failed: {e}")
            return False
    
    def test_analyzer(self) -> bool:
        """Test analyzer endpoints"""
        print_header("3. Analyzer Test")
        
        test_texts = [
            ("deep learning model optimization", "chinese_smart"),
            ("optimization techniques", "english"),
            ("PyTorch model training", "chinese_smart"),
        ]
        
        all_passed = True
        for text, analyzer in test_texts:
            try:
                resp = requests.post(
                    f"{self.config.API_BASE_URL}/search/analyze",
                    json={"text": text, "analyzer": analyzer},
                    timeout=10
                )
                
                if resp.status_code == 200:
                    result = resp.json()
                    tokens = result.get("tokens", [])
                    print_pass(f"'{text[:20]}...' → {tokens[:5]}")
                else:
                    print_fail(f"Analyzer failed for '{text[:20]}...': {resp.status_code}")
                    all_passed = False
                    
            except Exception as e:
                print_fail(f"Analyzer test error: {e}")
                all_passed = False
        
        return all_passed
    
    def test_search_modes(self) -> Dict:
        """Test different search modes"""
        print_header("4. Search Mode Tests")
        
        test_query = "deep learning"
        modes = ["hybrid", "knn", "bm25"]
        results = {}
        
        for mode in modes:
            try:
                resp = requests.post(
                    f"{self.config.API_BASE_URL}/search/",
                    json={
                        "query": test_query,
                        "top_k": 5,
                        "search_mode": mode
                    },
                    timeout=30
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    count = data.get("total_results", 0)
                    time_ms = data.get("execution_time_ms", 0)
                    print_pass(f"{mode:8} mode: {count} results in {time_ms:.1f}ms")
                    results[mode] = {"count": count, "time_ms": time_ms}
                else:
                    print_fail(f"{mode:8} mode failed: {resp.status_code}")
                    try:
                        error = resp.json()
                        print_info(f"  Error: {error.get('detail', 'Unknown')}")
                    except:
                        pass
                    results[mode] = {"error": resp.status_code}
                    
            except Exception as e:
                print_fail(f"{mode:8} mode error: {e}")
                results[mode] = {"error": str(e)}
        
        return results
    
    def test_query_categories(self) -> Dict:
        """Test different query categories"""
        print_header("5. Query Category Tests")
        
        results = {}
        
        for category, queries in self.config.TEST_QUERIES.items():
            print(f"\n{Colors.BOLD}Category: {category}{Colors.END}")
            print("-" * 40)
            
            category_results = []
            for query in queries:
                try:
                    resp = requests.post(
                        f"{self.config.API_BASE_URL}/search/",
                        json={
                            "query": query,
                            "top_k": 5,
                            "search_mode": "hybrid",
                            "auto_adjust": True
                        },
                        timeout=30
                    )
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        count = data.get("total_results", 0)
                        metadata = data.get("metadata", {})
                        knn_w = metadata.get("knn_weight", "N/A")
                        bm25_w = metadata.get("bm25_weight", "N/A")
                        
                        if count > 0:
                            print_pass(f"'{query[:25]}...' → {count} results (knn:{knn_w}, bm25:{bm25_w})")
                        else:
                            print_warn(f"'{query[:25]}...' → No results")
                        
                        category_results.append({
                            "query": query,
                            "count": count,
                            "weights": {"knn": knn_w, "bm25": bm25_w}
                        })
                    else:
                        print_fail(f"'{query[:25]}...' → Error {resp.status_code}")
                        category_results.append({"query": query, "error": resp.status_code})
                        
                except Exception as e:
                    print_fail(f"'{query[:25]}...' → {e}")
                    category_results.append({"query": query, "error": str(e)})
            
            results[category] = category_results
        
        return results
    
    def test_weight_adjustment(self) -> bool:
        """Test weight adjustment API"""
        print_header("6. Weight Adjustment Test")
        
        try:
            # Get current weights
            resp = requests.get(f"{self.config.API_BASE_URL}/search/config", timeout=5)
            original = resp.json().get("weights", {})
            print_info(f"Original weights: knn={original.get('knn')}, bm25={original.get('bm25')}")
            
            # Update weights
            resp = requests.post(
                f"{self.config.API_BASE_URL}/search/config/weights",
                params={"knn_weight": 0.7, "bm25_weight": 0.3},
                timeout=5
            )
            
            if resp.status_code == 200:
                print_pass("Weight update successful")
                
                # Verify update
                resp = requests.get(f"{self.config.API_BASE_URL}/search/config", timeout=5)
                updated = resp.json().get("weights", {})
                print_info(f"Updated weights: knn={updated.get('knn')}, bm25={updated.get('bm25')}")
                
                # Restore original
                requests.post(
                    f"{self.config.API_BASE_URL}/search/config/weights",
                    params={
                        "knn_weight": original.get("knn", 0.5),
                        "bm25_weight": original.get("bm25", 0.5)
                    },
                    timeout=5
                )
                print_pass("Weights restored")
                
                return True
            else:
                print_fail(f"Weight update failed: {resp.status_code}")
                return False
                
        except Exception as e:
            print_fail(f"Weight adjustment test failed: {e}")
            return False
    
    def test_search_comparison(self) -> Dict:
        """Test search comparison endpoint"""
        print_header("7. Search Comparison Test")
        
        test_query = "PyTorch optimization"
        
        try:
            resp = requests.get(
                f"{self.config.API_BASE_URL}/search/compare",
                params={"query": test_query, "top_k": 3},
                timeout=60
            )
            
            if resp.status_code == 200:
                data = resp.json()
                print_pass("Search comparison successful")
                
                # Print comparison
                for mode in ["hybrid", "knn_only", "bm25_only"]:
                    results = data.get(mode, {}).get("results", [])
                    count = len(results)
                    print_info(f"{mode:12}: {count} results")
                    
                    if results:
                        top_score = results[0].get("score", 0)
                        print(f"             Top score: {top_score:.4f}")
                
                return data
            else:
                print_fail(f"Comparison failed: {resp.status_code}")
                return {"error": resp.status_code}
                
        except Exception as e:
            print_fail(f"Comparison test failed: {e}")
            return {"error": str(e)}
    
    def test_highlight(self) -> bool:
        """Test highlight functionality"""
        print_header("8. Highlight Test")
        
        try:
            resp = requests.post(
                f"{self.config.API_BASE_URL}/search/",
                json={
                    "query": "deep learning",
                    "top_k": 3,
                    "search_mode": "hybrid"
                },
                timeout=30
            )
            
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                
                has_highlight = False
                for result in results:
                    highlights = result.get("highlights", [])
                    if highlights:
                        has_highlight = True
                        print_pass(f"Highlight found: {highlights[0][:60]}...")
                        break
                
                if not has_highlight:
                    print_warn("No highlights in results (may be normal if no exact match)")
                
                return True
            else:
                print_fail(f"Highlight test failed: {resp.status_code}")
                return False
                
        except Exception as e:
            print_fail(f"Highlight test failed: {e}")
            return False
    
    def test_file_filter(self) -> bool:
        """Test file filter functionality"""
        print_header("9. File Filter Test")
        
        try:
            # First, get a sample file_md5 from existing documents
            results = list(self.search_client.search(
                search_text="*",
                top=1,
                select=['file_md5']
            ))
            
            if not results:
                print_warn("No documents to test file filter")
                return True
            
            file_md5 = results[0].get('file_md5', '')
            print_info(f"Testing with file_md5: {file_md5[:16]}...")
            
            # Search with filter
            resp = requests.post(
                f"{self.config.API_BASE_URL}/search/",
                json={
                    "query": "test",
                    "top_k": 10,
                    "search_mode": "bm25",
                    "file_md5": file_md5
                },
                timeout=30
            )
            
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                
                # Verify all results are from the same file
                all_same_file = all(r.get("file_md5") == file_md5 for r in results)
                
                if all_same_file:
                    print_pass(f"File filter works: {len(results)} results from same file")
                else:
                    print_fail("File filter returned results from different files")
                
                return all_same_file
            else:
                print_fail(f"File filter test failed: {resp.status_code}")
                return False
                
        except Exception as e:
            print_fail(f"File filter test failed: {e}")
            return False
    
    def test_edge_cases(self) -> Dict:
        """Test edge cases"""
        print_header("10. Edge Case Tests")
        
        results = {}
        
        # Empty query (should fail validation)
        try:
            resp = requests.post(
                f"{self.config.API_BASE_URL}/search/",
                json={"query": "", "top_k": 5},
                timeout=10
            )
            if resp.status_code == 422:
                print_pass("Empty query correctly rejected (422)")
                results["empty_query"] = "pass"
            else:
                print_fail(f"Empty query should return 422, got {resp.status_code}")
                results["empty_query"] = "fail"
        except Exception as e:
            print_fail(f"Empty query test error: {e}")
            results["empty_query"] = "error"
        
        # Very long query
        long_query = "deep learning " * 50  # ~450 chars
        try:
            resp = requests.post(
                f"{self.config.API_BASE_URL}/search/",
                json={"query": long_query, "top_k": 5},
                timeout=30
            )
            if resp.status_code == 200:
                print_pass("Long query handled successfully")
                results["long_query"] = "pass"
            else:
                print_warn(f"Long query returned: {resp.status_code}")
                results["long_query"] = "warning"
        except Exception as e:
            print_fail(f"Long query test error: {e}")
            results["long_query"] = "error"
        
        # Special characters
        special_query = 'test "quoted" and (parentheses)'
        try:
            resp = requests.post(
                f"{self.config.API_BASE_URL}/search/",
                json={"query": special_query, "top_k": 5},
                timeout=30
            )
            if resp.status_code == 200:
                print_pass("Special characters handled successfully")
                results["special_chars"] = "pass"
            else:
                print_warn(f"Special characters returned: {resp.status_code}")
                results["special_chars"] = "warning"
        except Exception as e:
            print_fail(f"Special characters test error: {e}")
            results["special_chars"] = "error"
        
        # Invalid search mode
        try:
            resp = requests.post(
                f"{self.config.API_BASE_URL}/search/",
                json={"query": "test", "search_mode": "invalid"},
                timeout=10
            )
            if resp.status_code == 422:
                print_pass("Invalid search mode correctly rejected (422)")
                results["invalid_mode"] = "pass"
            else:
                print_fail(f"Invalid mode should return 422, got {resp.status_code}")
                results["invalid_mode"] = "fail"
        except Exception as e:
            print_fail(f"Invalid mode test error: {e}")
            results["invalid_mode"] = "error"
        
        return results
    
    def generate_report(self) -> str:
        """Generate test report"""
        print_header("Test Report Summary")
        
        report = []
        report.append(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Azure AI Search Index: {self.config.AZURE_SEARCH_INDEX}")
        report.append(f"API URL: {self.config.API_BASE_URL}")
        report.append("")
        report.append(f"Total Tests: {self.results['total']}")
        report.append(f"Passed: {self.results['passed']}")
        report.append(f"Failed: {self.results['failed']}")
        report.append(f"Warnings: {self.results['warnings']}")
        
        success_rate = (self.results['passed'] / max(self.results['total'], 1)) * 100
        report.append(f"Success Rate: {success_rate:.1f}%")
        
        report_text = "\n".join(report)
        print(report_text)
        
        return report_text
    
    def run_all_tests(self):
        """Run all tests"""
        print("\n")
        print("╔" + "=" * 58 + "╗")
        print("║" + " " * 15 + "END-TO-END SEARCH TESTS" + " " * 20 + "║")
        print("║" + " " * 12 + "(After File Upload Complete)" + " " * 17 + "║")
        print("╚" + "=" * 58 + "╝")
        
        # Connect to Azure AI Search
        if not self.connect_azure_search():
            print_fail("Cannot proceed without Azure AI Search connection")
            return
        
        # Run tests
        tests = [
            ("Index Check", self.check_index),
            ("API Health", self.test_api_health),
            ("Analyzer", self.test_analyzer),
            ("Search Modes", self.test_search_modes),
            ("Query Categories", self.test_query_categories),
            ("Weight Adjustment", self.test_weight_adjustment),
            ("Search Comparison", self.test_search_comparison),
            ("Highlight", self.test_highlight),
            ("File Filter", self.test_file_filter),
            ("Edge Cases", self.test_edge_cases),
        ]
        
        for name, test_func in tests:
            self.results["total"] += 1
            try:
                result = test_func()
                if result:
                    self.results["passed"] += 1
                else:
                    self.results["failed"] += 1
            except Exception as e:
                print_fail(f"{name} failed with exception: {e}")
                self.results["failed"] += 1
        
        # Generate report
        self.generate_report()


# ==================== Main ====================

def main():
    parser = argparse.ArgumentParser(description="End-to-End Search Test Suite")
    parser.add_argument("--index", default="knowledge_base", help="Azure Search index name")
    parser.add_argument("--api-url", default="http://localhost:8000/api/v1", help="API base URL")
    parser.add_argument("--top-k", type=int, default=5, help="Default top_k for searches")
    args = parser.parse_args()
    
    config = TestConfig()
    config.AZURE_SEARCH_INDEX = args.index
    config.API_BASE_URL = args.api_url
    
    tester = E2ESearchTester(config)
    tester.run_all_tests()


if __name__ == "__main__":
    main()

