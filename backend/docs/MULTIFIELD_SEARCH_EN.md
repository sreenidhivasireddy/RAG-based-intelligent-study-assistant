# Multi-field Hybrid Search

This document describes the multi-field hybrid search implementation for the RAG-based Intelligent Study Assistant.

## Overview

The search system combines **KNN (vector)** and **BM25 (keyword)** search with multi-field text analysis to provide accurate results for both Chinese and English content.

## Architecture

```
                         User Query
                             │
                             ▼
┌────────────────────────────────────────────────────────────┐
│                    Query Processing                        │
│                                                            │
│  1. Generate embedding vector (Gemini API)                 │
│  2. Auto-adjust weights based on query features            │
└────────────────────┬───────────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────────┐
│                 Elasticsearch Query                        │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────────┐    ┌──────────────────┐             │
│  │   KNN Search     │    │  Multi-field     │             │
│  │   (Semantic)     │    │  BM25 Search     │             │
│  │                  │    │                  │             │
│  │  cosine(q, doc)  │    │  textContent     │             │
│  │                  │    │  textContent.en  │             │
│  │                  │    │  textContent.std │             │
│  └────────┬─────────┘    └────────┬─────────┘             │
│           │                       │                        │
│           └───────────┬───────────┘                        │
│                       │                                    │
│                       ▼                                    │
│           ┌───────────────────────┐                        │
│           │    RRF Fusion         │                        │
│           │                       │                        │
│           │ score = w1*knn +      │                        │
│           │         w2*bm25/(k+bm25)                       │
│           └───────────────────────┘                        │
│                                                            │
└────────────────────────────────────────────────────────────┘
                     │
                     ▼
               Ranked Results
```

## Multi-field Index Structure

### Field Configuration

| Field | Analyzer | Purpose |
|-------|----------|---------|
| `textContent` | IK (chinese_max/smart) | Chinese tokenization |
| `textContent.english` | english | English stemming |
| `textContent.standard` | standard | Fallback tokenization |
| `vector` | - | 768-dim dense vector |

### Index Mapping

```json
{
  "mappings": {
    "properties": {
      "textContent": {
        "type": "text",
        "analyzer": "chinese_max",
        "search_analyzer": "chinese_smart",
        "fields": {
          "english": {
            "type": "text",
            "analyzer": "english"
          },
          "standard": {
            "type": "text",
            "analyzer": "standard"
          }
        }
      },
      "vector": {
        "type": "dense_vector",
        "dims": 768,
        "similarity": "cosine"
      }
    }
  }
}
```

## Configuration

### Environment Variables (.env)

```bash
# Elasticsearch
ES_INDEX_NAME=knowledge_base

# Hybrid Search Weights (KNN vs BM25)
SEARCH_KNN_WEIGHT=0.5          # 0-1, higher = more semantic
SEARCH_BM25_WEIGHT=0.5         # 0-1, higher = more keyword
SEARCH_RRF_K=60                # RRF constant (1-200)

# Multi-field Boost (BM25 internal)
SEARCH_CHINESE_BOOST=1.0       # Chinese field importance
SEARCH_ENGLISH_BOOST=0.8       # English field importance
SEARCH_STANDARD_BOOST=0.5      # Standard field importance
SEARCH_TIE_BREAKER=0.3         # Non-best field contribution

# Features
SEARCH_MULTIFIELD_ENABLED=true
SEARCH_AUTO_ADJUST_WEIGHTS=true
SEARCH_HIGHLIGHT_ENABLED=true
```

## API Endpoints

### Search

```http
POST /api/v1/search/
Content-Type: application/json

{
  "query": "How to optimize PyTorch models?",
  "top_k": 10,
  "search_mode": "hybrid",
  "knn_weight": 0.5,
  "bm25_weight": 0.5,
  "auto_adjust": true,
  "use_multifield": true
}
```

### Response

```json
{
  "query": "How to optimize PyTorch models?",
  "total_results": 5,
  "results": [
    {
      "file_md5": "abc123",
      "chunk_id": 1,
      "text_content": "PyTorch optimization techniques...",
      "score": 1.284,
      "highlights": ["<mark>PyTorch</mark> <mark>optimization</mark>..."]
    }
  ],
  "search_mode": "hybrid",
  "metadata": {
    "knn_weight": 0.5,
    "bm25_weight": 0.5,
    "multifield_enabled": true
  }
}
```

### Index Management

```http
# Create index
POST /api/v1/search/index/create?use_ik=true

# Get index info
GET /api/v1/search/index/info

# Delete index
DELETE /api/v1/search/index/delete

# Recreate index
POST /api/v1/search/index/recreate?use_ik=true
```

### Analyzer Testing

```http
POST /api/v1/search/analyze
Content-Type: application/json

{
  "text": "PyTorch deep learning optimization",
  "analyzer": "chinese_smart"
}
```

## Auto Weight Adjustment

The system automatically adjusts KNN/BM25 weights based on query characteristics:

| Query Type | KNN Weight | BM25 Weight | Reason |
|------------|------------|-------------|--------|
| Technical terms (PyTorch, BERT, etc.) | 0.3 | 0.7 | Precise matching needed |
| Questions (How, What, Why) | 0.7 | 0.3 | Semantic understanding |
| Long queries (>50 chars) | 0.7 | 0.3 | Semantic understanding |
| Default | 0.5 | 0.5 | Balanced |

## IK Plugin Installation

The IK Analysis plugin is required for Chinese tokenization:

```bash
# Navigate to ES directory
cd elasticsearch-9.2.0

# Install IK plugin (match your ES version)
./bin/elasticsearch-plugin install \
  https://github.com/infinilabs/analysis-ik/releases/download/v9.2.0/elasticsearch-analysis-ik-9.2.0.zip

# Restart Elasticsearch
./bin/elasticsearch
```

## Testing

### Mock Tests (No dependencies)

```bash
cd backend
python tests/test_search_mock.py
```

### Integration Tests (Requires ES)

```bash
# Start Elasticsearch
./elasticsearch-9.2.0/bin/elasticsearch

# Run multi-field tests
python tests/test_multifield_search.py
```

## File Structure

```
backend/
├── app/
│   ├── api/
│   │   └── search.py           # API endpoints
│   ├── core/
│   │   ├── search_config.py    # Configuration management
│   │   └── es_index_config.py  # Index mapping
│   ├── services/
│   │   ├── search.py           # Search logic
│   │   └── elasticsearch_service.py  # ES operations
│   └── schemas/
│       └── search.py           # Request/Response models
├── tests/
│   ├── test_search_mock.py     # Mock tests
│   └── test_multifield_search.py  # Integration tests
└── docs/
    ├── MULTIFIELD_SEARCH_EN.md # This file
    └── MULTIFIELD_SEARCH_CN.md # Chinese version
```

## Troubleshooting

### IK Plugin Not Found

If IK plugin is not installed, the system falls back to standard analyzer:

```
⚠️ IK plugin not available, using standard analyzer
```

Solution: Install IK plugin as described above.

### Poor Chinese Search Results

1. Check if IK plugin is installed: `GET /api/v1/search/index/info`
2. Test analyzer: `POST /api/v1/search/analyze`
3. Recreate index: `POST /api/v1/search/index/recreate?use_ik=true`

### English Stemming Not Working

Ensure you're using the `textContent.english` field:

```json
{
  "match": {
    "textContent.english": "optimizing"
  }
}
```

This will match "optimize", "optimizer", "optimization", etc.

