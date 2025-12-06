"""
Integration test for VectorizationService with real MySQL + Elasticsearch.

Flow:
1. Parse test document → save chunks in MySQL
2. Vectorize → embedding + bulk index to ES
3. Verify ES contains expected documents
4. Cleanup MySQL test data

Prerequisites:
- MySQL running
- Elasticsearch running
- .env configured correctly
"""

import io
import os
import hashlib
from pathlib import Path
import sys
from sqlalchemy import text

# Add backend to PYTHONPATH
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.database import SessionLocal, engine, Base
from app.services.parse_service import ParseService
from app.services.vectorize_service import VectorizationService
from app.repositories import document_vector_repository
from app.clients.gemini_embedding_client import GeminiEmbeddingClient
from app.services.es_service import ElasticsearchService
import app.clients.elastic as es
from app.clients.elastic import ES_INDEX
import app.clients.es_index_initializer as es_index_initializer

TEST_FILE_MD5 = None


# =============================================================
# Helper functions
# =============================================================

def setup_database():
    Base.metadata.create_all(bind=engine)


def setup_embedding():
    if not GeminiEmbeddingClient.is_configured():
        raise RuntimeError("GEMINI_API_KEY missing.")
    return GeminiEmbeddingClient()


def setup_es_service():
    """
    Reuse the runtime ES client so tests mirror production behavior.
    """
    try:
        client = es.get_client()
    except RuntimeError as exc:
        raise RuntimeError(
            "Elasticsearch client not initialized. Ensure ES is running and .env"
            " contains the correct connection info."
        ) from exc
    return ElasticsearchService(client)


# =============================================================
# Step 1 — Parse document and save chunks to MySQL
# =============================================================

def step_parse_and_save():
    global TEST_FILE_MD5

    test_text = """
    人工智能与机器学习 人工智能（Artificial Intelligence，AI）是计算机科学的一个重要分支。 
    它研究如何让机器模拟人类智能，使计算机能够像人一样思考和学习。 机器学习是实现人工智能的一种方法。通过机器学习，计算机可以从数据中自动学习规律。 
    深度学习是机器学习的一个子领域，它使用神经网络来处理复杂的数据。 自然语言处理 自然语言处理（NLP）是人工智能的重要应用领域之一。 它让计算机能够理解、解释和生成人类语言。 NLP 的应用包括机器翻译、情感分析、文本摘要等。 通过深度学习技术，NLP 的性能得到了显著提升。 计算机视觉 计算机视觉让机器能够"看"和理解图像与视频。 它的应用包括人脸识别、物体检测、图像分类等。 卷积神经网络（CNN）是计算机视觉中最常用的深度学习模型。 通过训练，CNN 可以自动学习图像的特征。
    """

    TEST_FILE_MD5 = hashlib.md5(test_text.encode()).hexdigest()
    print(f"📄 Test MD5 = {TEST_FILE_MD5}")

    db = SessionLocal()

    # Cleanup old test data
    document_vector_repository.delete_by_file_md5(db, TEST_FILE_MD5)

    # Parse
    parser = ParseService(chunk_size=200)
    file_stream = io.BytesIO(test_text.encode())

    parser.parse_and_save(
        file_md5=TEST_FILE_MD5,
        file_name="test_ai.txt",
        file_stream=file_stream,
        db=db
    )

    chunks = document_vector_repository.find_by_file_md5(db, TEST_FILE_MD5)
    db.close()

    assert len(chunks) > 0, "No text chunks saved"
    print(f"✓ Saved {len(chunks)} chunks to MySQL")
    return len(chunks)


# =============================================================
# Step 2 — Vectorize chunks and index to ES
# =============================================================

def step_vectorize(expected_chunk_count):
    embedding = setup_embedding()
    es_service = setup_es_service()
    db = SessionLocal()

    service = VectorizationService(
        embedding_client=embedding,
        elasticsearch_service=es_service
    )

    service.vectorize(TEST_FILE_MD5, db=db)

    print("✓ Vectorization completed")
    db.close()

    return es_service


# =============================================================
# Step 3 — Verify ES contains correct documents
# =============================================================

def step_verify_es(expected_chunks, es_service):
    es_client = es_service.es

    resp = es_client.search(
        index=ES_INDEX,
        query={"term": {"file_md5": {"value": TEST_FILE_MD5}}},
        size=expected_chunks
    )

    hits = [h["_source"] for h in resp["hits"]["hits"]]

    assert len(hits) == expected_chunks, \
        f"Expected {expected_chunks} docs in ES, found {len(hits)}"

    print(f"✓ Elasticsearch contains {len(hits)} documents")

    # Verify structure of the first doc
    doc = hits[0]
    assert "file_md5" in doc
    assert "chunk_id" in doc
    assert "text_content" in doc
    assert "model_version" in doc

    print("✓ ES document structure validated")


# =============================================================
# Step 4 — Cleanup MySQL test data
# =============================================================

def cleanup():
    db = SessionLocal()
    deleted = document_vector_repository.delete_by_file_md5(db, TEST_FILE_MD5)
    print(f"✓ Cleaned {deleted} rows from MySQL")
    db.close()


# =============================================================
# Run All Steps
# =============================================================

def run_all():
    print("====================================")
    print("🔬 Vectorization Integration Test")
    print("====================================")

    setup_database()
    es_index_initializer.ensure_index()

    # 1. Parse & save
    chunk_count = step_parse_and_save()

    # 2. Vectorize
    es_service = step_vectorize(chunk_count)

    # 3. Verify ES
    step_verify_es(chunk_count, es_service)

    # 4. Cleanup
    cleanup()

    print("\n🎉 All integration tests passed!")


if __name__ == "__main__":
    run_all()
