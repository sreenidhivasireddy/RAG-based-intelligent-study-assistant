# Hybrid Search Implementation Guide

This document is the English version of the hybrid search design notes.

## Overview
The hybrid search pipeline combines vector search (KNN) and keyword search (BM25) in a single query flow. It uses weighted score fusion so semantic matches and exact term matches can both contribute to ranking.

## Core Characteristics
- Single-request search execution
- Weighted KNN + BM25 fusion
- Runtime-configurable search weights
- Automatic query-aware weight adjustment
- Highlight support for search results

## Configuration
Set these values in `.env`:

```bash
ES_INDEX_NAME=knowledge_base
SEARCH_KNN_WEIGHT=0.5
SEARCH_BM25_WEIGHT=0.5
SEARCH_RRF_K=60
SEARCH_DEFAULT_TOP_K=10
SEARCH_MAX_TOP_K=100
SEARCH_AUTO_ADJUST_WEIGHTS=true
SEARCH_HIGHLIGHT_ENABLED=true
```

## Weighting Guidance
- Balanced mode: `0.5 / 0.5`
- Technical term heavy queries: favor BM25
- Natural-language questions: favor KNN
- Academic or mixed queries: use a balanced profile with slight BM25 bias when terminology matters

## API Usage
- Use the standard search endpoint for hybrid retrieval.
- Use the compare endpoint to inspect retrieval behavior across search modes.

## Notes
- KNN is useful for semantic understanding.
- BM25 is useful for exact terminology.
- Score fusion is more robust than relying on either mode alone.
