"""
Search Performance Test.
Tests search latency, throughput, and scalability.

Usage:
    python tests/test_search_performance.py
    python tests/test_search_performance.py --concurrent 10 --iterations 100
"""

import sys
import os
import time
import argparse
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict
from datetime import datetime
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import requests
except ImportError:
    print("Missing: pip install requests")
    sys.exit(1)


# ==================== Configuration ====================

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

TEST_QUERIES = [
    "深度学习模型优化",
    "PyTorch training",
    "神经网络",
    "machine learning algorithm",
    "Adam optimizer 训练模型",
    "如何提高准确率",
    "Transformer attention",
    "卷积神经网络",
]


# ==================== Test Functions ====================

def single_search(query: str, search_mode: str = "hybrid", top_k: int = 10) -> Dict:
    """
    Execute a single search and measure time.
    
    Returns:
        Dictionary with timing and result info
    """
    start_time = time.perf_counter()
    
    try:
        resp = requests.post(
            f"{API_BASE_URL}/search/",
            json={
                "query": query,
                "top_k": top_k,
                "search_mode": search_mode
            },
            timeout=60
        )
        
        end_time = time.perf_counter()
        latency_ms = (end_time - start_time) * 1000
        
        if resp.status_code == 200:
            data = resp.json()
            return {
                "success": True,
                "latency_ms": latency_ms,
                "result_count": data.get("total_results", 0),
                "server_time_ms": data.get("execution_time_ms", 0)
            }
        else:
            return {
                "success": False,
                "latency_ms": latency_ms,
                "error": f"HTTP {resp.status_code}"
            }
            
    except Exception as e:
        end_time = time.perf_counter()
        return {
            "success": False,
            "latency_ms": (end_time - start_time) * 1000,
            "error": str(e)
        }


def run_latency_test(iterations: int = 50) -> Dict:
    """
    Run latency test with multiple iterations.
    
    Returns:
        Dictionary with latency statistics
    """
    print("\n" + "=" * 50)
    print("LATENCY TEST")
    print("=" * 50)
    print(f"Iterations: {iterations}")
    print(f"Search mode: hybrid")
    print()
    
    latencies = {
        "hybrid": [],
        "knn": [],
        "bm25": []
    }
    
    for mode in latencies.keys():
        print(f"Testing {mode} mode...")
        
        for i in range(iterations):
            query = TEST_QUERIES[i % len(TEST_QUERIES)]
            result = single_search(query, search_mode=mode)
            
            if result["success"]:
                latencies[mode].append(result["latency_ms"])
            
            # Progress indicator
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{iterations} completed")
    
    # Calculate statistics
    stats = {}
    for mode, times in latencies.items():
        if times:
            stats[mode] = {
                "count": len(times),
                "min_ms": min(times),
                "max_ms": max(times),
                "avg_ms": statistics.mean(times),
                "median_ms": statistics.median(times),
                "p95_ms": sorted(times)[int(len(times) * 0.95)] if len(times) >= 20 else max(times),
                "p99_ms": sorted(times)[int(len(times) * 0.99)] if len(times) >= 100 else max(times),
            }
        else:
            stats[mode] = {"error": "No successful requests"}
    
    # Print results
    print("\nLatency Results:")
    print("-" * 50)
    for mode, s in stats.items():
        if "error" not in s:
            print(f"\n{mode.upper()}:")
            print(f"  Min:    {s['min_ms']:.1f} ms")
            print(f"  Max:    {s['max_ms']:.1f} ms")
            print(f"  Avg:    {s['avg_ms']:.1f} ms")
            print(f"  Median: {s['median_ms']:.1f} ms")
            print(f"  P95:    {s['p95_ms']:.1f} ms")
    
    return stats


def run_throughput_test(concurrent: int = 5, duration_sec: int = 30) -> Dict:
    """
    Run throughput test with concurrent requests.
    
    Returns:
        Dictionary with throughput statistics
    """
    print("\n" + "=" * 50)
    print("THROUGHPUT TEST")
    print("=" * 50)
    print(f"Concurrent users: {concurrent}")
    print(f"Duration: {duration_sec} seconds")
    print()
    
    results = []
    start_time = time.time()
    end_time = start_time + duration_sec
    request_count = 0
    
    def worker():
        nonlocal request_count
        local_results = []
        
        while time.time() < end_time:
            query = TEST_QUERIES[request_count % len(TEST_QUERIES)]
            result = single_search(query)
            local_results.append(result)
            request_count += 1
        
        return local_results
    
    # Run concurrent workers
    print("Running concurrent requests...")
    with ThreadPoolExecutor(max_workers=concurrent) as executor:
        futures = [executor.submit(worker) for _ in range(concurrent)]
        
        for future in as_completed(futures):
            results.extend(future.result())
    
    actual_duration = time.time() - start_time
    
    # Calculate statistics
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    stats = {
        "total_requests": len(results),
        "successful_requests": len(successful),
        "failed_requests": len(failed),
        "duration_sec": actual_duration,
        "requests_per_second": len(results) / actual_duration,
        "success_rate": len(successful) / len(results) * 100 if results else 0
    }
    
    if successful:
        latencies = [r["latency_ms"] for r in successful]
        stats["avg_latency_ms"] = statistics.mean(latencies)
        stats["p95_latency_ms"] = sorted(latencies)[int(len(latencies) * 0.95)]
    
    # Print results
    print(f"\nThroughput Results:")
    print("-" * 50)
    print(f"Total Requests:     {stats['total_requests']}")
    print(f"Successful:         {stats['successful_requests']}")
    print(f"Failed:             {stats['failed_requests']}")
    print(f"Duration:           {stats['duration_sec']:.1f} sec")
    print(f"Requests/Second:    {stats['requests_per_second']:.1f}")
    print(f"Success Rate:       {stats['success_rate']:.1f}%")
    
    if "avg_latency_ms" in stats:
        print(f"Avg Latency:        {stats['avg_latency_ms']:.1f} ms")
        print(f"P95 Latency:        {stats['p95_latency_ms']:.1f} ms")
    
    return stats


def run_scalability_test(max_concurrent: int = 20) -> Dict:
    """
    Test scalability by increasing concurrent users.
    
    Returns:
        Dictionary with scalability data
    """
    print("\n" + "=" * 50)
    print("SCALABILITY TEST")
    print("=" * 50)
    print(f"Testing concurrency from 1 to {max_concurrent}")
    print()
    
    results = {}
    concurrency_levels = [1, 2, 5, 10, 15, 20][:max_concurrent]
    
    for concurrent in concurrency_levels:
        if concurrent > max_concurrent:
            break
            
        print(f"\nTesting with {concurrent} concurrent users...")
        
        successful = []
        iterations = 20
        
        def worker():
            return single_search(TEST_QUERIES[0])
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=concurrent) as executor:
            futures = [executor.submit(worker) for _ in range(iterations)]
            
            for future in as_completed(futures):
                result = future.result()
                if result["success"]:
                    successful.append(result["latency_ms"])
        
        duration = time.time() - start_time
        
        if successful:
            results[concurrent] = {
                "avg_latency_ms": statistics.mean(successful),
                "requests_per_second": iterations / duration,
                "success_rate": len(successful) / iterations * 100
            }
            print(f"  Avg latency: {results[concurrent]['avg_latency_ms']:.1f} ms")
            print(f"  Throughput: {results[concurrent]['requests_per_second']:.1f} req/s")
    
    # Print summary
    print("\nScalability Summary:")
    print("-" * 50)
    print(f"{'Concurrent':>10} | {'Latency (ms)':>12} | {'Throughput':>12} | {'Success':>8}")
    print("-" * 50)
    
    for concurrent, data in results.items():
        print(f"{concurrent:>10} | {data['avg_latency_ms']:>12.1f} | {data['requests_per_second']:>12.1f} | {data['success_rate']:>7.1f}%")
    
    return results


def run_mode_comparison(iterations: int = 30) -> Dict:
    """
    Compare performance across search modes.
    
    Returns:
        Dictionary with mode comparison data
    """
    print("\n" + "=" * 50)
    print("SEARCH MODE COMPARISON")
    print("=" * 50)
    print(f"Iterations per mode: {iterations}")
    print()
    
    modes = ["hybrid", "knn", "bm25"]
    results = {}
    
    for mode in modes:
        print(f"Testing {mode} mode...")
        latencies = []
        
        for i in range(iterations):
            query = TEST_QUERIES[i % len(TEST_QUERIES)]
            result = single_search(query, search_mode=mode)
            
            if result["success"]:
                latencies.append(result["latency_ms"])
        
        if latencies:
            results[mode] = {
                "avg_ms": statistics.mean(latencies),
                "min_ms": min(latencies),
                "max_ms": max(latencies),
                "std_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0
            }
    
    # Print comparison
    print("\nMode Comparison Results:")
    print("-" * 50)
    print(f"{'Mode':>8} | {'Avg (ms)':>10} | {'Min (ms)':>10} | {'Max (ms)':>10}")
    print("-" * 50)
    
    for mode, data in results.items():
        print(f"{mode:>8} | {data['avg_ms']:>10.1f} | {data['min_ms']:>10.1f} | {data['max_ms']:>10.1f}")
    
    return results


def generate_performance_report(
    latency_stats: Dict,
    throughput_stats: Dict,
    scalability_stats: Dict,
    mode_comparison: Dict
) -> str:
    """Generate performance test report"""
    
    report = []
    report.append("\n" + "=" * 60)
    report.append("SEARCH PERFORMANCE REPORT")
    report.append("=" * 60)
    report.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"API: {API_BASE_URL}")
    report.append("")
    
    # Latency Summary
    report.append("LATENCY SUMMARY")
    report.append("-" * 40)
    for mode, stats in latency_stats.items():
        if "error" not in stats:
            report.append(f"{mode}: avg={stats['avg_ms']:.1f}ms, p95={stats['p95_ms']:.1f}ms")
    
    # Throughput Summary
    report.append("")
    report.append("THROUGHPUT SUMMARY")
    report.append("-" * 40)
    report.append(f"Requests/Second: {throughput_stats.get('requests_per_second', 0):.1f}")
    report.append(f"Success Rate: {throughput_stats.get('success_rate', 0):.1f}%")
    
    # Performance Rating
    report.append("")
    report.append("PERFORMANCE RATING")
    report.append("-" * 40)
    
    avg_latency = latency_stats.get("hybrid", {}).get("avg_ms", 999)
    throughput = throughput_stats.get("requests_per_second", 0)
    
    if avg_latency < 100 and throughput > 50:
        rating = "EXCELLENT ⭐⭐⭐⭐⭐"
    elif avg_latency < 200 and throughput > 30:
        rating = "GOOD ⭐⭐⭐⭐"
    elif avg_latency < 500 and throughput > 10:
        rating = "ACCEPTABLE ⭐⭐⭐"
    elif avg_latency < 1000:
        rating = "NEEDS OPTIMIZATION ⭐⭐"
    else:
        rating = "POOR ⭐"
    
    report.append(f"Overall Rating: {rating}")
    
    report.append("\n" + "=" * 60)
    
    return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description="Search Performance Test")
    parser.add_argument("--iterations", type=int, default=30, help="Iterations for latency test")
    parser.add_argument("--concurrent", type=int, default=5, help="Concurrent users for throughput")
    parser.add_argument("--duration", type=int, default=30, help="Duration for throughput test (sec)")
    parser.add_argument("--quick", action="store_true", help="Run quick test only")
    args = parser.parse_args()
    
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 12 + "SEARCH PERFORMANCE TEST" + " " * 23 + "║")
    print("╚" + "=" * 58 + "╝")
    
    # Check API availability
    try:
        resp = requests.get(f"{API_BASE_URL}/search/config", timeout=5)
        if resp.status_code != 200:
            print(f"❌ API not available: {resp.status_code}")
            return
        print("✅ API connected")
    except Exception as e:
        print(f"❌ Cannot connect to API: {e}")
        return
    
    # Run tests
    if args.quick:
        print("\n🚀 Running quick test...")
        latency_stats = run_latency_test(iterations=10)
        throughput_stats = {"requests_per_second": 0, "success_rate": 0}
        scalability_stats = {}
        mode_comparison = run_mode_comparison(iterations=10)
    else:
        latency_stats = run_latency_test(iterations=args.iterations)
        throughput_stats = run_throughput_test(concurrent=args.concurrent, duration_sec=args.duration)
        scalability_stats = run_scalability_test(max_concurrent=10)
        mode_comparison = run_mode_comparison(iterations=args.iterations)
    
    # Generate report
    report = generate_performance_report(
        latency_stats, throughput_stats, scalability_stats, mode_comparison
    )
    print(report)
    
    # Save report
    report_file = f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, "w") as f:
        f.write(report)
    print(f"\n📄 Report saved to: {report_file}")


if __name__ == "__main__":
    main()

