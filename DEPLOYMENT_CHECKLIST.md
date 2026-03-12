# Deployment Checklist

This checklist reflects the current Azure-based RAG study assistant, not the older file-content fallback implementation.

## 1. Required Services

Confirm these are available before deployment:

- MySQL
- Redis
- Kafka
- Azure Blob Storage
- Azure OpenAI
- Azure AI Search
- Azure AI Evaluation SDK access through existing Azure OpenAI configuration

Optional local-only support in this repo:

- Docker Compose for Redis, Kafka, Zookeeper, MinIO, and Elasticsearch

## 2. Environment Configuration

Verify `backend/.env` contains working values for:

- MySQL connection
- Redis connection
- Kafka bootstrap servers
- Azure OpenAI endpoint, key, API version, deployments
- Azure AI Search endpoint, key, index name
- Azure Blob Storage connection details
- optional evaluation tuning values such as batch size and sleep interval

## 3. Backend Readiness

Before release, verify:

- backend dependencies install cleanly
- FastAPI starts without import or schema errors
- SQLAlchemy models initialize correctly
- required tables exist
- Kafka consumer starts without broker errors

Commands:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r ..\requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a separate terminal:

```bash
cd backend
.venv\Scripts\activate
python -m app.consumer.run_consumer
```

## 4. Frontend Readiness

Verify:

- dependencies install
- Vite dev server builds cleanly
- Evaluation page loads
- Chat, Knowledge Base, Quiz, and Evaluation routes render

Commands:

```bash
cd frontend
npm install
npm run dev
```

## 5. Functional Verification

### Upload and ingestion

- Upload a PDF, DOCX, or TXT file
- Confirm upload completes
- Confirm file metadata appears in the Knowledge Base
- Confirm Kafka consumer processes the file
- Confirm chunks are indexed and searchable

### Chat

- Ask a document-grounded question
- Confirm response uses retrieved context
- Confirm source display behaves correctly in the UI

### Quiz

- Generate a quiz from uploaded material
- Confirm MCQ flow works end to end
- Confirm scoring and summary display correctly

### Evaluation

Run all three modes:

- `synthetic`
- `fixed`
- `both`

Verify:

- per-question results render
- summaries render correctly
- fixed and synthetic histories stay separated
- regression charts use `Run N` labels
- no raw local file paths or run IDs leak into the UI

## 6. Evaluation-Specific Checks

Verify:

- fixed dataset is seeded if fixed mode is required
- synthetic dataset rows can be generated from processed documents
- evaluation run history is stored
- Azure rate limiting is controlled by batch size and sleep settings

If `both` mode is slow or hits 429 responses:

- reduce evaluation batch size
- increase batch sleep interval
- consider a separate Azure deployment for judge traffic

## 7. Logging and Monitoring

Check:

- backend logs for ingestion, retrieval, evaluation, and consumer errors
- consumer logs for processing completion
- no repeated schema or import failures at startup
- no unhandled Azure quota failures during evaluation

Useful file:

- `backend/app/logs/app.log`

## 8. Security and Cleanup

Before final deployment:

- keep secrets only in environment variables
- ensure `.env` is not committed
- remove generated artifacts from source control if not needed
- remove local test files and stale evaluation output files if they are not part of the release

## 9. Release Acceptance Criteria

Deployment is ready only if all of the following are true:

- backend starts cleanly
- consumer starts cleanly
- frontend starts cleanly
- upload and ingestion complete successfully
- chat retrieval works on processed documents
- quiz generation works
- synthetic evaluation works when synthetic rows exist
- fixed evaluation works from seeded dataset
- both mode returns separated fixed and synthetic summaries
- regression history is stored and displayed by dataset type

