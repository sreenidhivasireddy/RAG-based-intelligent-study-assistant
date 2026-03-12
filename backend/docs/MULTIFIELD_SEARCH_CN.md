# Multi-Field Hybrid Search

This document is the English version of the multi-field search notes used by the RAG study assistant.

## Overview
The retrieval layer combines vector search and BM25 over multiple text fields so mixed Chinese/English content can still be indexed accurately.

## Retrieval Flow
1. Generate a query embedding.
2. Inspect the query and adjust KNN/BM25 weights.
3. Search across semantic vectors and multiple text fields.
4. Fuse the scores and return ranked chunks.

## Index Design
Suggested fields:
- `textContent`: primary text field
- `textContent.english`: English stemming field
- `textContent.standard`: fallback tokenizer field
- `vector`: embedding vector field

## Why multiple fields help
- Better handling of multilingual corpora
- Better exact matching for terminology
- Better fallback behavior when analyzers differ by language

## Practical Guidance
- Keep `top_k` moderate.
- Tune field boosts based on your corpus.
- Use compare/debug endpoints before changing production defaults.
