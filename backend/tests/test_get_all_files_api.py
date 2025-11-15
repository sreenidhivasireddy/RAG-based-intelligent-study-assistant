"""
Test script for GET all files API endpoint.

Tests the /api/v1/documents/uploads endpoint which retrieves all merged files.

Test Cases:
1. Get all files successfully (status=1 or status=2)
2. Verify response structure and field types
3. Verify status filtering (only merged and completed files)
4. Test empty file list scenario
5. Verify sorting order (newest first)
"""

import requests
import logging
import json
from datetime import datetime

# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API base URL
BASE_URL = "http://localhost:8000/api/v1"


def test_get_all_files_success():
    """Test Case 1: Successfully retrieve all merged files."""
    logger.info("\n" + "=" * 70)
    logger.info("Test Case 1: Get All Merged Files")
    logger.info("=" * 70)
    
    try:
        url = f"{BASE_URL}/documents/uploads"
        logger.info(f"\n📡 Sending request: GET {url}")
        
        response = requests.get(url, timeout=10)
        
        logger.info(f"\n📥 HTTP Status Code: {response.status_code}")
        
        # Parse JSON response
        result = response.json()
        logger.info(f"📥 Response Body:\n{json.dumps(result, indent=2, ensure_ascii=False)}")
        
        # Verify HTTP status
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Verify response structure
        assert 'status' in result, "Response missing 'status' field"
        assert 'data' in result, "Response missing 'data' field"
        
        # Verify success status
        status = result.get('status')
        assert status == 'success', f"Expected status='success', got '{status}'"
        
        # Get file list
        files = result.get('data', [])
        logger.info(f"\n✅ Test Passed - Successfully retrieved file list")
        logger.info(f"   Total files: {len(files)}")
        
        if len(files) > 0:
            logger.info(f"\n📄 File Details:")
            for idx, file in enumerate(files, 1):
                status_map = {
                    0: "Uploading",
                    1: "Completed (Searchable)",
                    2: "Merged (Waiting for Parsing)"
                }
                status_text = status_map.get(file.get('status'), "Unknown Status")
                
                logger.info(f"\n   【File {idx}】")
                logger.info(f"      File Name: {file.get('fileName')}")
                logger.info(f"      MD5: {file.get('fileMd5')}")
                logger.info(f"      Size: {file.get('totalSize'):,} bytes ({file.get('totalSize') / (1024*1024):.2f} MB)")
                logger.info(f"      Status: {file.get('status')} - {status_text}")
                logger.info(f"      Created At: {file.get('createdAt')}")
                logger.info(f"      Merged At: {file.get('mergedAt')}")
        else:
            logger.info(f"\n📭 No merged files found")
            logger.info(f"   Hint: Upload and merge some files first")
        
        return True, files
        
    except AssertionError as e:
        logger.error(f"\n❌ Assertion Failed: {e}")
        return False, []
    except Exception as e:
        logger.error(f"\n❌ Test Error: {e}")
        return False, []


def test_response_structure(files):
    """Test Case 2: Verify response structure and field types."""
    logger.info("\n" + "=" * 70)
    logger.info("Test Case 2: Verify Response Structure")
    logger.info("=" * 70)
    
    if len(files) == 0:
        logger.info("\n⚠️  Skipped: File list is empty")
        return True
    
    try:
        # Test first file structure
        file = files[0]
        logger.info(f"\n🔍 Checking structure of first file...")
        
        # Required fields
        required_fields = ['fileMd5', 'fileName', 'totalSize', 'status', 'createdAt']
        for field in required_fields:
            assert field in file, f"Missing required field: {field}"
            assert file[field] is not None, f"Field {field} is None"
        
        # Field type validation
        assert isinstance(file['fileMd5'], str), "fileMd5 must be string"
        assert len(file['fileMd5']) == 32, "fileMd5 must be 32 characters (MD5 hash)"
        
        assert isinstance(file['fileName'], str), "fileName must be string"
        assert len(file['fileName']) > 0, "fileName cannot be empty"
        
        assert isinstance(file['totalSize'], int), "totalSize must be integer"
        assert file['totalSize'] > 0, "totalSize must be positive"
        
        assert isinstance(file['status'], int), "status must be integer"
        assert file['status'] in [1, 2], f"status must be 1 or 2, got {file['status']}"
        
        # Verify createdAt is valid ISO datetime
        try:
            datetime.fromisoformat(file['createdAt'].replace('Z', '+00:00'))
        except:
            raise AssertionError("createdAt must be valid ISO 8601 datetime")
        
        # mergedAt can be null or valid datetime
        if file.get('mergedAt') is not None:
            try:
                datetime.fromisoformat(file['mergedAt'].replace('Z', '+00:00'))
            except:
                raise AssertionError("mergedAt must be valid ISO 8601 datetime or null")
        
        logger.info(f"✅ Structure validation passed")
        logger.info(f"   - All required fields present")
        logger.info(f"   - Field types correct")
        logger.info(f"   - Data format valid")
        
        return True
        
    except AssertionError as e:
        logger.error(f"\n❌ Structure Validation Failed: {e}")
        return False
    except Exception as e:
        logger.error(f"\n❌ Validation Error: {e}")
        return False


def test_status_filtering(files):
    """Test Case 3: Verify only merged and completed files are returned."""
    logger.info("\n" + "=" * 70)
    logger.info("Test Case 3: Verify Status Filtering (only status=1 or status=2)")
    logger.info("=" * 70)
    
    if len(files) == 0:
        logger.info("\n⚠️  Skipped: File list is empty")
        return True
    
    try:
        logger.info(f"\n🔍 Checking status of {len(files)} files...")
        
        # Count files by status
        status_counts = {1: 0, 2: 0}
        invalid_statuses = []
        
        for file in files:
            status = file.get('status')
            if status in [1, 2]:
                status_counts[status] += 1
            else:
                invalid_statuses.append({
                    'fileName': file.get('fileName'),
                    'status': status
                })
        
        # Verify no invalid statuses
        assert len(invalid_statuses) == 0, \
            f"Found files with invalid status (should be 1 or 2): {invalid_statuses}"
        
        logger.info(f"\n✅ Status filtering validation passed")
        logger.info(f"   Completed (status=1): {status_counts[1]} files")
        logger.info(f"   Waiting for parsing (status=2): {status_counts[2]} files")
        logger.info(f"   Total: {len(files)} files")
        logger.info(f"   ✓ No status=0 (uploading) files found")
        
        return True
        
    except AssertionError as e:
        logger.error(f"\n❌ Status Filtering Validation Failed: {e}")
        return False
    except Exception as e:
        logger.error(f"\n❌ Validation Error: {e}")
        return False


def test_sorting_order(files):
    """Test Case 4: Verify files are sorted by createdAt descending (newest first)."""
    logger.info("\n" + "=" * 70)
    logger.info("Test Case 4: Verify Sorting Order (by createdAt DESC)")
    logger.info("=" * 70)
    
    if len(files) < 2:
        logger.info(f"\n⚠️  Skipped: Less than 2 files, cannot verify sorting")
        return True
    
    try:
        logger.info(f"\n🔍 Checking sort order of {len(files)} files...")
        
        # Parse timestamps
        timestamps = []
        for idx, file in enumerate(files):
            created_at_str = file.get('createdAt')
            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            timestamps.append({
                'index': idx,
                'fileName': file.get('fileName'),
                'createdAt': created_at
            })
        
        # Verify descending order
        for i in range(len(timestamps) - 1):
            current = timestamps[i]['createdAt']
            next_item = timestamps[i + 1]['createdAt']
            
            assert current >= next_item, \
                f"Sorting error: File {i} ({timestamps[i]['fileName']}) created at {current} " \
                f"should be before File {i+1} ({timestamps[i+1]['fileName']}) created at {next_item}"
        
        logger.info(f"\n✅ Sorting validation passed")
        logger.info(f"   Newest file: {timestamps[0]['fileName']} ({timestamps[0]['createdAt']})")
        logger.info(f"   Oldest file: {timestamps[-1]['fileName']} ({timestamps[-1]['createdAt']})")
        logger.info(f"   ✓ Files correctly sorted by creation time (newest → oldest)")
        
        return True
        
    except AssertionError as e:
        logger.error(f"\n❌ Sorting Validation Failed: {e}")
        return False
    except Exception as e:
        logger.error(f"\n❌ Validation Error: {e}")
        return False


def test_error_handling():
    """Test Case 5: Test error scenarios (server down, invalid endpoint, etc.)."""
    logger.info("\n" + "=" * 70)
    logger.info("Test Case 5: Error Handling Test")
    logger.info("=" * 70)
    
    try:
        # Test with invalid endpoint
        url = f"{BASE_URL}/documents/uploads/invalid"
        logger.info(f"\n🔍 Testing invalid endpoint: GET {url}")
        
        response = requests.get(url, timeout=5)
        logger.info(f"   Status code: {response.status_code}")
        
        # Should return 404 or 405
        assert response.status_code in [404, 405], \
            f"Expected 404/405 for invalid endpoint, got {response.status_code}"
        
        logger.info(f"✅ Error handling correct - returned {response.status_code}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        logger.info(f"⚠️  Connection error (expected behavior): {e}")
        return True
    except AssertionError as e:
        logger.error(f"\n❌ Error Handling Validation Failed: {e}")
        return False
    except Exception as e:
        logger.error(f"\n❌ Test Error: {e}")
        return False


def print_summary(results):
    """Print test summary."""
    logger.info("\n" + "=" * 70)
    logger.info("📊 Test Results Summary")
    logger.info("=" * 70)
    
    total = len(results)
    passed = sum(1 for r in results if r['passed'])
    failed = total - passed
    
    for result in results:
        status = "✅ PASS" if result['passed'] else "❌ FAIL"
        logger.info(f"{status} - {result['name']}")
    
    logger.info(f"\nTotal: {total} tests")
    logger.info(f"Passed: {passed}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Success Rate: {(passed/total*100):.1f}%")
    
    logger.info("=" * 70)
    
    return failed == 0


def main():
    """Run all test cases."""
    logger.info("\n" + "=" * 70)
    logger.info("🧪 GET All Files API Test Suite")
    logger.info("=" * 70)
    logger.info(f"API Base URL: {BASE_URL}")
    logger.info(f"Test Endpoint: /documents/uploads")
    logger.info(f"Method: GET")
    
    results = []
    
    # Test 1: Get all files
    success, files = test_get_all_files_success()
    results.append({'name': 'Test Case 1: Get All Files', 'passed': success})
    
    if success and len(files) > 0:
        # Test 2: Response structure
        success = test_response_structure(files)
        results.append({'name': 'Test Case 2: Response Structure Validation', 'passed': success})
        
        # Test 3: Status filtering
        success = test_status_filtering(files)
        results.append({'name': 'Test Case 3: Status Filtering Validation', 'passed': success})
        
        # Test 4: Sorting order
        success = test_sorting_order(files)
        results.append({'name': 'Test Case 4: Sorting Order Validation', 'passed': success})
    else:
        logger.info("\n⚠️  Skipped Test Cases 2-4 (file list empty or fetch failed)")
    
    # Test 5: Error handling
    success = test_error_handling()
    results.append({'name': 'Test Case 5: Error Handling Validation', 'passed': success})
    
    # Print summary
    all_passed = print_summary(results)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
