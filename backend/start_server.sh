#!/bin/bash

# Backend Server Startup Script
# IMPORTANT: Activate virtual environment before running this script!
# Run: source venv/bin/activate (from project root)

echo "======================================"
echo "RAG Backend - Starting Server"
echo "======================================"
echo ""

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  WARNING: Virtual environment not activated!"
    echo "Please activate it first (from project root):"
    echo "  source venv/bin/activate"
    echo "  cd backend"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check .env file (in project root)
if [ ! -f ../.env ]; then
    echo "⚠️  .env file not found in project root"
    echo "Please create and configure .env in the root directory:"
    echo "  cd .."
    echo "  cp .env.example .env"
    echo "  Then edit .env with correct configuration"
    exit 1
fi

# Check required services
echo "Checking required services..."
echo ""

# Check MySQL
if nc -z localhost 3306 2>/dev/null; then
    echo "✅ MySQL (port 3306)"
else
    echo "❌ MySQL not running (port 3306)"
    echo "   Start: brew services start mysql"
fi

# Check Redis
if nc -z localhost 6379 2>/dev/null; then
    echo "✅ Redis (port 6379)"
else
    echo "❌ Redis not running (port 6379)"
    echo "   Start: brew services start redis"
fi

# Check MinIO
if nc -z localhost 9000 2>/dev/null; then
    echo "✅ MinIO (port 9000)"
else
    echo "❌ MinIO not running (port 9000)"
    echo "   Start: minio server /data --console-address ':9001'"
fi

echo ""
echo "======================================"
echo "Starting FastAPI Server..."
echo "======================================"
echo ""
echo "Server URL: http://127.0.0.1:8000"
echo "API Docs: http://127.0.0.1:8000/docs"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
