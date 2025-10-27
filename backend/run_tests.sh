#!/bin/bash

# Test Suite Runner
# Run all tests automatically
# IMPORTANT: Activate virtual environment before running this script!
# Run: source venv/bin/activate (from project root)

echo "======================================"
echo "RAG Backend - Test Suite"
echo "======================================"
echo ""

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  WARNING: Virtual environment not activated!"
    echo "Please activate it first (from project root):"
    echo "  source venv/bin/activate"
    echo "  cd backend"
    echo ""
    echo "Exiting..."
    exit 1
fi

echo "✅ Using virtual environment: $VIRTUAL_ENV"
echo ""

# Check if server is running
echo "Checking server status..."
if lsof -ti:8000 > /dev/null 2>&1; then
    echo "✅ Server is running (port 8000)"
    SERVER_RUNNING=true
else
    echo "⚠️  Server is not running"
    echo "Please start the server first:"
    echo "  uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
    SERVER_RUNNING=false
fi

echo ""
echo "======================================"
echo "1. Client Connection Tests"
echo "======================================"

echo ""
echo "Testing Redis connection..."
python3 tests/test_redis.py
if [ $? -eq 0 ]; then
    echo "✅ Redis test passed"
else
    echo "❌ Redis test failed"
fi

echo ""
echo "Testing MinIO connection..."
python3 tests/test_minio.py
if [ $? -eq 0 ]; then
    echo "✅ MinIO test passed"
else
    echo "❌ MinIO test failed"
fi

echo ""
echo "======================================"
echo "2. Schema Validation Tests"
echo "======================================"
echo ""
PYTHONPATH=. python3 tests/test_upload_schemas.py
if [ $? -eq 0 ]; then
    echo "✅ Schema tests passed"
else
    echo "❌ Schema tests failed"
fi

if [ "$SERVER_RUNNING" = true ]; then
    echo ""
    echo "======================================"
    echo "3. API Functionality Tests"
    echo "======================================"
    echo ""
    
    echo "Running comprehensive API tests..."
    PYTHONPATH=. python3 tests/test_upload_api_simple.py
    if [ $? -eq 0 ]; then
        echo "✅ API tests passed"
    else
        echo "❌ API tests failed"
    fi
else
    echo ""
    echo "======================================"
    echo "Skipping API tests (server not running)"
    echo "======================================"
fi

echo ""
echo "======================================"
echo "All tests completed!"
echo "======================================"
