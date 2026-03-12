# Kafka Consumer Guide

## Current Architecture

```text
1. User uploads a file
2. API receives the file and uploads chunks to storage
3. API merges the file and generates a signed URL
4. API creates a FileProcessingTask and publishes it to Kafka
5. Kafka stores the message in the queue
6. Consumer listens for and pulls the message
7. Consumer downloads the file, parses it, vectorizes it, and stores it in search
8. Users can search the file content
```

## Why the Consumer Must Run Separately

### Kafka queue model
- **Producer**: API code that only sends tasks to Kafka.
  - File: `backend/app/api/upload.py`
  - Role: returns immediately after publishing the message.
- **Kafka**: stores messages until a consumer processes them.
- **Consumer**: a separate long-running process that listens to Kafka.
  - File: `backend/app/consumer/file_processing_consumer.py`
  - Role: downloads, parses, and vectorizes uploaded files.

### Why it is not started automatically
1. **Decoupled design**: API response time stays fast while background processing runs elsewhere.
2. **Independent scaling**: you can run multiple consumers for higher throughput.
3. **Fault isolation**: consumer failures do not bring down the API.
4. **Flexible deployment**: API and consumer can run on different machines.

## Start the Consumer

### Option 1: startup script
```bash
./start_consumer.sh
```

### Option 2: run the Python module directly
```bash
cd backend
python -m app.consumer.run_consumer
```

### Option 3: background process
Run the same command with your process manager of choice.

## Development Workflow

### 1. Start all services
Open four terminals:

**Terminal 1 - Kafka**
```bash
# start Kafka if you use Docker or local services
```

**Terminal 2 - FastAPI**
```bash
./start_server.sh
```

**Terminal 3 - Kafka Consumer**
```bash
./start_consumer.sh
```

**Terminal 4 - Testing / debugging**
```bash
# run tests or manual API calls
```

### 2. Verify the Consumer is running
A healthy startup should include messages like:
```text
Starting File Processing Kafka Consumer
All services initialized successfully
Consumer is now listening for messages...
```

### 3. Upload a file
1. Upload file chunks.
2. Merge the file.
3. Check the consumer terminal for parse and vectorization logs.

## FAQ

### Q1: Why is my uploaded file not being processed?
**A**: The consumer is probably not running. Make sure:
1. The consumer process is active.
2. The consumer log says it is listening for messages.
3. Kafka is running normally.

### Q2: Why do tests pass even if I forgot to start the consumer manually?
**A**: Some test flows start the consumer explicitly inside the test code.

### Q3: Can the API and consumer run in the same process?
**A**: Yes, but it is not recommended. It makes failures harder to isolate, reduces scaling flexibility, and complicates debugging.

### Q4: How should this be deployed in production?
**A**: Run the consumer as an independent service with Docker Compose, Kubernetes, or another process manager.

## Monitoring

### What to check
- **Lag**: number of pending messages waiting to be consumed.
- **Processing rate**: messages handled per second.
- **Error rate**: percentage of messages sent to the dead-letter queue.

## Summary

Remember this flow:
1. API publishes the Kafka message.
2. Kafka stores it.
3. The consumer must be running.
4. The consumer processes the file automatically.

During development you must start:
- the FastAPI server
- the Kafka consumer

Otherwise the file processing pipeline will not complete.
