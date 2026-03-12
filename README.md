# RAG-based Intelligent Study Assistant

An end-to-end study assistant built around Retrieval-Augmented Generation (RAG) for document-grounded chat, quiz generation, and automated evaluation.

## Overview

This project lets users upload study material such as PDFs, DOCX files, notes, and text documents, then:
- ingest and parse them asynchronously
- chunk and embed them
- index them for retrieval
- answer questions grounded in retrieved content
- generate MCQ quizzes from uploaded material
- run fixed and synthetic RAG evaluations with regression tracking

## Tech Stack

### Frontend
- React
- TypeScript
- Vite
- Tailwind CSS
- React Router
- Axios
- React Markdown
- Lucide React
- Recharts
- SparkMD5

### Backend
- Python
- FastAPI
- Uvicorn
- Pydantic
- SQLAlchemy
- python-dotenv

### Data / Messaging
- MySQL
- Redis
- Kafka

### Azure Services
- Azure OpenAI
- Azure AI Search
- Azure Blob Storage
- Azure AI Evaluation SDK

### Parsing / NLP / Utilities
- pypdf
- python-docx
- NLTK
- jieba
- NumPy
- psutil
- websockets
- aiohttp

### Local Infrastructure via Docker Compose
- Redis
- Kafka
- Zookeeper
- MinIO
- Elasticsearch

Note: Docker Compose in this repo is used for local infrastructure support. The frontend and backend applications themselves are not containerized here.

## Core Features

- Document upload with chunked/resumable flow
- Asynchronous ingestion using Kafka consumer pipeline
- PDF, DOCX, TXT, and note-style document support
- Hybrid retrieval using vector + keyword search
- Document-grounded conversational chat over WebSocket
- File-scoped knowledge base workflow
- MCQ quiz generation from uploaded material
- Automated evaluation with three modes:
  - synthetic
  - fixed
  - both
- Regression tracking for fixed and synthetic evaluation runs
- Evaluation UI with summaries, per-question scores, and graphs

## Architecture

### High-level flow
1. User uploads a file from the frontend
2. Backend stores metadata and merged file state
3. File is stored in Azure Blob Storage
4. Kafka task is published for background processing
5. Consumer downloads and parses the file
6. Parsed chunks are saved in MySQL
7. Embeddings are generated with Azure OpenAI
8. Chunks are indexed in Azure AI Search
9. User queries trigger hybrid retrieval
10. Retrieved chunks are passed into Azure OpenAI for grounded response generation
11. Synthetic QA generation and evaluation can run on processed documents

### Backend structure
- `backend/app/api/`
  - FastAPI routers
- `backend/app/services/`
  - business logic
- `backend/app/repositories/`
  - database access layer
- `backend/app/models/`
  - SQLAlchemy ORM models
- `backend/app/schemas/`
  - Pydantic schemas
- `backend/app/clients/`
  - Azure, Redis, Kafka, and external service clients
- `backend/app/consumer/`
  - Kafka background consumer

### Frontend structure
- `frontend/src/pages/`
  - Chat, Knowledge Base, Quiz, Evaluation pages
- `frontend/src/components/`
  - shared UI components and evaluation charts
- `frontend/src/api.ts`
  - API client layer
- `frontend/src/types.ts`
  - shared TypeScript types

## Retrieval Pipeline

### Retrieval method
Hybrid retrieval is used:
- semantic retrieval through embeddings
- lexical retrieval through keyword search

### Retrieval steps
1. User submits a question
2. Query embedding is generated using Azure OpenAI
3. Query type is inspected to adjust retrieval weighting
4. Azure AI Search runs hybrid retrieval
5. Top chunks are deduplicated and assembled into context
6. Azure OpenAI generates a grounded answer using retrieved chunks only

### Retrieval techniques used
- vector embeddings
- hybrid search
- weight auto-adjustment based on query style
- chunk deduplication
- source-aware prompting
- bounded context assembly

## File Ingestion and Processing

### Supported files
- PDF
- DOCX
- TXT
- Markdown-like text files

### Ingestion steps
1. Frontend splits file into chunks and computes MD5
2. Backend accepts chunk uploads
3. Upload progress is tracked
4. Chunks are merged into the final file
5. Kafka processing event is emitted
6. Consumer downloads file from storage
7. File is parsed and chunked
8. Chunks are stored in MySQL
9. Embeddings are created
10. Indexed records are written to Azure AI Search
11. File status is updated to completed

## Quiz System

The project includes a quiz workflow that:
- generates MCQ questions from uploaded material
- presents them in flashcard style
- checks selected answers
- reveals the correct answer and explanation after selection
- calculates final score
- shows an answer summary after completion

## Evaluation System

### Evaluation modes
- `synthetic`
  - QA pairs generated automatically from uploaded document chunks
- `fixed`
  - seeded static dataset for regression tracking
- `both`
  - runs synthetic and fixed together with separate summaries

### Evaluation metrics
- Groundedness
- Relevance
- Similarity
- Overall score

### Evaluation technology
- Azure AI Evaluation SDK
- Azure OpenAI as LLM judge configuration

### Evaluators used
- `GroundednessEvaluator`
- `RelevanceEvaluator`
- `SimilarityEvaluator`

### Regression tracking
- Separate histories for `fixed` and `synthetic`
- Stored evaluation runs with run labels such as `Run 1`, `Run 2`
- Frontend charts for trend tracking over time

## Local Development

### Prerequisites
- Python 3.10+
- Node.js 18+
- MySQL
- Azure service credentials configured in `backend/.env`

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r ..\requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Kafka consumer
```bash
cd backend
.venv\Scripts\activate
python -m app.consumer.run_consumer
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Optional local infra with Docker Compose
```bash
docker compose up -d
```

## Main Application Pages

- `Chat`
  - document-grounded question answering
- `Knowledge Base`
  - file upload and management
- `Quiz`
  - generated MCQ quiz experience
- `Evaluation`
  - synthetic/fixed RAG evaluation and regression tracking

## Key Project Strengths

- Full-stack RAG implementation, not just a chat wrapper
- Async ingestion pipeline with background processing
- Real document grounding using retrieval
- Quiz generation from uploaded study material
- Automated evaluation with visible regression tracking
- Clear service/repository separation in backend design

## Repository Structure

```text
.
+- frontend/
+- backend/
¦  +- app/
¦  +- data/
¦  +- docs/
¦  +- scripts/
¦  +- tests/
+- docker-compose.yml
+- README.md
+- requirements.txt
```

## License

MIT
