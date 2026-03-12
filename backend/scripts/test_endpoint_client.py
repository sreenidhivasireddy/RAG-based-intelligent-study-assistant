#!/usr/bin/env python3
"""Test if Azure Search client is properly initialized in the endpoint."""
import sys
sys.path.insert(0, '/data/RAG-based-intelligent-study-assistant/backend')

from app.clients.azure_search import get_azure_search_client
from app.clients.azure_openai_embedding_client import AzureOpenAIEmbeddingClient
from app.services.search import HybridSearchService

print("Testing client initialization...")

# Test 1: Get client
try:
    client = get_azure_search_client()
    print(f"✓ Azure Search client initialized: {type(client)}")
except Exception as e:
    print(f"✗ Failed to initialize client: {e}")
    sys.exit(1)

# Test 2: Get embedding client
try:
    embedding_client = AzureOpenAIEmbeddingClient()
    print(f"✓ Embedding client initialized: {type(embedding_client)}")
except Exception as e:
    print(f"✗ Failed to initialize embedding client: {e}")
    sys.exit(1)

# Test 3: Create search service
try:
    search_service = HybridSearchService(
        search_client=client,
        embedding_client=embedding_client
    )
    print(f"✓ HybridSearchService initialized: {type(search_service)}")
except Exception as e:
    print(f"✗ Failed to initialize search service: {e}")
    sys.exit(1)

# Test 4: Try a simple search
try:
    print("\nTesting hybrid_search('HCI')...")
    results, meta = search_service.hybrid_search(
        query='HCI',
        top_k=5
    )
    print(f"✓ Search executed: got {len(results)} results")
    for i, result in enumerate(results[:3]):
        print(f"  Result {i+1}: chunk_id={result.get('chunk_id')}, score={result.get('score')}")
except Exception as e:
    print(f"✗ Search failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✓ All tests passed!")
