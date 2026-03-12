"""
Search Quality Evaluation Test.
Evaluates search relevance, recall, and precision.

This test is designed to run after:
1. Documents are uploaded and parsed
2. Vectors are generated
3. Index is populated

Usage:
    python tests/test_search_quality.py
"""

import sys
import os
import json
from typing import List, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import requests
except ImportError:
    print("Missing: pip install requests")
    sys.exit(1)


# ==================== Configuration ====================

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")


@dataclass
class QueryTestCase:
    """A test case with query and expected relevant documents"""
    query: str
    expected_keywords: List[str]  # Keywords that should appear in results
    category: str  # Query category
    min_results: int = 1  # Minimum expected results


# ==================== Test Cases ====================

TEST_CASES = [
    # Chinese queries
    QueryTestCase(
        query="deep learning model optimization",
        expected_keywords=["deep", "learning", "optimization", "model"],
        category="chinese"
    ),
    QueryTestCase(
        query="neural network training methods",
        expected_keywords=["neural", "training"],
        category="chinese"
    ),
    
    # English queries
    QueryTestCase(
        query="PyTorch model training",
        expected_keywords=["pytorch", "train", "model"],
        category="english"
    ),
    QueryTestCase(
        query="optimization algorithm",
        expected_keywords=["optim", "algorithm"],
        category="english"
    ),
    
    # Mixed queries
    QueryTestCase(
        query="PyTorch deep learning",
        expected_keywords=["pytorch", "deep", "learning"],
        category="mixed"
    ),
    QueryTestCase(
        query="Adam optimizer training",
        expected_keywords=["adam", "optim", "training"],
        category="mixed"
    ),
    
    # Questions
    QueryTestCase(
        query="How can model accuracy be improved?",
        expected_keywords=["model", "accuracy"],
        category="question"
    ),
    QueryTestCase(
        query="What is gradient descent?",
        expected_keywords=["gradient", "descent"],
        category="question"
    ),
]


# ==================== Evaluation Functions ====================

def evaluate_keyword_presence(result_text: str, keywords: List[str]) -> float:
    """
    Evaluate how many expected keywords appear in the result.
    
    Returns:
        Score between 0 and 1
    """
    text_lower = result_text.lower()
    found = sum(1 for kw in keywords if kw.lower() in text_lower)
    return found / len(keywords) if keywords else 0


def evaluate_position_bias(results: List[Dict], keywords: List[str]) -> float:
    """
    Evaluate if relevant results appear near the top.
    Higher positions get higher scores.
    
    Returns:
        Score between 0 and 1
    """
    if not results:
        return 0
    
    position_scores = []
    for i, result in enumerate(results):
        text = result.get("text_content", "").lower()
        keyword_score = evaluate_keyword_presence(text, keywords)
        
        # Position weight: first result = 1.0, decreases linearly
        position_weight = 1 - (i / len(results))
        position_scores.append(keyword_score * position_weight)
    
    return sum(position_scores) / len(results) if position_scores else 0


def evaluate_diversity(results: List[Dict]) -> float:
    """
    Evaluate result diversity (different files).
    
    Returns:
        Score between 0 and 1
    """
    if not results:
        return 0
    
    unique_files = set(r.get("file_md5", "") for r in results)
    return len(unique_files) / len(results)


def run_quality_test(test_case: QueryTestCase, top_k: int = 10) -> Dict:
    """
    Run quality test for a single query.
    
    Returns:
        Dictionary with evaluation metrics
    """
    try:
        # Execute search
        resp = requests.post(
            f"{API_BASE_URL}/search/",
            json={
                "query": test_case.query,
                "top_k": top_k,
                "search_mode": "hybrid",
                "auto_adjust": True
            },
            timeout=30
        )
        
        if resp.status_code != 200:
            return {
                "query": test_case.query,
                "category": test_case.category,
                "error": f"HTTP {resp.status_code}",
                "metrics": {}
            }
        
        data = resp.json()
        results = data.get("results", [])
        
        # Calculate metrics
        metrics = {
            "result_count": len(results),
            "has_min_results": len(results) >= test_case.min_results,
            "keyword_presence": 0,
            "position_bias": 0,
            "diversity": 0,
            "avg_score": 0
        }
        
        if results:
            # Keyword presence in top result
            top_text = results[0].get("text_content", "")
            metrics["keyword_presence"] = evaluate_keyword_presence(
                top_text, test_case.expected_keywords
            )
            
            # Position bias
            metrics["position_bias"] = evaluate_position_bias(
                results, test_case.expected_keywords
            )
            
            # Diversity
            metrics["diversity"] = evaluate_diversity(results)
            
            # Average score
            scores = [r.get("score", 0) for r in results]
            metrics["avg_score"] = sum(scores) / len(scores)
        
        # Weights info
        metadata = data.get("metadata", {})
        
        return {
            "query": test_case.query,
            "category": test_case.category,
            "metrics": metrics,
            "weights_used": {
                "knn": metadata.get("knn_weight"),
                "bm25": metadata.get("bm25_weight"),
                "auto_adjusted": metadata.get("auto_adjusted")
            }
        }
        
    except Exception as e:
        return {
            "query": test_case.query,
            "category": test_case.category,
            "error": str(e),
            "metrics": {}
        }


def compare_search_modes(query: str, top_k: int = 5) -> Dict:
    """
    Compare results across different search modes.
    
    Returns:
        Dictionary with comparison results
    """
    modes = ["hybrid", "knn", "bm25"]
    comparison = {"query": query, "modes": {}}
    
    for mode in modes:
        try:
            resp = requests.post(
                f"{API_BASE_URL}/search/",
                json={
                    "query": query,
                    "top_k": top_k,
                    "search_mode": mode
                },
                timeout=30
            )
            
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                
                comparison["modes"][mode] = {
                    "count": len(results),
                    "top_scores": [r.get("score", 0) for r in results[:3]],
                    "execution_time_ms": data.get("execution_time_ms", 0)
                }
            else:
                comparison["modes"][mode] = {"error": resp.status_code}
                
        except Exception as e:
            comparison["modes"][mode] = {"error": str(e)}
    
    return comparison


def generate_quality_report(results: List[Dict]) -> str:
    """
    Generate quality evaluation report.
    
    Returns:
        Formatted report string
    """
    report = []
    report.append("\n" + "=" * 60)
    report.append("SEARCH QUALITY EVALUATION REPORT")
    report.append("=" * 60)
    report.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Total test cases: {len(results)}")
    report.append("")
    
    # Group by category
    categories = {}
    for r in results:
        cat = r.get("category", "unknown")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r)
    
    # Summary by category
    report.append("SUMMARY BY CATEGORY")
    report.append("-" * 40)
    
    for cat, cat_results in categories.items():
        successful = [r for r in cat_results if "error" not in r]
        
        if successful:
            avg_keyword = sum(r["metrics"]["keyword_presence"] for r in successful) / len(successful)
            avg_position = sum(r["metrics"]["position_bias"] for r in successful) / len(successful)
            avg_diversity = sum(r["metrics"]["diversity"] for r in successful) / len(successful)
            
            report.append(f"\n{cat.upper()}:")
            report.append(f"  Tests: {len(cat_results)}, Successful: {len(successful)}")
            report.append(f"  Avg Keyword Presence: {avg_keyword:.2%}")
            report.append(f"  Avg Position Bias: {avg_position:.2%}")
            report.append(f"  Avg Diversity: {avg_diversity:.2%}")
    
    # Overall metrics
    all_successful = [r for r in results if "error" not in r]
    if all_successful:
        report.append("\n" + "-" * 40)
        report.append("OVERALL METRICS")
        
        overall_keyword = sum(r["metrics"]["keyword_presence"] for r in all_successful) / len(all_successful)
        overall_position = sum(r["metrics"]["position_bias"] for r in all_successful) / len(all_successful)
        overall_diversity = sum(r["metrics"]["diversity"] for r in all_successful) / len(all_successful)
        
        report.append(f"  Overall Keyword Presence: {overall_keyword:.2%}")
        report.append(f"  Overall Position Bias: {overall_position:.2%}")
        report.append(f"  Overall Diversity: {overall_diversity:.2%}")
        
        # Quality score (weighted average)
        quality_score = (overall_keyword * 0.4 + overall_position * 0.4 + overall_diversity * 0.2)
        report.append(f"\n  QUALITY SCORE: {quality_score:.2%}")
        
        if quality_score >= 0.8:
            report.append("  Rating: EXCELLENT ⭐⭐⭐⭐⭐")
        elif quality_score >= 0.6:
            report.append("  Rating: GOOD ⭐⭐⭐⭐")
        elif quality_score >= 0.4:
            report.append("  Rating: FAIR ⭐⭐⭐")
        elif quality_score >= 0.2:
            report.append("  Rating: NEEDS IMPROVEMENT ⭐⭐")
        else:
            report.append("  Rating: POOR ⭐")
    
    # Detailed results
    report.append("\n" + "-" * 40)
    report.append("DETAILED RESULTS")
    
    for r in results:
        report.append(f"\nQuery: '{r['query']}'")
        report.append(f"  Category: {r['category']}")
        
        if "error" in r:
            report.append(f"  ERROR: {r['error']}")
        else:
            m = r["metrics"]
            report.append(f"  Results: {m['result_count']}")
            report.append(f"  Keyword Presence: {m['keyword_presence']:.2%}")
            report.append(f"  Position Bias: {m['position_bias']:.2%}")
            report.append(f"  Diversity: {m['diversity']:.2%}")
            
            w = r.get("weights_used", {})
            if w.get("auto_adjusted"):
                report.append(f"  Auto-adjusted: knn={w.get('knn')}, bm25={w.get('bm25')}")
    
    report.append("\n" + "=" * 60)
    
    return "\n".join(report)


def main():
    """Run quality evaluation"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 12 + "SEARCH QUALITY EVALUATION" + " " * 21 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    # Check API availability
    try:
        resp = requests.get(f"{API_BASE_URL}/search/config", timeout=5)
        if resp.status_code != 200:
            print(f"❌ API not available: {resp.status_code}")
            return
        print("✅ API connected")
    except Exception as e:
        print(f"❌ Cannot connect to API: {e}")
        print("   Start with: uvicorn app.main:app --reload")
        return
    
    # Run tests
    print("\nRunning quality tests...")
    results = []
    
    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"  [{i}/{len(TEST_CASES)}] Testing: '{test_case.query[:30]}...'")
        result = run_quality_test(test_case)
        results.append(result)
    
    # Run mode comparison
    print("\nRunning search mode comparison...")
    comparison = compare_search_modes("deep learning optimization")
    
    # Generate report
    report = generate_quality_report(results)
    print(report)
    
    # Mode comparison summary
    print("\nSEARCH MODE COMPARISON")
    print("-" * 40)
    print(f"Query: '{comparison['query']}'")
    for mode, data in comparison["modes"].items():
        if "error" not in data:
            print(f"  {mode:8}: {data['count']} results, top scores: {data['top_scores']}")
        else:
            print(f"  {mode:8}: Error - {data['error']}")
    
    # Save report
    report_file = f"search_quality_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, "w") as f:
        f.write(report)
    print(f"\n📄 Report saved to: {report_file}")


if __name__ == "__main__":
    main()

