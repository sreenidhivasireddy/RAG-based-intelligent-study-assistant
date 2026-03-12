FILE READING INTEGRATION - ARCHITECTURE DIAGRAMS
═════════════════════════════════════════════════════════════════════════════════


SYSTEM ARCHITECTURE
═══════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (React)                                   │
│                      (Chat & Knowledge Base Pages)                           │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
            File Upload      Chat WebSocket    Status Check
                    │               │               │
                    ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          BACKEND (FastAPI)                                   │
│                                                                              │
│  ┌─ Upload API              ┌─ Chat API              ┌─ Documents API      │
│  │ · /upload/chunk          │ · /ws/{conv_id}        │ · /documents/status │
│  │ · /upload/merge          │                         │ · /documents/content│
│  └─────────────────────────┘                         │ · /documents/process│
│                    │                    │             └────────┬────────────│
│            Upload Handler         ChatHandler                  │            │
│                    │                    │                      │            │
│          ┌─────────▼─────────┐  ┌──────▼──────────┐   ┌───────▼────────┐   │
│          │   File Merging    │  │ Process Message │   │ FileContent    │   │
│          │ & Verification    │  │     Logic       │   │ Service        │   │
│          └────────┬──────────┘  └────────┬────────┘   └────────┬───────┘   │
│                   │                      │                     │            │
│                   ▼                      ▼                     ▼            │
│          ┌────────────────┐      ┌──────────────┐    ┌──────────────────┐ │
│          │  Kafka Topic   │      │Search Service│    │FileContentService│ │
│          │ (file-process) │      │  (Hybrid)    │    │  (Direct Read)   │ │
│          └────────┬───────┘      └──────┬───────┘    └────────┬─────────┘ │
│                   │                     │                     │            │
└───────────────────┼─────────────────────┼─────────────────────┼────────────┘
                    │                     │                     │
          ┌─────────▼─────────────────────▼─────────────────────▼──────┐
          │                   Unified Data Layer                       │
          │                                                           │
          │  ┌─────────────────────────────────────────────────┐     │
          │  │         Database (MySQL/PostgreSQL)            │     │
          │  │  · file_uploads (status, metadata)             │     │
          │  │  · document_vectors (parsed chunks)            │     │
          │  └─────────────────┬───────────────────────────────┘     │
          │                    │                                     │
          │  ┌─────────────────▼───────────────────────────────┐     │
          │  │    Storage (Azure Blob / MinIO)                 │     │
          │  │  · Uploaded files                              │     │
          │  │  · Parsed chunks                               │     │
          │  └─────────────────────────────────────────────────┘     │
          │                                                           │
          │  ┌─────────────────────────────────────────────────┐     │
          │  │   Search Index (Azure Search)                   │     │
          │  │  · Vectorized content                          │     │
          │  │  · Full-text indexed                           │     │
          │  └─────────────────────────────────────────────────┘     │
          └─────────────────────────────────────────────────────────┘


CHAT MESSAGE FLOW - WITH FALLBACK
═════════════════════════════════════

Normal Flow (Search Works):
───────────────────────────

  User: "What's in my file?"
         │
         ▼
  ChatHandler.process_message()
         │
         ├─ Get history from Redis
         │
         ├─ HybridSearchService.search(query)
         │
         ├─ Search Returns Results ✅
         │  └─ Build context from search results
         │  └─ Add to LLM prompt
         │
         ├─ Call LLM with context
         │
         └─ Stream response to user
            "Here's what I found... [file content]"


Fallback Flow (Search Fails):
─────────────────────────────

  User: "What's in my file?"
         │
         ▼
  ChatHandler.process_message()
         │
         ├─ Get history from Redis
         │
         ├─ HybridSearchService.search(query)
         │
         ├─ Search Returns NO Results ⚠️
         │  └─ Log: "Search returned no results"
         │
         ├─ _get_fallback_context() [NEW]
         │  │
         │  ├─ Query all completed files
         │  │
         │  ├─ For each file:
         │  │  └─ FileContentService.get_file_snippets()
         │  │     ├─ Check DocumentVector table
         │  │     │  └─ Return chunks if available
         │  │     └─ If empty, download & parse from storage
         │  │        └─ _download_and_parse_file()
         │  │
         │  └─ Combine all snippets into context
         │     └─ Return to process_message()
         │
         ├─ Context Now Available ✅
         │  └─ Log: "Fallback retrieval successful"
         │
         ├─ Call LLM with fallback context
         │
         └─ Stream response to user
            "Here's what I found in your file... [content]"


DATA FLOW - FILE CONTENT RETRIEVAL
═════════════════════════════════════

Path 1: Fast Path (Database)
────────────────────────────

  get_file_content_by_md5(file_md5)
         │
         ├─ Query DocumentVector table
         │  WHERE file_md5 = ?
         │
         ├─ Results Found ✅
         │  │
         │  └─ _combine_chunks()
         │     └─ Return: "Full file content"
         │
         └─ Time: <100ms


Path 2: Fallback Path (Storage)
────────────────────────────────

  get_file_content_by_md5(file_md5)
         │
         ├─ Query DocumentVector table
         │  WHERE file_md5 = ?
         │
         ├─ No Results ❌
         │  │
         │  ├─ Get file record (name, size)
         │  │
         │  ├─ _download_and_parse_file()
         │  │  │
         │  │  ├─ Construct path: "documents/{md5}/{name}"
         │  │  │
         │  │  ├─ Download from storage
         │  │  │  ├─ Azure Blob
         │  │  │  └─ OR MinIO
         │  │  │
         │  │  ├─ Get iterator based on file type
         │  │  │  ├─ PDF → PdfTextIterator
         │  │  │  ├─ DOCX → DocxTextIterator
         │  │  │  └─ TXT → PlainTextIterator
         │  │  │
         │  │  ├─ Extract text from file
         │  │  │
         │  │  └─ Return parsed content
         │  │
         │  └─ Return: "Full file content"
         │
         └─ Time: 500ms - 5s (depending on file size)


New API Endpoints Flow
══════════════════════

Status Check Endpoint:
─────────────────────

  GET /api/v1/documents/{file_md5}/status
         │
         ▼
  Query FileUpload table
         │
  ┌──────┴──────┐
  │             │
  ▼             ▼
Record Found   Not Found
  │             │
  ▼             ▼
Return:       Return:
{             {
  status: 0,   code: 404
  ...          error: "File not found"
}             }


Content Endpoint:
─────────────────

  GET /api/v1/documents/{file_md5}/content
         │
         ▼
  FileContentService.get_file_content_by_md5()
         │
  ┌──────┴──────┐
  │             │
  ▼             ▼
Success       Failure
  │             │
  ▼             ▼
Return:       Return:
{             {
  content:    code: 404
  "..."       error: "Could not retrieve"
}             }


Process Endpoint:
─────────────────

  POST /api/v1/documents/{file_md5}/process
         │
         ▼
  Query FileUpload table
         │
  ┌──────┴──────┐
  │             │
  ▼             ▼
status: 1     status: 2
(complete)    (merged)
  │             │
  ▼             ▼
Return:       Publish Kafka
{             Message
  error: "Already"   │
}             ▼
          Background
          Processing
          (in Kafka)


Component Interaction Diagram
══════════════════════════════

┌─────────────────────────────────────────────────────────────────────────┐
│                     ChatHandler (Core Chat Logic)                       │
│                                                                         │
│  process_message(user_message)                                         │
│  ├─ 1. Redis: Get conversation history                                │
│  ├─ 2. HybridSearchService: Search index                              │
│  │   │                                                                 │
│  │   ├─ Azure Search (KNN + BM25)                                     │
│  │   └─ Returns: search_results, metadata                             │
│  │                                                                     │
│  ├─ 3. FileContentService: Lookup file names [NEW]                    │
│  │   └─ Database: Get file_md5 → file_name mapping                    │
│  │                                                                     │
│  ├─ 4. Build context from results                                     │
│  │                                                                     │
│  ├─ 5. [NEW] Fallback check:                                          │
│  │   │                                                                 │
│  │   ├─ if no results or empty context:                              │
│  │   │  └─ _get_fallback_context()                                   │
│  │   │     ├─ FileContentService: Get all files [NEW]                │
│  │   │     ├─ For each file: Get snippets [NEW]                      │
│  │   │     └─ Combine into context                                    │
│  │   │                                                                 │
│  │   └─ else: Use original search context                             │
│  │                                                                     │
│  ├─ 6. GPTClient: Stream response with context                        │
│  │   └─ LLM generates answer based on context                         │
│  │                                                                     │
│  └─ 7. Save to Redis: Update history                                 │
└─────────────────────────────────────────────────────────────────────────┘
              │                      │                    │
              ▼                      ▼                    ▼
         ┌──────────┐         ┌──────────────┐    ┌──────────────────┐
         │   Redis  │         │   Database   │    │FileContentService│
         │ History  │         │  Lookup      │    │  - Get content   │
         │ Storage  │         │  Files       │    │  - Parse files   │
         └──────────┘         └──────────────┘    │  - Search chunks │
                                                  └──────────────────┘


Database Schema (Relevant Tables)
════════════════════════════════════

file_uploads:
┌────────────────┬──────────┐
│ file_md5 (PK)  │ string   │
│ file_name      │ string   │
│ total_size     │ int      │
│ status         │ int 0-2  │
│ created_at     │ datetime │
│ merged_at      │ datetime │
└────────────────┴──────────┘

document_vectors:
┌─────────────────┬──────────┐
│ vector_id (PK)  │ int      │
│ file_md5 (FK)   │ string   │  ← Used for lookups
│ chunk_id        │ int      │  ← Used for ordering
│ text_content    │ text     │  ← Actual content
│ model_version   │ string   │
└─────────────────┴──────────┘


Request/Response Flow Example
════════════════════════════════

User uploads: document.pdf
      │
      ▼
Frontend calculates MD5: abc123def456...
      │
      ▼
POST /api/v1/upload/chunk
        └─ chunk by chunk
      │
      ▼
All chunks received
      │
      ▼
POST /api/v1/upload/merge {file_md5: "abc123...", file_name: "document.pdf"}
      │
      ▼
Backend stores in FileUpload table (status=2)
      │
      ▼
Kafka message published to: file-processing-topic
      │
      ▼
Consumer picks up message
      │
      ├─ Downloads file from storage
      ├─ Parses into chunks
      ├─ Stores in DocumentVector table ← [DATA NOW AVAILABLE]
      ├─ Generates embeddings
      ├─ Indexes to Azure Search
      └─ Updates status=1 in FileUpload

User asks: "What's in my file?"
      │
      ▼
GET /ws/chat/{conversation_id} with message
      │
      ▼
ChatHandler.process_message()
      │
      ├─ Try search first
      │  └─ If fails: Use fallback
      │     └─ FileContentService queries:
      │        ├─ DocumentVector (chunks) ← [FOUND!]
      │        └─ Return to LLM
      │
      └─ LLM generates answer with file context
         │
         └─ Stream back to user


═════════════════════════════════════════════════════════════════════════════════
Last Updated: 2025-02-24
Architecture Version 1.0
═════════════════════════════════════════════════════════════════════════════════
