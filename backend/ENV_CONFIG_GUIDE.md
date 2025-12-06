# Environment Configuration Guide

## Quick Setup

1. **Copy the example configuration:**
```bash
# If .env doesn't exist, create it with the following content
```

2. **Add these lines to your `.env` file:**

```bash
# ============================================
# Elasticsearch Configuration
# ============================================
ES_HOST=localhost
ES_PORT=9200
ES_SCHEME=http
# ES_USERNAME=elastic
# ES_PASSWORD=your_password
ES_INDEX_NAME=knowledge_base

# ============================================
# Search Configuration (Hybrid Search)
# ============================================

# Weight Configuration for Hybrid Search
# KNN (Vector Search) Weight: 0.0 - 1.0
SEARCH_KNN_WEIGHT=0.5

# BM25 (Keyword Search) Weight: 0.0 - 1.0
SEARCH_BM25_WEIGHT=0.5

# RRF (Reciprocal Rank Fusion) Constant
# Higher value = less emphasis on ranking differences
SEARCH_RRF_K=60

# Result Limits
SEARCH_DEFAULT_TOP_K=10
SEARCH_MAX_TOP_K=100

# Search Mode (hybrid/knn/bm25)
SEARCH_DEFAULT_MODE=hybrid

# Auto-adjust weights based on query features
# true: Automatically adjust weights for technical terms or questions
# false: Always use configured weights
SEARCH_AUTO_ADJUST_WEIGHTS=true

# Highlight Configuration
SEARCH_HIGHLIGHT_ENABLED=true
SEARCH_HIGHLIGHT_FRAGMENT_SIZE=150
SEARCH_HIGHLIGHT_FRAGMENTS=3
```

3. **Restart the server** to load the new configuration:
```bash
cd backend
./start_server.sh
```

## Configuration Parameters Explained

### Weight Configuration

- **SEARCH_KNN_WEIGHT**: Weight for vector similarity search (0.0 to 1.0)
  - Higher value = More emphasis on semantic understanding
  - Example: 0.7 for question-based queries

- **SEARCH_BM25_WEIGHT**: Weight for keyword matching (0.0 to 1.0)
  - Higher value = More emphasis on exact term matching
  - Example: 0.7 for technical documentation

- **SEARCH_RRF_K**: RRF normalization constant (typically 30-100)
  - Higher value = Less emphasis on ranking differences
  - Default: 60 (balanced)

### Recommended Presets

```bash
# Balanced Mode (Default)
SEARCH_KNN_WEIGHT=0.5
SEARCH_BM25_WEIGHT=0.5

# Professional Mode (Technical Terms)
SEARCH_KNN_WEIGHT=0.3
SEARCH_BM25_WEIGHT=0.7

# Semantic Mode (Questions & Concepts)
SEARCH_KNN_WEIGHT=0.7
SEARCH_BM25_WEIGHT=0.3

# Academic Mode (Research Papers)
SEARCH_KNN_WEIGHT=0.4
SEARCH_BM25_WEIGHT=0.6

# Code Mode (Code Snippets)
SEARCH_KNN_WEIGHT=0.2
SEARCH_BM25_WEIGHT=0.8
```

## Verification

After configuration, verify it's working:

```bash
# Check configuration
curl http://localhost:8000/api/v1/search/config

# Test search
curl -X POST http://localhost:8000/api/v1/search/ \
  -H "Content-Type: application/json" \
  -d '{"query": "test query", "top_k": 3}'
```

