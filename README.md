# RAG-based Intelligent Study Assistant

A full-stack RAG (Retrieval-Augmented Generation) application that enables intelligent document search and conversational Q&A using hybrid search techniques.

## Overview

This system allows users to upload documents (PDF, Word, TXT), which are then parsed, chunked, and indexed with vector embeddings. Users can ask natural language questions and receive answers grounded in their uploaded documents using a hybrid search approach that combines semantic (KNN) and keyword (BM25) search.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                             │
│              React + TypeScript + Vite                       │
│        (Chat UI, Document Upload, Management)                │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP/WebSocket
┌────────────────────────┴────────────────────────────────────┐
│                    Backend (FastAPI)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │  API Layer   │  │   Services   │  │   Kafka Topic   │   │
│  │   (REST)     │→ │ (Upload,     │→ │ (file-process)  │   │
│  │              │  │  Search)     │  │                 │   │
│  └──────────────┘  └──────────────┘  └────────┬────────┘   │
└──────────────────────────────────────────────┼─────────────┘
                         │                      │
         ┌───────────────┼──────────────────────┘
         │               │
         ▼               ▼
┌────────────────┐  ┌──────────────────────────────────────┐
│ Kafka Consumer │  │        Storage Layer                 │
│ (Async Worker) │  │  ┌────────┐ ┌────────┐ ┌──────────┐ │
│  - Parse docs  │  │  │ MinIO  │ │ Redis  │ │  MySQL   │ │
│  - Vectorize   │  │  │(Files) │ │(Cache) │ │(Metadata)│ │
│  - Index to ES │  │  └────────┘ └────────┘ └──────────┘ │
└────────┬───────┘  │  ┌──────────────────────────────┐   │
         │          │  │      Elasticsearch           │   │
         └──────────┼─→│  (Hybrid Search Index)       │   │
                    │  └──────────────────────────────┘   │
                    └──────────────────────────────────────┘
```

## Key Features

### 📄 Document Processing
- **Chunked Upload**: Large file support with resumable uploads
- **Multi-format Support**: PDF, Word (.docx), and plain text files
- **Async Processing**: Kafka-based message queue for background parsing and vectorization
- **Progress Tracking**: Real-time upload progress with Redis bitmaps

### 🔍 Hybrid Search
- **Dual Search Strategy**: Combines semantic (KNN vector) and keyword (BM25) search
- **Single Query Execution**: Efficient server-side fusion using Elasticsearch script_score
- **Auto Weight Adjustment**: Dynamically adjusts KNN/BM25 weights based on query characteristics
- **Multi-field Text Analysis**: Separate Chinese (IK) and English (stemming) analyzers
- **Phrase Matching**: Boosts exact phrase matches for technical terms
- **Smart Highlighting**: Filters stopwords and highlights meaningful terms

### 💬 Conversational Interface
- **WebSocket Chat**: Real-time streaming responses
- **Context-aware Q&A**: Retrieves relevant document chunks before generating answers
- **Conversation History**: Persistent chat sessions with message tracking
- **Source Attribution**: Shows which documents were used to answer questions

## Project Structure

```
.
├── backend/                      # FastAPI backend service
│   ├── app/
│   │   ├── api/                  # REST API endpoints
│   │   │   ├── upload.py         # File upload (chunked)
│   │   │   ├── documents.py      # Document management
│   │   │   ├── search.py         # Hybrid search API
│   │   │   ├── chat.py           # WebSocket chat
│   │   │   └── conversation.py   # Conversation management
│   │   ├── services/             # Business logic
│   │   │   ├── upload_service.py # Upload handling
│   │   │   ├── search.py         # Hybrid search implementation
│   │   │   ├── parse_service.py  # Document parsing
│   │   │   ├── vectorize_service.py  # Embedding generation
│   │   │   └── chat_handler.py   # Chat logic
│   │   ├── consumer/             # Kafka consumer
│   │   │   ├── file_processing_consumer.py
│   │   │   └── run_consumer.py   # Consumer entry point
│   │   ├── clients/              # External service clients
│   │   │   ├── minio.py          # MinIO object storage
│   │   │   ├── redis.py          # Redis cache
│   │   │   ├── elastic.py        # Elasticsearch
│   │   │   └── gemini_embedding_client.py  # Embedding API
│   │   ├── models/               # SQLAlchemy ORM models
│   │   ├── schemas/              # Pydantic schemas
│   │   └── core/                 # Configuration
│   ├── docs/                     # Technical documentation
│   │   ├── HYBRID_SEARCH_EN.md   # Hybrid search guide
│   │   └── MULTIFIELD_SEARCH_EN.md
│   └── tests/                    # Test suite
│
├── frontend/                     # React frontend
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Chat.tsx          # Chat interface
│   │   │   └── KnowledgeBase.tsx # Document management
│   │   ├── components/           # Reusable UI components
│   │   ├── api.ts                # Backend API client
│   │   └── types.ts              # TypeScript types
│   └── public/
│
└── README.md                     # This file
```

## Technology Stack

### Backend
- **Framework**: FastAPI, Uvicorn (ASGI)
- **Database**: MySQL (metadata), SQLAlchemy ORM
- **Cache**: Redis (upload progress, session management)
- **Object Storage**: MinIO (S3-compatible)
- **Search Engine**: Elasticsearch (hybrid search, vector storage)
- **Message Queue**: Kafka (async task processing)
- **Embedding**: Google Gemini API

### Frontend
- **Framework**: React 18 + TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS
- **HTTP Client**: Axios
- **WebSocket**: Native WebSocket API

## Quick Start

### Prerequisites
- Python 3.8+
- Node.js 18+
- MySQL 5.7+
- Redis 5.0+
- MinIO (latest)
- Elasticsearch 7.x/8.x
- Kafka 2.8+ (with Zookeeper or KRaft)

### 1. Clone Repository
```bash
git clone <repository-url>
cd RAG-based-intelligent-study-assistant
```

### 2. Setup Backend

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env with your configuration
```

### 3. Setup Frontend

```bash
cd frontend
npm install
```

### 4. Start Services

#### Start Infrastructure Services
```bash
# MySQL
# TODO: Add MySQL startup instructions

# Redis
# TODO: Add Redis startup instructions

# MinIO
# TODO: Add MinIO startup instructions

# Elasticsearch
# TODO: Add Elasticsearch startup instructions

# Kafka
# TODO: Add Kafka startup instructions
```

#### Start Backend Services
```bash
# Terminal 1: API Server
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2: Kafka Consumer (for document processing)
cd backend
python -m app.consumer.run_consumer
```

#### Start Frontend
```bash
# Terminal 3: Frontend Dev Server
cd frontend
npm run dev
```

Access the application at `http://localhost:5173`

## Configuration

### Backend Environment Variables
Key configurations in `backend/.env`:

```bash
# ==================== Server Configuration ====================
PORT=8000
DEBUG=True
LOG_LEVEL=INFO

# ==================== MySQL Configuration ====================
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=
MYSQL_PASSWORD=   
MYSQL_DATABASE=rag

# ==================== Redis Configuration ====================
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# ==================== MinIO Configuration ====================
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY= 
MINIO_SECRET_KEY=   
MINIO_BUCKET=documents
MINIO_SECURE=False

# ==================== Kafka Configuration ====================
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# ==================== Elasticsearch Configuration ====================
ES_HOST=localhost
ES_PORT=9200
ES_SCHEME=http
ES_INDEX_NAME=knowledge_base
# Security disabled for local testing
ES_USERNAME=elastic
ES_PASSWORD=      

# ==================== Gemini API Configuration ====================
GEMINI_API_KEY=   
GEMINI_MODEL_NAME=models/embedding-001
GEMINI_BATCH_SIZE=100

# ==================== Document Parsing Configuration ====================
CHUNK_SIZE=512
PARENT_CHUNK_SIZE=1048576
BUFFER_SIZE=8192
MAX_MEMORY_THRESHOLD=0.8

# ==================== Search Configuration ====================
# Hybrid Search Weights (KNN vs BM25)
SEARCH_KNN_WEIGHT=0.5
SEARCH_BM25_WEIGHT=0.5
SEARCH_RRF_K=60

# Multi-field Boost (BM25 internal)
SEARCH_CHINESE_BOOST=1.0
SEARCH_ENGLISH_BOOST=0.8
SEARCH_STANDARD_BOOST=0.5
SEARCH_TIE_BREAKER=0.3

# Search Result Limits
SEARCH_DEFAULT_TOP_K=10
SEARCH_MAX_TOP_K=100

# Search Mode: hybrid, knn, bm25
SEARCH_DEFAULT_MODE=hybrid

# Features
SEARCH_MULTIFIELD_ENABLED=true
SEARCH_AUTO_ADJUST_WEIGHTS=true
SEARCH_HIGHLIGHT_ENABLED=true
SEARCH_HIGHLIGHT_FRAGMENT_SIZE=150
SEARCH_HIGHLIGHT_FRAGMENTS=3

# ==================== OpenAI GPT Configuration ====================
OPENAI_API_KEY=     
GPT_MODEL=gpt-4o-mini
GPT_TEMPERATURE=0.7
GPT_TOP_P=0.95
GPT_MAX_TOKENS=2000



```

See `backend/ENV_CONFIG_GUIDE.md` for detailed configuration options.

## API Endpoints

### Document Management
- `POST /api/v1/upload/chunk` - Upload file chunk
- `POST /api/v1/upload/merge` - Merge chunks into complete file
- `GET /api/v1/upload/status` - Query upload progress
- `GET /api/v1/documents/list` - List all documents

### Search
- `POST /api/v1/search/hybrid` - Hybrid search (KNN + BM25)
- `POST /api/v1/search/knn` - Pure semantic search
- `POST /api/v1/search/bm25` - Pure keyword search

### Chat
- `WebSocket /api/v1/chat/ws/{conversation_id}` - Real-time chat
- `GET /api/v1/conversations` - List conversations
- `POST /api/v1/conversations/{id}/clear` - Clear conversation history

Interactive API documentation: `http://localhost:8000/docs`

## File Processing Lifecycle

1. **Upload** → User uploads file chunks via frontend
2. **Merge** → Backend merges chunks and stores in MinIO
3. **Queue** → Merge service sends message to Kafka topic
4. **Process** → Consumer picks up message and:
   - Downloads file from MinIO
   - Parses document (PDF/Word/TXT)
   - Chunks text into segments
   - Generates embeddings
   - Indexes to Elasticsearch
5. **Search** → Users can now search document content

See `backend/FILE_LIFECYCLE.md` for detailed workflow.

## Hybrid Search Strategy

The system uses a novel hybrid search approach:

1. **Query Analysis**: Automatically detects technical terms and question patterns
2. **Dual Retrieval**: 
   - Semantic search using embeddings (KNN)
   - Keyword search using BM25 with multi-field analysis
3. **Dynamic Weighting**: Adjusts KNN/BM25 weights based on query characteristics
4. **RRF Fusion**: Combines scores using Reciprocal Rank Fusion
5. **Smart Highlighting**: Emphasizes meaningful content words

See `backend/docs/HYBRID_SEARCH_EN.md` for technical details.

## Testing

### Backend Tests
```bash
cd backend
./run_tests.sh
```

Test coverage includes:
- Upload API (chunked, idempotent)
- Search API (hybrid, KNN, BM25)
- Kafka integration
- Service layer logic

### Frontend
```bash
cd frontend
npm run lint
```

## Documentation

- `backend/README.md` - Backend setup and API reference
- `backend/CONSUMER_README.md` - Kafka consumer guide
- `backend/FILE_LIFECYCLE.md` - Document processing workflow
- `backend/docs/HYBRID_SEARCH_EN.md` - Hybrid search implementation
- `backend/docs/MULTIFIELD_SEARCH_EN.md` - Multi-field text analysis
- `frontend/README.md` - Frontend setup and structure

## License

This project is licensed under the MIT License - see the LICENSE file for details.

---

**Happy Coding! 🚀**
