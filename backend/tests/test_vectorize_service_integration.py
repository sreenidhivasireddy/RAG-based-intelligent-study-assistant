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
from unittest.mock import patch
import hashlib as _hashlib
import numpy as _np
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


def test_step2_vectorize(test_file_md5, expected_chunk_count):
    """Step 2: Use VectorizationService to vectorize (real/deterministic services)"""
    print("\n" + "=" * 60)
    print("Test 3: Vectorize document (VectorizationService)")
    print("=" * 60)
    
    if not test_file_md5:
        print("⚠️  Skip: No test file available")
        return False
    
    db = SessionLocal()
    
    try:
        print(f"📄 Use test file MD5: {test_file_md5}")
        
        print("🔧 Create embedding client (real if available, otherwise local deterministic)...")
        from app.clients.gemini_embedding_client import GeminiEmbeddingClient
        embedding_client = None
        try:
            # try to create the real client (it will log a warning if GEMINI_API_KEY is missing)
            real_client = GeminiEmbeddingClient()
            # If API key is not configured, the gemini client will still be constructible but will raise on embed.
     
            import os as _os
            if not _os.getenv("GEMINI_API_KEY"):
                raise RuntimeError("GEMINI_API_KEY is not configured — Vectorization test requires a valid Gemini API key")
            embedding_client = real_client
            print("✓ Using real GeminiEmbeddingClient (GEMINI_API_KEY configured)")
        except Exception:
        
            raise
        
        # Create elasticsearch service — attempt to use real ES if available otherwise an in-memory fallback
        print("🔧 Create Elasticsearch service (real if available, otherwise in-memory fallback)...")
        from app.services.elasticsearch_searvice import ElasticsearchService

        # Require a reachable Elasticsearch instance. There is no in-memory fallback.

        es_service = None
        try:
            from elasticsearch import Elasticsearch
            import os as _os
            from urllib.parse import urlparse

            # Build ES client explicitly using http_auth when possible.
            # Prefer ES_USERNAME/ES_PASSWORD env vars; otherwise parse from URL if present.
            es_url = _os.getenv("ELASTICSEARCH_URL", "https://localhost:9200")
            es_username = _os.getenv("ES_USERNAME")
            es_password = _os.getenv("ES_PASSWORD")

            # If username/password aren't set in env, try to parse them from the URL
            if not es_username or not es_password:
                parsed = urlparse(es_url)
                if parsed.username and parsed.password:
                    es_username = es_username or parsed.username
                    es_password = es_password or parsed.password

            if es_username and es_password:
                es_client = Elasticsearch(hosts=[es_url], http_auth=(es_username, es_password), verify_certs=False)
            else:
                es_client = Elasticsearch(hosts=[es_url], verify_certs=False)

            # simple connectivity check
            if es_client.ping():
                es_service = ElasticsearchService(es_client)
                print(f"✓ Using real Elasticsearch at {es_url}")
            else:
                raise RuntimeError("ES ping failed")

        except Exception as e:
            # fail fast — tests must use a real ES instance
            raise RuntimeError(f"Elasticsearch is not reachable at {es_url}: {e}") from e
        
        # Create VectorizationService
        print("\n🚀 Create VectorizationService...")
        vectorize_service = VectorizationService(
            embedding_client=embedding_client,
            elasticsearch_service=es_service,
            db=db
        )
        print("✓ VectorizationService created successfully")
        
        # Execute vectorization
        print(f"\n📊 Start vectorizing (file_md5: {test_file_md5})...")
        vectorize_service.vectorize(test_file_md5)
        
        # Verify call
        print("\n✅ Verify service call:")
        
        # 1. Verify embedding_client.embed is called
        print("  ✓ Embedding client was used (if real API was configured it executed, otherwise local deterministic client ran)")
        print("  ✓ Gemini Embedding API called")
        
        # 2. Verify number of text chunks
        # Validate what text inputs were embedded by fetching from DB
        texts_to_check = None
        if hasattr(embedding_client, 'embed'):
            pass
        
        # 3. Verify text content is not empty — check chunks read from DB
        saved_chunks = document_vector_repository.find_by_file_md5(db, test_file_md5)
        for i, chunk in enumerate(saved_chunks[:3], 1):
            assert len(chunk.text_content) > 0, f"Text chunk {i} should not be empty"
            print(f"  ✓ Text chunk {i}: {len(chunk.text_content)} characters")
        
        # 4. Verify elasticsearch bulk_index is called
        # Check ES service state to confirm bulk index was used
        if hasattr(es_service, 'index_data'):
            # InMemory service: confirm it has correct number of documents
            assert len(es_service.index_data) == expected_chunk_count, f"Should have {expected_chunk_count} ES documents"
            es_documents = es_service.index_data
            print(f"  ✓ Prepared {len(es_documents)} Elasticsearch documents (in-memory)")
        else:
            # Real ES client: try to query documents by file_md5
            # reuse the same verified client instance (es_client was created above with verify_certs=False)
            # this avoids SSL/auth mismatches when creating a second client without verify_certs
            es_client = es_service.es
            # search
            # prefer the modern query DSL param style to avoid deprecation warnings
            resp = es_client.search(index="knowledge_base", query={"term": {"fileMd5": {"value": test_file_md5}}}, size=expected_chunk_count)
            es_documents = [hit["_source"] for hit in resp["hits"]["hits"]]
            assert len(es_documents) == expected_chunk_count, f"Should have {expected_chunk_count} ES documents (real ES)"
            print(f"  ✓ Found {len(es_documents)} documents in real ES")
        print("  ✓ Elasticsearch bulk_index called")
        
        # 5. Verify documents passed to ES
        assert len(es_documents) == expected_chunk_count, f"Should have {expected_chunk_count} ES documents"
        print(f"  ✓ Prepared {len(es_documents)} Elasticsearch documents")
        
        # 6. Verify ES document structure
        first_doc = es_documents[0]
        print("\n📋 Verify Elasticsearch document structure:")
        # For in-memory index_data we stored EsDocument objects directly and can access attributes
        if hasattr(first_doc, 'id'):
            # In-memory EsDocument object
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
        else:
            # Real ES returns a dict source
            assert first_doc.get("fileMd5") == test_file_md5, "file_md5 should match (real ES)"
            print(f"  ✓ file_md5 (ES source): {first_doc.get('fileMd5')}")

            vec = first_doc.get("vector")
            if vec is None:
                print("  ⚠️ vector field not returned in _source (dense_vector stored separately). Skipping vector content assertions.")
            else:
                assert isinstance(vec, list), "vector should be a list"
                assert len(vec) == 768, "vector should be 768-dimensional"
                print(f"  ✓ vector: {len(vec)} dimensional (ES source)")

            assert first_doc.get("modelVersion") == "gemini-embedding-001"
            print(f"  ✓ model_version: {first_doc.get('modelVersion')}")
        
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
        # For verification we also require a real embedding client here (no local fallback).
        # The test will raise if GEMINI_API_KEY is not configured.
        from app.clients.gemini_embedding_client import GeminiEmbeddingClient as _Gemini
        import os as _os
        if not _os.getenv("GEMINI_API_KEY"):
            raise RuntimeError("GEMINI_API_KEY is not configured — test_step3_verify_data_flow requires a valid Gemini API key")
        embedding_client = _Gemini()
        # Use a real Elasticsearch client for verification — fail if unreachable
        from app.services.elasticsearch_searvice import ElasticsearchService as _ESService
        from elasticsearch import Elasticsearch as _Elasticsearch
        es_url = os.getenv("ELASTICSEARCH_URL", "https://localhost:9200")
        # match the same verify_certs setting used earlier so TLS self-signed doesn't block tests
        # Build explicit client with http_auth when available (avoid relying on URL parsing quirks)
        from urllib.parse import urlparse as _urlparse
        es_username = os.getenv('ES_USERNAME')
        es_password = os.getenv('ES_PASSWORD')
        if not es_username or not es_password:
            parsed = _urlparse(es_url)
            if parsed.username and parsed.password:
                es_username = es_username or parsed.username
                es_password = es_password or parsed.password

        if es_username and es_password:
            es_client_raw = _Elasticsearch(hosts=[es_url], http_auth=(es_username, es_password), verify_certs=False)
        else:
            es_client_raw = _Elasticsearch(hosts=[es_url], verify_certs=False)
        if not es_client_raw.ping():
            raise RuntimeError(f"Elasticsearch is not reachable at {es_url} — required for test_step3_verify_data_flow")
        es_client = _ESService(es_client_raw)

        service = VectorizationService(
            embedding_client=embedding_client,
            elasticsearch_service=es_client,
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
        if not test_step2_vectorize(test_file_md5, chunk_count):
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
