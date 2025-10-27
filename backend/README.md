# RAG-based Intelligent Study Assistant - Backend

A backend service for an intelligent study assistant powered by RAG (Retrieval-Augmented Generation) technology, featuring chunked file uploads with resumable capabilities.

## 📋 Table of Contents

- [Features](#-features)
- [Tech Stack](#️-tech-stack)
- [Architecture](#️-architecture)
- [Quick Start](#-quick-start)
- [API Documentation](#-api-documentation)
- [Testing Guide](#-testing-guide)
- [Logging](#-logging)
- [License](#-license)

## ✨ Features

### File Upload Service
- ✅ **Chunked Upload**: Support for large files with chunk-based uploads to avoid timeouts
- ✅ **Resumable Upload**: Resume from breakpoints if upload fails
- ✅ **Progress Tracking**: Real-time upload progress monitoring
- ✅ **MD5 Verification**: Ensure file integrity with MD5 checksums
- ✅ **Idempotent Operations**: Safely handle duplicate chunk uploads
- ✅ **Unicode Support**: Full support for Chinese and other Unicode filenames

### Storage Systems
- ✅ **MinIO Object Storage**: Store file chunks in MinIO
- ✅ **Redis Cache**: Track upload progress using Redis Bitmaps
- ✅ **MySQL Database**: Manage metadata with SQLAlchemy ORM

### Logging System
- ✅ **Structured Logging**: Unified log format across the application
- ✅ **Log Rotation**: Automatic log file management (10MB max size)
- ✅ **Multiple Log Levels**: Support for DEBUG/INFO/WARNING/ERROR

## 🛠️ Tech Stack

### Core Framework
- **FastAPI** - Modern, fast web framework
- **Uvicorn** - ASGI server
- **Pydantic** - Data validation and serialization

### Data Storage
- **MySQL** - Relational database for metadata
- **Redis** - In-memory cache for progress tracking
- **MinIO** - Object storage for file chunks
- **Elasticsearch** - Search engine for vector retrieval (planned)
- **Kafka** - Message queue for async tasks (planned)

### ORM & Database Tools
- **SQLAlchemy** - Python ORM framework
- **mysql-connector-python** - MySQL driver

### Additional Tools
- **python-dotenv** - Environment variable management
- **requests** - HTTP client for testing

## 🏗️ Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ HTTP
       ▼
┌─────────────────────────────────────┐
│         FastAPI Application         │
│  ┌─────────────────────────────┐   │
│  │      API Layer (Routers)    │   │
│  └────────────┬────────────────┘   │
│               │                     │
│  ┌────────────▼────────────────┐   │
│  │     Service Layer           │   │
│  │  (Business Logic)           │   │
│  └────────────┬────────────────┘   │
│               │                     │
│  ┌────────────▼────────────────┐   │
│  │   Repository Layer          │   │
│  │  (Data Access)              │   │
│  └─────────────────────────────┘   │
└──────┬──────┬──────┬──────┬────────┘
       │      │      │      │
       ▼      ▼      ▼      ▼
    MySQL  Redis  MinIO  Elasticsearch
```

## 🚀 Quick Start

### Prerequisites

**Python Environment:**
- Python 3.8+

**Required Services (must be installed and running):**
- MySQL 5.7+
- Redis 5.0+
- MinIO (latest)

**Optional Services:**
- Elasticsearch 8.0+ (for search features)
- Kafka (for async tasks)

### 1. Create and Activate Virtual Environment

```bash
# Navigate to project root
cd RAG-based-intelligent-study-assistant

# Create virtual environment in project root (if not exists)
python3 -m venv venv

# Activate virtual environment (IMPORTANT - do this every time!)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**Important**: Always activate the virtual environment before running any commands!

**Note**: The `venv` folder will be created in your project root and is ignored by git.

### 2. Configure Environment

Create a `.env` file in the **project root directory** (not in backend/):

```bash
# MySQL Configuration
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=rag

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# MinIO Configuration
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=documents
MINIO_SECURE=False

# Elasticsearch Configuration (optional)
ES_HOST=localhost
ES_PORT=9200
ES_SCHEME=http

# Kafka Configuration (optional)
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
```

### 3. Install and Start Required Services

**Important**: These are separate server processes, not Python packages!

#### MySQL (Required)
```bash
# macOS (using Homebrew)
brew install mysql
brew services start mysql

# Create database
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS rag;"

# Verify: should show "rag" database
mysql -u root -p -e "SHOW DATABASES;"
```

#### Redis (Required)
```bash
# macOS (using Homebrew)
brew install redis
brew services start redis

# Verify: should return "PONG"
redis-cli ping
```

#### MinIO (Required)
```bash
# macOS (using Homebrew)
brew install minio/stable/minio

# Start MinIO (keep this terminal open)
minio server /data --console-address ":9001"

# Access web console: http://localhost:9001
# Default credentials: minioadmin / minioadmin
```

#### Elasticsearch (Optional - for search features)
```bash
# If you have elasticsearch-9.2.0/ in your project:
cd elasticsearch-9.2.0
./bin/elasticsearch

# Or install via Homebrew:
brew install elasticsearch
brew services start elasticsearch
```

**Quick Check**: Verify all services are running:
```bash
cd backend
chmod +x check_services.sh
./check_services.sh
```

This will show you which services are running and which need to be started.

### 4. Initialize Database

```bash
cd backend
python -c "from app.database import engine, Base; from app.models.file_upload import FileUpload; Base.metadata.create_all(bind=engine)"
```

### 5. Start the Server

**Step 1: Activate virtual environment**
```bash
# From project root
source venv/bin/activate
```

**Step 2: Start the server**

Option A - Using startup script (recommended):
```bash
cd backend
chmod +x start_server.sh
./start_server.sh
```

Option B - Manual start:
```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The server will start at:
- **API Documentation (Swagger UI)**: http://127.0.0.1:8000/docs
- **API Documentation (ReDoc)**: http://127.0.0.1:8000/redoc

## 📚 API Documentation

For complete interactive API documentation with live testing, visit **http://127.0.0.1:8000/docs** after starting the server.

### Quick Reference

**Base URL**: `http://localhost:8000/api/v1`

| Endpoint | Method | Description | Key Parameters |
|----------|--------|-------------|----------------|
| `/upload/chunk` | POST | Upload a file chunk | file, fileMd5, chunkIndex, fileName, totalSize |
| `/upload/status` | GET | Query upload progress | file_md5 |

### Response Format

All endpoints return a standardized JSON response:

```json
{
  "code": 200,           // Status code (200=success, 404=not found, 500=error)
  "message": "...",      // Status message
  "data": { ... }        // Response data (if applicable)
}
```

### Upload Flow

1. Split file into chunks on the client side
2. Calculate MD5 hash of the complete file
3. Upload each chunk via `POST /upload/chunk`
4. Track progress with `GET /upload/status` (optional)
5. System automatically tracks completed chunks for resumable uploads

## 🧪 Testing Guide

### Automated Testing (Recommended)

**Terminal 1** - Start the server:
```bash
# From project root, activate virtual environment
source venv/bin/activate

# Start server
cd backend
./start_server.sh
```

**Terminal 2** - Run all tests:
```bash
# From project root, activate virtual environment
source venv/bin/activate

# Run tests
cd backend
chmod +x run_tests.sh
./run_tests.sh
```

The test suite includes:
- ✅ Redis connection test
- ✅ MinIO connection test
- ✅ Schema validation test
- ✅ API functionality test (5 scenarios):
  - Query non-existent file (404)
  - Upload single chunk
  - Query upload status
  - Upload multiple chunks (3 chunks)
  - Idempotent upload (duplicate chunk handling)

### Interactive Testing (Swagger UI)

For manual testing with a visual interface:

1. Start the server: `./start_server.sh`
2. Open browser: **http://127.0.0.1:8000/docs**
3. Try any endpoint: Click "Try it out" → Fill parameters → Click "Execute"

### Troubleshooting

**Q: Why does the server seem "stuck" after starting?**  
A: This is normal! Web servers run continuously. Open a new terminal to run tests.

**Q: How do I stop the server?**  
A: Press `Ctrl+C` in the terminal running the server.

**Q: Port already in use?**  
A: Change the port in `start_server.sh` or run manually:
```bash
uvicorn app.main:app --port 8001 --reload
```

## 🔍 Logging

Application logs are saved in `app/logs/app.log` with log rotation:
- Maximum file size: 10MB
- Backup files kept: 5
- Log format: `timestamp - level - message`

View real-time logs:
```bash
tail -f app/logs/app.log
```

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](../LICENSE) file for details.

---

**Happy Coding! 🚀**
