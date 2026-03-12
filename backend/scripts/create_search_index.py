import os
from pathlib import Path
from dotenv import load_dotenv

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    VectorSearchProfile,
    HnswAlgorithmConfiguration,
)

# ✅ Ensure we load backend/.env (not root .env)
dotenv_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=dotenv_path)

endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
key = os.getenv("AZURE_SEARCH_ADMIN_KEY")
index_name = os.getenv("AZURE_SEARCH_INDEX", "rag-index")

if not endpoint or not key:
    raise RuntimeError(
        "Missing AZURE_SEARCH_ENDPOINT or AZURE_SEARCH_ADMIN_KEY.\n"
        f"Loaded .env from: {dotenv_path}\n"
        f"endpoint={endpoint}, key_present={bool(key)}"
    )

client = SearchIndexClient(endpoint=endpoint, credential=AzureKeyCredential(key))

EMBED_DIM = 1536  # matches your embedding output length

fields = [
    SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),

    # ✅ These must match what YOUR bulk_index uploads
    SimpleField(name="file_md5", type=SearchFieldDataType.String, filterable=True),
    SimpleField(name="file_name", type=SearchFieldDataType.String, filterable=True),
    SimpleField(name="chunk_id", type=SearchFieldDataType.String, filterable=True),
    SimpleField(name="chunk_index", type=SearchFieldDataType.Int32, filterable=True, sortable=True),

    SearchableField(
        name="content",
        type=SearchFieldDataType.String,
        analyzer_name="en.lucene",
        retrievable=True
    ),

    # ✅ Vector field (new schema uses vector_search_profile_name)
    SearchField(
        name="embedding",
        type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
        searchable=True,
        vector_search_dimensions=EMBED_DIM,
        vector_search_profile_name="vec-profile",
        retrievable=False,
    ),
]

vector_search = VectorSearch(
    profiles=[
        VectorSearchProfile(
            name="vec-profile",
            algorithm_configuration_name="hnsw-config",
        )
    ],
    algorithms=[
        HnswAlgorithmConfiguration(
            name="hnsw-config"
        )
    ],
)

index = SearchIndex(
    name=index_name,
    fields=fields,
    vector_search=vector_search
)

# Delete + recreate
try:
    client.delete_index(index_name)
    print(f"🗑️ Deleted existing index: {index_name}")
except Exception:
    pass

client.create_index(index)
print(f"✅ Created Azure AI Search index: {index_name}")
print(f"Endpoint: {endpoint}")