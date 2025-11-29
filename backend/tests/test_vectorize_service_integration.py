"""
Integration tests for VectorizationService with real database and services.

Test flow:
1. Use ParseService to parse the test document and save to document_vectors table
2. Use VectorizationService to vectorize the saved document
3. Verify the vectorized result is stored in Elasticsearch
4. Clean up test data

Prerequisites:
- MySQL database running
- Elasticsearch running
- .env file configured correctly
- document_vectors table created
"""

import sys
import io
import os
import hashlib
from pathlib import Path
from unittest.mock import Mock, patch
import time

# Add the backend directory to the path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from sqlalchemy import text
from app.database import SessionLocal, engine, Base
from app.models.document_vector import DocumentVector
from app.services.parse_service import ParseService
from app.services.vectorize_service import VectorizationService
from app.repositories import document_vector_repository

# Track test file MD5s for cleanup
TEST_FILE_MD5S = []


def setup_database():
    """Create database tables (if not exist)"""
    print("🔧 Setting up database...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✓ Database tables created/verified successfully")
        return True
    except Exception as e:
        print(f"❌ Database setup failed: {e}")
        return False


def test_database_connection():
    """Test database connection"""
    print("\n" + "=" * 60)
    print("Test 1: Database connection")
    print("=" * 60)
    
    try:
        db = SessionLocal()
        result = db.execute(text("SELECT 1"))
        result.fetchone()
        db.close()
        print("✓ Database connection successful")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\nPlease check:")
        print("  1. MySQL is running")
        print("  2. .env file database configuration is correct")
        print("  3. Database exists")
        return False


def test_step1_parse_and_save():
    """Step 1: Use ParseService to parse and save test document"""
    print("\n" + "=" * 60)
    print("Test 2: Parse and save test document (ParseService)")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Create test text content
        test_content = """
人工智能与机器学习

人工智能（Artificial Intelligence，AI）是计算机科学的一个重要分支。
它研究如何让机器模拟人类智能，使计算机能够像人一样思考和学习。

机器学习是实现人工智能的一种方法。通过机器学习，计算机可以从数据中自动学习规律。
深度学习是机器学习的一个子领域，它使用神经网络来处理复杂的数据。

自然语言处理

自然语言处理（NLP）是人工智能的重要应用领域之一。
它让计算机能够理解、解释和生成人类语言。

NLP 的应用包括机器翻译、情感分析、文本摘要等。
通过深度学习技术，NLP 的性能得到了显著提升。

计算机视觉

计算机视觉让机器能够"看"和理解图像与视频。
它的应用包括人脸识别、物体检测、图像分类等。

卷积神经网络（CNN）是计算机视觉中最常用的深度学习模型。
通过训练，CNN 可以自动学习图像的特征。
        """
        
        # Calculate MD5
        test_file_md5 = hashlib.md5(test_content.encode('utf-8')).hexdigest()
        TEST_FILE_MD5S.append(test_file_md5)
        
        print(f"📄 Test file MD5: {test_file_md5}")
        
        # Clean up old data if exists
        old_count = document_vector_repository.count_by_file_md5(db, test_file_md5)
        if old_count > 0:
            print(f"⚠️  Found old test data ({old_count} items), cleaning up...")
            document_vector_repository.delete_by_file_md5(db, test_file_md5)
        
        # Use ParseService to parse document
        print("📝 Start parsing document...")
        parse_service = ParseService(chunk_size=200)
        
        # Create file stream
        file_stream = io.BytesIO(test_content.encode('utf-8'))

        # Parse and save
        parse_service.parse_and_save(
            file_md5=test_file_md5,
            file_name="test_ai_document.txt",
            file_stream=file_stream,
            db=db
        )
        
        # Verify save result
        saved_chunks = document_vector_repository.find_by_file_md5(db, test_file_md5)
        chunk_count = len(saved_chunks)
        
        print(f"✓ Document parsed successfully")
        print(f"✓ Saved {chunk_count} text chunks")
        
        # Display information of the first few chunks
        print("\n📊 Text chunk preview:")
        for i, chunk in enumerate(saved_chunks[:3], 1):
            content_preview = chunk.text_content[:100] + "..." if len(chunk.text_content) > 100 else chunk.text_content
            print(f"  Chunk {i} (ID: {chunk.chunk_id}): {content_preview}")
        
        if chunk_count > 3:
            print(f"  ... still {chunk_count - 3} chunks")
        
        assert chunk_count > 0, "There should be at least one text chunk"
        print(f"\n✅ Step 1 completed: Successfully parsed and saved {chunk_count} text chunks")
        
        db.close()
        return test_file_md5, chunk_count
        
    except Exception as e:
        print(f"❌ Parse and save failed: {e}")
        import traceback
        traceback.print_exc()
        db.close()
        return None, 0


def test_step2_vectorize_with_mock_services(test_file_md5, expected_chunk_count):
    """Step 2: Use VectorizationService to vectorize (Mock Gemini and ES)"""
    print("\n" + "=" * 60)
    print("Test 3: Vectorize document (VectorizationService)")
    print("=" * 60)
    
    if not test_file_md5:
        print("⚠️  Skip: No test file available")
        return False
    
    db = SessionLocal()
    
    try:
        print(f"📄 Use test file MD5: {test_file_md5}")
        
        # Create Mock Gemini Embedding Client
        print("🔧 Create Mock Gemini Embedding Client...")
        mock_embedding_client = Mock()
        
        # Simulate returning 768-dimensional vectors
        import numpy as np
        mock_vectors = [np.random.rand(768).tolist() for _ in range(expected_chunk_count)]
        mock_embedding_client.embed.return_value = mock_vectors
        print(f"✓ Mock Embedding Client ready (will return {len(mock_vectors)} 768-dimensional vectors)")
        
        # Create Mock Elasticsearch Service
        print("🔧 Create Mock Elasticsearch Service...")
        mock_es_service = Mock()
        mock_es_service.bulk_index.return_value = None  # Assume success
        print("✓ Mock Elasticsearch Service ready")
        
        # Create VectorizationService
        print("\n🚀 Create VectorizationService...")
        vectorize_service = VectorizationService(
            embedding_client=mock_embedding_client,
            elasticsearch_service=mock_es_service,
            db=db
        )
        print("✓ VectorizationService created successfully")
        
        # Execute vectorization
        print(f"\n📊 Start vectorizing (file_md5: {test_file_md5})...")
        vectorize_service.vectorize(test_file_md5)
        
        # Verify call
        print("\n✅ Verify service call:")
        
        # 1. Verify embedding_client.embed is called
        assert mock_embedding_client.embed.called, "Embedding client should be called"
        print("  ✓ Gemini Embedding API called")
        
        # 2. Verify number of text chunks
        call_args = mock_embedding_client.embed.call_args[0][0]
        assert len(call_args) == expected_chunk_count, f"Should process {expected_chunk_count} text chunks"
        print(f"  ✓ Processed {len(call_args)} text chunks")
        
        # 3. Verify text content is not empty
        for i, text in enumerate(call_args[:3], 1):
            assert len(text) > 0, f"Text chunk {i} should not be empty"
            print(f"  ✓ Text chunk {i}: {len(text)} characters")
        
        # 4. Verify elasticsearch bulk_index is called
        assert mock_es_service.bulk_index.called, "Elasticsearch bulk_index should be called"
        print("  ✓ Elasticsearch bulk_index called")
        
        # 5. Verify documents passed to ES
        es_documents = mock_es_service.bulk_index.call_args[0][0]
        assert len(es_documents) == expected_chunk_count, f"Should have {expected_chunk_count} ES documents"
        print(f"  ✓ Prepared {len(es_documents)} Elasticsearch documents")
        
        # 6. Verify ES document structure
        first_doc = es_documents[0]
        print("\n📋 Verify Elasticsearch document structure:")
        assert hasattr(first_doc, 'id'), "Document should have id"
        print(f"  ✓ id: {first_doc.id}")
        
        assert first_doc.file_md5 == test_file_md5, "file_md5 should match"
        print(f"  ✓ file_md5: {first_doc.file_md5}")
        
        assert first_doc.chunk_id is not None, "Should have chunk_id"
        print(f"  ✓ chunk_id: {first_doc.chunk_id}")
        
        assert len(first_doc.text_content) > 0, "text_content should not be empty"
        print(f"  ✓ text_content: {len(first_doc.text_content)} characters")
        
        assert isinstance(first_doc.vector, list), "vector should be a list"
        assert len(first_doc.vector) == 768, "vector should be 768-dimensional"
        print(f"  ✓ vector: {len(first_doc.vector)} dimensional")
        
        assert first_doc.model_version == "gemini-embedding-001", "model_version should be correct"
        print(f"  ✓ model_version: {first_doc.model_version}")
        
        print(f"\n✅ Step 2 completed: Successfully vectorized {expected_chunk_count} text chunks")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ Vectorization failed: {e}")
        import traceback
        traceback.print_exc()
        db.close()
        return False


def test_step3_verify_data_flow():
    """Step 3: Verify complete data flow"""
    print("\n" + "=" * 60)
    print("Test 4: Verify complete data flow")
    print("=" * 60)
    
    if not TEST_FILE_MD5S:
        print("⚠️  Skip: No test data available")
        return False
    
    db = SessionLocal()
    
    try:
        test_file_md5 = TEST_FILE_MD5S[-1]
        
        # 1. Verify data in database
        print("📊 Verify data in database...")
        chunks = document_vector_repository.find_by_file_md5(db, test_file_md5)
        print(f"  ✓ Database has {len(chunks)} text chunks")
        
        # 2. Verify text chunk completeness
        print("\n📋 Verify text chunk completeness:")
        for i, chunk in enumerate(chunks[:3], 1):
            assert chunk.file_md5 == test_file_md5
            assert chunk.chunk_id is not None
            assert len(chunk.text_content) > 0
            print(f"  ✓ Chunk {i}: chunk_id={chunk.chunk_id}, content length={len(chunk.text_content)}")
        
        # 3. Verify data can be read by VectorizationService
        print("\n🔍 Verify data can be read by VectorizationService:")
        mock_embedding = Mock()
        mock_es = Mock()
        mock_embedding.embed.return_value = [[0.1] * 768 for _ in chunks]
        
        service = VectorizationService(
            embedding_client=mock_embedding,
            elasticsearch_service=mock_es,
            db=db
        )
        
        # Test _fetch_text_chunks method
        fetched_chunks = service._fetch_text_chunks(test_file_md5)
        assert len(fetched_chunks) == len(chunks)
        print(f"  ✓ _fetch_text_chunks successfully fetched {len(fetched_chunks)} chunks")
        
        # Verify converted TextChunk objects
        for i, text_chunk in enumerate(fetched_chunks[:3], 1):
            assert hasattr(text_chunk, 'chunk_id')
            assert hasattr(text_chunk, 'content')
            assert len(text_chunk.content) > 0
            print(f"  ✓ TextChunk {i}: chunk_id={text_chunk.chunk_id}")
        
        print("\n✅ Step 3 completed: Data flow verification successful")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ Data flow verification failed: {e}")
        import traceback
        traceback.print_exc()
        db.close()
        return False


def cleanup_test_data():
    """Clean up test data"""
    print("\n" + "=" * 60)
    print("Clean up test data")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        total_deleted = 0
        for test_file_md5 in TEST_FILE_MD5S:
            deleted = document_vector_repository.delete_by_file_md5(db, test_file_md5)
            total_deleted += deleted
            print(f"✓ Deleted {deleted} test data (MD5: {test_file_md5})")
        
        print(f"\n✅ Cleanup completed: Total deleted {total_deleted} test data")
        db.close()
        
    except Exception as e:
        print(f"⚠️  Cleanup failed: {e}")
        db.close()


def run_integration_tests():
    """Run complete integration tests"""
    print("=" * 60)
    print("🧪 VectorizationService integration tests")
    print("=" * 60)
    print("\nTest instructions:")
    print("1. Use ParseService to parse test document")
    print("2. Use VectorizationService to vectorize")
    print("3. Verify complete data flow")
    print("4. Clean up test data")
    print()
    
    try:
        # Setup
        if not setup_database():
            print("\n❌ Database setup failed, test aborted")
            return False
        
        # Test 1: Database connection
        if not test_database_connection():
            print("\n❌ Database connection failed, test aborted")
            return False
        
        # Test 2: Parse and save
        test_file_md5, chunk_count = test_step1_parse_and_save()
        if not test_file_md5:
            print("\n❌ Document parsing failed, test aborted")
            cleanup_test_data()
            return False
        
        # Test 3: Vectorize
        if not test_step2_vectorize_with_mock_services(test_file_md5, chunk_count):
            print("\n❌ Vectorization failed, test aborted")
            cleanup_test_data()
            return False
        
        # Test 4: Verify data flow
        if not test_step3_verify_data_flow():
            print("\n❌ Data flow verification failed")
            cleanup_test_data()
            return False
        
        # Cleanup
        cleanup_test_data()
        
        # Success
        print("\n" + "=" * 60)
        print("✅ All integration tests passed!")
        print("=" * 60)
        print("\n📊 Test summary:")
        print(f"  ✓ Parsed and saved {chunk_count} text chunks")
        print(f"  ✓ Successfully vectorized {chunk_count} text chunks")
        print(f"  ✓ Data flow verification passed")
        print(f"  ✓ Test data cleaned up")
        print("\n🎉 VectorizationService integration tests passed!")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Tests failed: {e}")
        import traceback
        traceback.print_exc()
        cleanup_test_data()
        return False


if __name__ == "__main__":
    import sys
    success = run_integration_tests()
    sys.exit(0 if success else 1)
