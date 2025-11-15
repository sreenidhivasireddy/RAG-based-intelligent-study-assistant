"""
Integration tests for ParseService with database.

This test suite tests the full parse_and_save workflow with a real database connection.
It tests:
1. Parsing text files
2. Saving chunks to database
3. Querying saved data
4. Cleanup

Prerequisites:
- MySQL database running
- Database configured in .env file
- document_vectors table created
"""

import sys
import io
import os
import hashlib
from pathlib import Path

# Add the backend directory to the path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from sqlalchemy import text
from app.database import SessionLocal, engine, Base
from app.models.documentVector import DocumentVector
from app.services.parse_service import ParseService
from app.repositories.document_vector_repository import (
    find_by_file_md5,
    delete_by_file_md5,
    count_by_file_md5,
)

# Track test file MD5s for cleanup
TEST_FILE_MD5S = []


def setup_database():
    """Create tables if they don't exist"""
    print("Setting up database...")
    try:
        # Create all tables
        Base.metadata.create_all(bind=engine)
        print("✓ Database tables created/verified")
        return True
    except Exception as e:
        print(f"❌ Database setup failed: {e}")
        return False


def test_database_connection():
    """Test if we can connect to the database"""
    print("\n" + "=" * 60)
    print("Test 1: Database Connection")
    print("=" * 60)
    
    try:
        db = SessionLocal()
        # Try a simple query
        result = db.execute(text("SELECT 1"))
        result.fetchone()
        db.close()
        print("✓ Database connection successful")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\nPlease check:")
        print("  1. MySQL is running")
        print("  2. .env file has correct database credentials")
        print("  3. Database exists")
        return False


def test_parse_and_save_text_file():
    """Test parsing and saving a text file"""
    print("\n" + "=" * 60)
    print("Test 2: Parse and Save Text File")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Create test text file content
        test_content = """
            人工智能简介

            人工智能（Artificial Intelligence，AI）是计算机科学的一个分支。
            它试图了解智能的实质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。

            机器学习基础

            机器学习是人工智能的核心。它使计算机能够从数据中学习。
            深度学习是机器学习的一个分支。神经网络是深度学习的基础。

            应用场景

            该领域的研究包括机器人、语言识别、图像识别、自然语言处理和专家系统等。
            现代AI技术已经广泛应用于各个行业。
        """
        
        # Calculate MD5
        file_md5 = hashlib.md5(test_content.encode()).hexdigest()
        filename = "test_ai_intro.txt"
        
        # Track for cleanup
        TEST_FILE_MD5S.append(file_md5)
        
        print(f"Test file MD5: {file_md5}")
        print(f"Content length: {len(test_content)} characters")
        
        # Clean up any existing data for this file
        delete_by_file_md5(db, file_md5)
        
        # Create file stream
        file_stream = io.BytesIO(test_content.encode('utf-8'))
        
        # Parse and save
        service = ParseService(chunk_size=100)
        chunk_count = service.parse_and_save(
            file_md5=file_md5,
            filename=filename,
            file_stream=file_stream,
            db=db
        )
        
        print(f"✓ Parsed and saved: {chunk_count} chunks")
        
        # Verify data in database
        vectors = find_by_file_md5(db, file_md5)
        print(f"✓ Found in database: {len(vectors)} chunks")
        
        # Display first few chunks
        print("\nFirst 3 chunks:")
        for i, vector in enumerate(vectors[:3], 1):
            content_preview = vector.text_content[:50] + "..." if len(vector.text_content) > 50 else vector.text_content
            print(f"  Chunk {vector.chunk_id}: {content_preview}")
        
        assert len(vectors) > 0, "No chunks were saved to database"
        assert len(vectors) == chunk_count, f"Expected {chunk_count} chunks, found {len(vectors)}"
        
        print("\n✓ Test 2 passed")
        return True
        
    except Exception as e:
        print(f"\n❌ Test 2 failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_parse_and_save_with_different_chunk_sizes():
    """Test parsing with different chunk sizes"""
    print("\n" + "=" * 60)
    print("Test 3: Different Chunk Sizes")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        test_content = "这是一个测试句子。" * 50  # 500 characters
        
        results = []
        
        for chunk_size in [50, 100, 200]:
            file_md5 = hashlib.md5(f"{test_content}_{chunk_size}".encode()).hexdigest()
            
            # Track for cleanup
            TEST_FILE_MD5S.append(file_md5)
            
            # Clean up
            delete_by_file_md5(db, file_md5)
            
            # Parse with specific chunk size
            service = ParseService(chunk_size=chunk_size)
            file_stream = io.BytesIO(test_content.encode('utf-8'))
            
            chunk_count = service.parse_and_save(
                file_md5=file_md5,
                filename=f"test_{chunk_size}.txt",
                file_stream=file_stream,
                db=db
            )
            
            results.append((chunk_size, chunk_count))
            print(f"  Chunk size {chunk_size}: {chunk_count} chunks")
        
        # Verify that smaller chunk sizes produce more chunks
        assert results[0][1] >= results[1][1] >= results[2][1], "Smaller chunk sizes should produce more chunks"
        
        print("\n✓ Test 3 passed")
        return True
        
    except Exception as e:
        print(f"\n❌ Test 3 failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_parse_and_save_large_content():
    """Test parsing large content"""
    print("\n" + "=" * 60)
    print("Test 4: Large Content Processing")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Create a large text (simulate a real document)
        large_content = ""
        for i in range(100):
            large_content += f"\n\n段落 {i+1}\n\n"
            large_content += f"这是第{i+1}个段落的内容。" * 20
        
        file_md5 = hashlib.md5(large_content.encode()).hexdigest()
        
        # Track for cleanup
        TEST_FILE_MD5S.append(file_md5)
        
        print(f"Content size: {len(large_content)} characters")
        
        # Clean up
        delete_by_file_md5(db, file_md5)
        
        # Parse
        service = ParseService(chunk_size=500)
        file_stream = io.BytesIO(large_content.encode('utf-8'))
        
        chunk_count = service.parse_and_save(
            file_md5=file_md5,
            filename="large_test.txt",
            file_stream=file_stream,
            db=db
        )
        
        print(f"✓ Processed large content: {chunk_count} chunks")
        
        # Verify
        count_in_db = count_by_file_md5(db, file_md5)
        assert count_in_db == chunk_count, f"Expected {chunk_count}, found {count_in_db}"
        
        print(f"✓ All chunks saved to database")
        print("\n✓ Test 4 passed")
        return True
        
    except Exception as e:
        print(f"\n❌ Test 4 failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_query_and_cleanup():
    """Test querying and cleanup operations"""
    print("\n" + "=" * 60)
    print("Test 5: Query and Cleanup")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Create test data
        test_content = "测试内容 " * 10
        file_md5 = hashlib.md5(test_content.encode()).hexdigest()
        
        # Track for cleanup
        TEST_FILE_MD5S.append(file_md5)
        
        # Parse and save
        service = ParseService()
        file_stream = io.BytesIO(test_content.encode('utf-8'))
        chunk_count = service.parse_and_save(
            file_md5=file_md5,
            filename="cleanup_test.txt",
            file_stream=file_stream,
            db=db
        )
        
        print(f"✓ Created {chunk_count} chunks")
        
        # Query
        vectors = find_by_file_md5(db, file_md5)
        print(f"✓ Queried {len(vectors)} chunks")
        
        # Cleanup
        deleted_count = delete_by_file_md5(db, file_md5)
        print(f"✓ Deleted {deleted_count} chunks")
        
        # Verify cleanup
        remaining = count_by_file_md5(db, file_md5)
        assert remaining == 0, f"Expected 0 remaining, found {remaining}"
        
        print("✓ Cleanup verified")
        print("\n✓ Test 5 passed")
        return True
        
    except Exception as e:
        print(f"\n❌ Test 5 failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def cleanup_all_test_data():
    """Clean up all test data from database"""
    print("\n" + "=" * 60)
    print("Cleaning up test data...")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Count records before cleanup
        result = db.execute(text("SELECT COUNT(*) FROM document_vectors"))
        count_before = result.fetchone()[0]
        print(f"Total records before cleanup: {count_before}")
        
        if TEST_FILE_MD5S:
            # Delete only test records by file_md5
            total_deleted = 0
            for file_md5 in set(TEST_FILE_MD5S):  # Use set to avoid duplicates
                deleted = delete_by_file_md5(db, file_md5)
                total_deleted += deleted
            
            print(f"✓ Deleted {total_deleted} test records for {len(set(TEST_FILE_MD5S))} test files")
        else:
            print("✓ No test files tracked for cleanup")
        
        # Verify cleanup
        result = db.execute(text("SELECT COUNT(*) FROM document_vectors"))
        count_after = result.fetchone()[0]
        print(f"Total records after cleanup: {count_after}")
        
        db.close()
        print("✓ Cleanup completed")
        
    except Exception as e:
        print(f"⚠ Cleanup warning: {e}")
        import traceback
        traceback.print_exc()
        db.close()


def run_all_tests():
    """Run all database integration tests"""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 8 + "ParseService Database Integration Tests" + " " * 11 + "║")
    print("╚" + "═" * 58 + "╝")
    print("\n")
    
    # Setup
    if not setup_database():
        print("\n❌ Database setup failed. Aborting tests.")
        return False
    
    # Run tests
    results = []
    
    results.append(("Database Connection", test_database_connection()))
    
    if not results[-1][1]:
        print("\n❌ Cannot proceed without database connection")
        return False
    
    results.append(("Parse and Save Text File", test_parse_and_save_text_file()))
    results.append(("Different Chunk Sizes", test_parse_and_save_with_different_chunk_sizes()))
    results.append(("Large Content Processing", test_parse_and_save_large_content()))
    results.append(("Query and Cleanup", test_query_and_cleanup()))
    
    # Cleanup
    cleanup_all_test_data()
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:40} {status}")
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    print("=" * 60)
    print(f"Total: {passed_count}/{total_count} tests passed")
    print("=" * 60)
    
    if passed_count == total_count:
        print("\n🎉 All database integration tests passed!")
        return True
    else:
        print(f"\n⚠ {total_count - passed_count} test(s) failed")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

