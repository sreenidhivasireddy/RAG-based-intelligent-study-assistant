"""
Simple test script for Upload API endpoints
Run this after starting the server with: uvicorn app.main:app --reload
"""

import requests
import hashlib
import time

BASE_URL = "http://127.0.0.1:8000/api/v1/upload"

def test_status_not_found():
    """Test status API for non-existent file (should return 404)"""
    print("\n" + "="*60)
    print("TEST 1: Query status for non-existent file")
    print("="*60)
    
    file_md5 = "00000000000000000000000000000000"
    response = requests.get(f"{BASE_URL}/status", params={"file_md5": file_md5})
    
    print(f"Request: GET {BASE_URL}/status?file_md5={file_md5}")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.json()["code"] == 404
    print("✅ Test passed!")

def test_upload_chunk():
    """Test uploading a single chunk"""
    print("\n" + "="*60)
    print("TEST 2: Upload a chunk")
    print("="*60)
    
    # Create test data with timestamp to ensure uniqueness
    import time
    test_data = b"This is test chunk data for upload testing" + str(time.time()).encode()
    file_md5 = hashlib.md5(test_data * 5).hexdigest()  # MD5 of full "file"
    
    print(f"Test data size: {len(test_data)} bytes")
    print(f"File MD5: {file_md5}")
    
    # Upload chunk
    files = {'file': ('chunk_0.bin', test_data)}
    data = {
        'fileMd5': file_md5,
        'chunkIndex': 0,
        'totalSize': len(test_data) * 5,
        'fileName': 'test_file.txt',
        'totalChunks': 5
    }
    
    response = requests.post(f"{BASE_URL}/chunk", files=files, data=data)
    
    print(f"Request: POST {BASE_URL}/chunk")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    result = response.json()
    assert result["code"] == 200
    assert result["data"]["progress"] == 20.0  # 1/5 = 20%
    assert 0 in result["data"]["uploaded"]
    print("✅ Test passed!")
    
    return file_md5

def test_status_after_upload(file_md5):
    """Test status API after uploading a chunk"""
    print("\n" + "="*60)
    print("TEST 3: Query status after upload")
    print("="*60)
    
    response = requests.get(f"{BASE_URL}/status", params={"file_md5": file_md5})
    
    print(f"Request: GET {BASE_URL}/status?file_md5={file_md5}")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    result = response.json()
    assert result["code"] == 200
    assert 0 in result["data"]["uploaded"]
    assert result["data"]["progress"] > 0
    print("✅ Test passed!")

def test_upload_multiple_chunks():
    """Test uploading multiple chunks"""
    print("\n" + "="*60)
    print("TEST 4: Upload multiple chunks")
    print("="*60)
    
    # Create test file data with timestamp to ensure uniqueness
    import time
    full_data = b"A" * 1000 + b"B" * 1000 + b"C" * 1000 + str(time.time()).encode()
    file_md5 = hashlib.md5(full_data).hexdigest()
    
    # Split into 3 chunks
    chunk_size = 1000
    total_chunks = 3
    
    print(f"Total file size: {len(full_data)} bytes")
    print(f"Chunks: {total_chunks}")
    print(f"File MD5: {file_md5}")
    
    for i in range(total_chunks):
        chunk_data = full_data[i*chunk_size:(i+1)*chunk_size]
        
        files = {'file': (f'chunk_{i}.bin', chunk_data)}
        data = {
            'fileMd5': file_md5,
            'chunkIndex': i,
            'totalSize': len(full_data),
            'fileName': 'multi_chunk_file.bin',
            'totalChunks': total_chunks
        }
        
        response = requests.post(f"{BASE_URL}/chunk", files=files, data=data)
        result = response.json()
        
        print(f"\nChunk {i}:")
        print(f"  Response: {result}")
        print(f"  Progress: {result['data']['progress']}%")
        
        expected_progress = (i + 1) / total_chunks * 100
        actual_progress = result["data"]["progress"]
        assert result["code"] == 200
        # Allow small floating point difference
        assert abs(actual_progress - expected_progress) < 0.1, f"Expected ~{expected_progress:.1f}%, got {actual_progress}%"
    
    print("\n✅ All chunks uploaded successfully!")
    
    # Check final status
    response = requests.get(f"{BASE_URL}/status", params={"file_md5": file_md5})
    result = response.json()
    print(f"\nFinal status: {result}")
    assert result["data"]["progress"] == 100.0
    assert len(result["data"]["uploaded"]) == total_chunks
    print("✅ Test passed!")

def test_idempotent_upload():
    """Test that uploading the same chunk twice is idempotent"""
    print("\n" + "="*60)
    print("TEST 5: Idempotent upload (same chunk twice)")
    print("="*60)
    
    import time
    test_data = b"Idempotent test data" + str(time.time()).encode()
    file_md5 = hashlib.md5(test_data).hexdigest()
    
    files = {'file': ('chunk_0.bin', test_data)}
    data = {
        'fileMd5': file_md5,
        'chunkIndex': 0,
        'totalSize': len(test_data),
        'fileName': 'idempotent_test.txt',
        'totalChunks': 1
    }
    
    # Upload first time
    response1 = requests.post(f"{BASE_URL}/chunk", files=files, data=data)
    result1 = response1.json()
    print(f"First upload: {result1}")
    
    # Upload second time (should be idempotent)
    files = {'file': ('chunk_0.bin', test_data)}  # Recreate files object
    response2 = requests.post(f"{BASE_URL}/chunk", files=files, data=data)
    result2 = response2.json()
    print(f"Second upload: {result2}")
    
    assert result1["code"] == 200
    assert result2["code"] == 200
    assert result1["data"]["progress"] == result2["data"]["progress"]
    print("✅ Test passed - upload is idempotent!")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("Upload API Test Suite")
    print("="*60)
    print("\nMake sure the server is running:")
    print("  cd backend")
    print("  python3 -m uvicorn app.main:app --reload")
    print("\n" + "="*60)
    
    input("\nPress Enter to start tests...")
    
    try:
        # Run tests
        test_status_not_found()
        file_md5 = test_upload_chunk()
        test_status_after_upload(file_md5)
        test_upload_multiple_chunks()
        test_idempotent_upload()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to server")
        print("Please start the server first:")
        print("  cd backend")
        print("  python3 -m uvicorn app.main:app --reload")
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
