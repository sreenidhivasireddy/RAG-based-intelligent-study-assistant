#!/bin/bash

# Service Health Check Script
# Checks if all required services are running

echo "======================================"
echo "Service Health Check"
echo "======================================"
echo ""

ALL_OK=true

# Check MySQL
echo "Checking MySQL (port 3306)..."
if nc -z localhost 3306 2>/dev/null; then
    echo "✅ MySQL is running"
else
    echo "❌ MySQL is NOT running"
    echo "   Start: brew services start mysql"
    ALL_OK=false
fi

# Check Redis
echo ""
echo "Checking Redis (port 6379)..."
if nc -z localhost 6379 2>/dev/null; then
    echo "✅ Redis is running"
    # Try to ping
    if command -v redis-cli &> /dev/null; then
        if redis-cli ping &> /dev/null; then
            echo "   (ping successful)"
        fi
    fi
else
    echo "❌ Redis is NOT running"
    echo "   Start: brew services start redis"
    ALL_OK=false
fi

# Check MinIO
echo ""
echo "Checking MinIO (port 9000)..."
if nc -z localhost 9000 2>/dev/null; then
    echo "✅ MinIO is running"
    echo "   Web console: http://localhost:9001"
else
    echo "❌ MinIO is NOT running"
    echo "   Start: minio server /data --console-address ':9001'"
    ALL_OK=false
fi

# Check Elasticsearch (optional)
echo ""
echo "Checking Elasticsearch (port 9200) [Optional]..."
if nc -z localhost 9200 2>/dev/null; then
    echo "✅ Elasticsearch is running"
else
    echo "⚠️  Elasticsearch is NOT running (optional for now)"
    echo "   Start: cd elasticsearch-9.2.0 && ./bin/elasticsearch"
fi

echo ""
echo "======================================"
if [ "$ALL_OK" = true ]; then
    echo "✅ All required services are running!"
    echo "You can now start the backend server."
else
    echo "❌ Some required services are not running."
    echo "Please start them before running the server."
    exit 1
fi
echo "======================================"

