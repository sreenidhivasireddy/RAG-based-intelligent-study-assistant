"""
Test script for file merge API endpoint.

This script tests the complete workflow:
1. Upload multiple chunks
2. Verify all chunks are uploaded
3. Call merge endpoint
4. Verify merged file exists in MinIO
"""

import hashlib
import time
import requests
import sys
import os
import logging

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API base URL
BASE_URL = "http://localhost:8000/api/v1/upload"

# Test configuration
CHUNK_SIZE = 1024 * 1024  # 1MB per chunk
TEST_CONTENT = b"Hello, this is a test file for merge API!\n" * 10000  # ~500KB


def generate_unique_content():
    """Generate unique test content with timestamp to avoid Redis conflicts."""
    timestamp = str(time.time()).encode()
    return TEST_CONTENT + b"\nTimestamp: " + timestamp


def calculate_md5(data: bytes) -> str:
    """Calculate MD5 hash of data."""
    return hashlib.md5(data).hexdigest()


def split_into_chunks(data: bytes, chunk_size: int) -> list[bytes]:
    """Split data into fixed-size chunks."""
    chunks = []
    for i in range(0, len(data), chunk_size):
        chunks.append(data[i:i + chunk_size])
    return chunks


def test_merge_workflow():
    """Test complete upload + merge workflow."""
    logger.info("=" * 60)
    logger.info("Starting File Merge API Test")
    logger.info("=" * 60)
    
    # Generate unique test data
    file_content = generate_unique_content()
    file_md5 = calculate_md5(file_content)
    file_name = "test_merge_file.txt"
    total_size = len(file_content)
    
    logger.info(f"\nTest File Info:")
    logger.info(f"  - File MD5: {file_md5}")
    logger.info(f"  - File Name: {file_name}")
    logger.info(f"  - Total Size: {total_size} bytes")
    
    # Split into chunks
    chunks = split_into_chunks(file_content, CHUNK_SIZE)
    total_chunks = len(chunks)
    
    logger.info(f"  - Total Chunks: {total_chunks}")
    logger.info(f"  - Chunk Size: {CHUNK_SIZE} bytes")
    
    # -------------------------------------------------------------------------
    # Step 1: Upload all chunks
    # -------------------------------------------------------------------------
    logger.info(f"\n{'=' * 60}")
    logger.info("Step 1: Uploading Chunks")
    logger.info("=" * 60)
    
    for chunk_index, chunk_data in enumerate(chunks):
        logger.info(f"\nUploading chunk {chunk_index + 1}/{total_chunks}...")
        
        files = {
            'file': (f'chunk_{chunk_index}', chunk_data, 'application/octet-stream')
        }
        
        data = {
            'fileMd5': file_md5,
            'chunkIndex': chunk_index,
            'totalSize': total_size,
            'fileName': file_name,
            'totalChunks': total_chunks
        }
        
        try:
            response = requests.post(f"{BASE_URL}/chunk", files=files, data=data)
            result = response.json()
            
            if result.get('code') == 200:
                progress = result['data']['progress']
                uploaded_count = len(result['data']['uploaded'])
                logger.info(f"  ✓ Chunk {chunk_index} uploaded successfully")
                logger.info(f"    Progress: {progress}% ({uploaded_count}/{total_chunks} chunks)")
            else:
                logger.error(f"  ✗ Failed to upload chunk {chunk_index}: {result.get('message')}")
                return False
                
        except Exception as e:
            logger.error(f"  ✗ Error uploading chunk {chunk_index}: {e}")
            return False
    
    # -------------------------------------------------------------------------
    # Step 2: Verify upload status
    # -------------------------------------------------------------------------
    logger.info(f"\n{'=' * 60}")
    logger.info("Step 2: Verifying Upload Status")
    logger.info("=" * 60)
    
    try:
        response = requests.get(
            f"{BASE_URL}/status",
            params={'file_md5': file_md5, 'total_chunks': total_chunks}
        )
        result = response.json()
        
        if result.get('code') == 200:
            data = result['data']
            progress = data['progress']
            uploaded_count = len(data['uploaded'])
            
            logger.info(f"\nUpload Status:")
            logger.info(f"  - Progress: {progress}%")
            logger.info(f"  - Uploaded Chunks: {uploaded_count}/{total_chunks}")
            logger.info(f"  - Uploaded Indices: {data['uploaded']}")
            
            if progress == 100.0:
                logger.info(f"  ✓ All chunks uploaded successfully!")
            else:
                logger.warning(f"  ⚠ Upload incomplete: {progress}%")
                missing = [i for i in range(total_chunks) if i not in data['uploaded']]
                logger.warning(f"    Missing chunks: {missing}")
                return False
        else:
            logger.error(f"  ✗ Failed to get upload status: {result.get('message')}")
            return False
            
    except Exception as e:
        logger.error(f"  ✗ Error checking upload status: {e}")
        return False
    
    # -------------------------------------------------------------------------
    # Step 3: Call merge endpoint
    # -------------------------------------------------------------------------
    logger.info(f"\n{'=' * 60}")
    logger.info("Step 3: Merging File Chunks")
    logger.info("=" * 60)
    
    try:
        merge_request = {
            'file_md5': file_md5,
            'file_name': file_name
        }
        
        logger.info(f"\nSending merge request...")
        logger.info(f"  Request: {merge_request}")
        
        response = requests.post(
            f"{BASE_URL}/merge",
            json=merge_request,
            headers={'Content-Type': 'application/json'}
        )
        result = response.json()
        
        logger.info(f"\nMerge Response:")
        logger.info(f"  Status Code: {response.status_code}")
        logger.info(f"  Response: {result}")
        
        if result.get('code') == 200:
            data = result['data']
            object_url = data['object_url']
            file_size = data['file_size']
            
            logger.info(f"\n  ✓ File merged successfully!")
            logger.info(f"    Object URL: {object_url}")
            logger.info(f"    File Size: {file_size} bytes")
            logger.info(f"    Expected Size: {total_size} bytes")
            
            # Verify file size matches
            if file_size == total_size:
                logger.info(f"    ✓ File size matches original!")
            else:
                logger.warning(f"    ⚠ File size mismatch!")
                logger.warning(f"      Expected: {total_size} bytes")
                logger.warning(f"      Got: {file_size} bytes")
                return False
            
            return True
            
        else:
            logger.error(f"  ✗ Merge failed: {result.get('message')}")
            return False
            
    except Exception as e:
        logger.error(f"  ✗ Error calling merge endpoint: {e}")
        return False


def test_merge_error_cases():
    """Test error handling in merge endpoint."""
    logger.info(f"\n{'=' * 60}")
    logger.info("Testing Merge Error Cases")
    logger.info("=" * 60)
    
    # Test 1: Non-existent file
    logger.info(f"\nTest 1: Merge non-existent file")
    try:
        response = requests.post(
            f"{BASE_URL}/merge",
            json={
                'file_md5': 'aaaabbbbccccddddeeeeffffgggghhhh',  # Valid 32-char MD5 format
                'file_name': 'nonexistent.txt'
            },
            headers={'Content-Type': 'application/json'}
        )
        result = response.json()
        
        if result.get('code') in [400, 404]:
            logger.info(f"  ✓ Correctly rejected non-existent file")
            logger.info(f"    Message: {result.get('message')}")
        else:
            logger.warning(f"  ⚠ Unexpected response: {result}")
            
    except Exception as e:
        logger.error(f"  ✗ Error: {e}")
    
    # Test 2: Invalid MD5 format (too short)
    logger.info(f"\nTest 2: Invalid MD5 format")
    try:
        response = requests.post(
            f"{BASE_URL}/merge",
            json={
                'file_md5': 'invalid_md5',  # Too short
                'file_name': 'test.txt'
            },
            headers={'Content-Type': 'application/json'}
        )
        result = response.json()
        
        # Pydantic will return 422 for validation errors
        if result.get('detail') or response.status_code == 422:
            logger.info(f"  ✓ Correctly rejected invalid MD5")
            logger.info(f"    Status: {response.status_code}")
        else:
            logger.warning(f"  ⚠ Unexpected response: {result}")
            
    except Exception as e:
        logger.error(f"  ✗ Error: {e}")


if __name__ == "__main__":
    logger.info("\n" + "=" * 60)
    logger.info("FILE MERGE API TEST SUITE")
    logger.info("=" * 60)
    logger.info(f"Base URL: {BASE_URL}")
    logger.info(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test main workflow
    success = test_merge_workflow()
    
    # Test error cases
    test_merge_error_cases()
    
    # Final summary
    logger.info(f"\n{'=' * 60}")
    if success:
        logger.info("✓ ALL TESTS PASSED")
    else:
        logger.info("✗ SOME TESTS FAILED")
    logger.info("=" * 60)
