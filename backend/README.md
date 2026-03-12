# Backend

Backend service for the RAG-based Intelligent Study Assistant.

## Stack

- Python
- FastAPI
- Uvicorn
- Pydantic
- SQLAlchemy
- MySQL
- Redis
- Kafka
- Azure OpenAI
- Azure AI Search
- Azure Blob Storage
- Azure AI Evaluation SDK

## What This Backend Does

- Accepts chunked file uploads from the frontend
- Tracks upload state and file metadata
- Publishes ingestion jobs to Kafka
- Runs background document parsing and chunking
- Generates embeddings and indexes chunks for retrieval
- Serves chat, quiz, and evaluation APIs
- Stores synthetic and fixed evaluation datasets
- Tracks regression history for evaluation runs

## Architecture

The backend follows a layered structure:

- `app/api/`
  - FastAPI routers and WebSocket endpoints
- `app/services/`
  - business logic
- `app/repositories/`
  - database access
- `app/models/`
  - SQLAlchemy models
- `app/schemas/`
  - Pydantic request and response schemas
- `app/clients/`
  - Azure, Kafka, Redis, and search clients
- `app/consumer/`
  - Kafka background consumer

## Main Flows

### Document ingestion

1. Frontend uploads file chunks
2. Backend merges the final file
3. File metadata is stored in MySQL
4. File is persisted to Azure Blob Storage
5. Kafka message is published for processing
6. Consumer parses the document into chunks
7. Chunks are stored in MySQL
8. Embeddings are generated with Azure OpenAI
9. Chunks are indexed in Azure AI Search
10. Synthetic QA generation can run after ingestion completes

### Retrieval and answer generation

1. User asks a question
2. Query embedding is generated
3. Hybrid retrieval runs against Azure AI Search
4. Top chunks are deduplicated and assembled
5. Azure OpenAI generates a grounded answer from retrieved context

### Evaluation

Supported modes:

- `synthetic`
- `fixed`
- `both`

Metrics used:

- groundedness
- relevance
- similarity
- overall

Evaluation uses Azure AI Evaluation SDK with Azure OpenAI as judge configuration.

## Local Setup

### Prerequisites

- Python 3.10+
- MySQL
- Azure credentials configured in `backend/.env`

Optional local infrastructure from repo root:

```bash
docker compose up -d
```

That Compose file is only for local support services such as Redis, Kafka, MinIO, and Elasticsearch. The backend app itself is run directly with Python.

### Install dependencies

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r ..\requirements.txt
```

### Start API server

```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Start Kafka consumer

```bash
cd backend
.venv\Scripts\activate
python -m app.consumer.run_consumer
```

## Useful Paths

- `app/main.py`
  - FastAPI app entrypoint
- `app/database.py`
  - DB engine and session setup
- `app/consumer/run_consumer.py`
  - Kafka consumer entrypoint
- `tests/`
  - backend tests
- `data/fixed_eval_dataset.json`
  - fixed evaluation dataset seed

## API Docs

When the backend is running:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

