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
from app.clients.azure_openai_embedding_client import AzureOpenAIEmbeddingClient
from app.services.azure_search_service import AzureSearchService
import app.clients.azure_search as azure_search
from app.core.search_config import search_config
import app.clients.es_index_initializer as es_index_initializer

TEST_FILE_MD5 = None


# =============================================================
# Helper functions
# =============================================================

def setup_database():
    Base.metadata.create_all(bind=engine)


def setup_embedding():
    client = AzureOpenAIEmbeddingClient()
    if not client.is_configured():
        raise RuntimeError("Azure OpenAI embedding client not configured.")
    return client


def setup_es_service():
    """
    Setup Azure AI Search service for testing.
    """
    try:
        search_client = azure_search.get_azure_search_client()
    except RuntimeError as exc:
        raise RuntimeError(
            "Azure AI Search client not initialized. Ensure configuration is set"
            " in .env with AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_ADMIN_KEY,"
            " and AZURE_SEARCH_INDEX."
        ) from exc
    return AzureSearchService(search_client)


# =============================================================
# Step 1 — Parse document and save chunks to MySQL
# =============================================================

def step_parse_and_save():
    global TEST_FILE_MD5

    test_text = """
    Artificial Intelligence and Machine Learning. Artificial intelligence (AI) is an important branch of computer science. 
    It studies how machines can simulate human intelligence so computers can think and learn. Machine learning is one way to implement AI, allowing computers to learn patterns from data. 
    Deep learning is a subfield of machine learning that uses neural networks to process complex data. Natural language processing (NLP) is an important AI application area. It allows computers to understand, interpret, and generate human language. NLP applications include machine translation, sentiment analysis, and text summarization. Deep learning has significantly improved NLP performance. Computer vision enables machines to understand images and video. Applications include face recognition, object detection, and image classification. Convolutional neural networks (CNNs) are among the most common deep learning models in computer vision, and they can learn image features automatically through training.
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
        search_service=es_service
    )

    service.vectorize(TEST_FILE_MD5, db=db)

    print("✓ Vectorization completed")
    db.close()

    return es_service


# =============================================================
# Step 3 — Verify ES contains correct documents
# =============================================================

def step_verify_es(expected_chunks, es_service):
    # Use Azure Search client's search API to find documents by file id
    client = getattr(es_service, "search_client", None)
    if client is None:
        raise RuntimeError("AzureSearchService missing underlying search_client")

    filter_query = f"fileMd5 eq '{TEST_FILE_MD5}' or file_md5 eq '{TEST_FILE_MD5}'"
    results = list(client.search(search_text="*", filter=filter_query, top=expected_chunks))

    hits = []
    for r in results:
        try:
            # SearchResult behaves like dict-like object
            hits.append(dict(r))
        except Exception:
            hits.append(r)

    assert len(hits) == expected_chunks, f"Expected {expected_chunks} docs in Azure Search, found {len(hits)}"

    print(f"✓ Azure Search contains {len(hits)} documents")

    # Verify presence of expected fields (accept both snake_case and camelCase)
    doc = hits[0]
    assert any(k in doc for k in ("file_md5", "fileMd5")), "file_md5/fileMd5 not present"
    assert any(k in doc for k in ("chunk_id", "chunkId")), "chunk_id/chunkId not present"
    assert any(k in doc for k in ("text_content", "textContent")), "text_content/textContent not present"
    assert any(k in doc for k in ("model_version", "modelVersion")), "model_version/modelVersion not present"

    print("✓ Azure Search document structure validated")


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
