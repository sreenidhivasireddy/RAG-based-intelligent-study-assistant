# Kafka Consumer 使用说明

## 当前架构

```
┌─────────────────────────────────────────────────────────────┐
│                      完整的文件处理流程                        │
└─────────────────────────────────────────────────────────────┘

1. 用户上传文件
   ↓
2. API 接收文件并分片上传到 MinIO
   ↓
3. API 合并文件并生成预签名 URL
   ↓
4. API 创建 FileProcessingTask 并发送到 Kafka  ← 你已完成
   ↓
5. Kafka 存储消息（队列中）
   ↓
6. Consumer 监听并拉取消息                     ← 需要手动启动
   ↓
7. Consumer 下载文件、解析、向量化、存储到 ES
   ↓
8. 用户可以搜索文件内容
```

## 为什么需要单独启动 Consumer？

### Kafka 的消息队列模型

- **Producer（生产者）**：API 中的代码，只负责把任务发送到 Kafka
  - 文件：`backend/app/api/upload.py`
  - 作用：发送消息后立即返回，不等待处理完成
  
- **Kafka（消息队列）**：存储消息，等待被消费
  - 消息会一直保留在队列中，直到被 Consumer 消费
  
- **Consumer（消费者）**：独立运行的进程，持续监听 Kafka
  - 文件：`backend/app/consumer/file_processing_consumer.py`
  - 作用：从 Kafka 拉取消息，处理文件（解析、向量化）

### 为什么不自动启动？

1. **解耦设计**：API 服务和消息处理服务分离
   - API 只负责接收请求，快速响应
   - Consumer 负责耗时的后台处理
   
2. **独立扩展**：可以运行多个 Consumer 实例来处理大量任务
   ```bash
   # Terminal 1
   python -m app.consumer.run_consumer
   
   # Terminal 2
   python -m app.consumer.run_consumer
   
   # Terminal 3
   python -m app.consumer.run_consumer
   ```
   
3. **故障隔离**：Consumer 崩溃不影响 API 服务

4. **灵活部署**：可以在不同机器上运行

## 启动 Consumer

### 方式 1：使用启动脚本（推荐）

```bash
cd backend
./start_consumer.sh
```

### 方式 2：直接运行 Python 模块

```bash
cd backend
python -m app.consumer.run_consumer
```

### 方式 3：后台运行

```bash
cd backend
nohup python -m app.consumer.run_consumer > logs/consumer.log 2>&1 &

# 查看日志
tail -f logs/consumer.log

# 停止 Consumer
ps aux | grep run_consumer
kill <PID>
```

## 开发流程

### 1. 启动所有服务

打开 **4 个终端窗口**：

**Terminal 1 - Kafka & Zookeeper**
```bash
# 启动 Kafka (如果使用 Docker)
docker-compose up kafka zookeeper
```

**Terminal 2 - FastAPI 服务**
```bash
cd backend
./start_server.sh
# 或
uvicorn app.main:app --reload
```

**Terminal 3 - Kafka Consumer**  ⭐ **重要：这个必须启动！**
```bash
cd backend
./start_consumer.sh
```

**Terminal 4 - 测试/调试**
```bash
# 运行测试
python backend/tests/test_full_upload_integration.py

# 或手动测试 API
curl -X POST http://localhost:8000/api/v1/upload/chunk ...
```

### 2. 验证 Consumer 是否运行

Consumer 启动后会输出：

```
================================================================================
🚀 Starting File Processing Kafka Consumer
================================================================================
Initializing database connection...
Initializing parse service...
Initializing Gemini embedding client...
Initializing Elasticsearch service...
Initializing vectorization service...
Creating Kafka Consumer...
================================================================================
✅ All services initialized successfully
================================================================================
Consumer is now listening for messages...
Press Ctrl+C to stop
================================================================================
```

### 3. 上传文件测试

```bash
# 1. 上传文件分片
curl -X POST "http://localhost:8000/api/v1/upload/chunk" \
  -F "file=@test.pdf" \
  -F "fileMd5=abc123" \
  -F "chunkIndex=0" \
  -F "totalSize=1024000" \
  -F "fileName=test.pdf"

# 2. 合并文件
curl -X POST "http://localhost:8000/api/v1/upload/merge" \
  -H "Content-Type: application/json" \
  -d '{"file_md5": "abc123", "file_name": "test.pdf"}'

# 此时检查 Consumer 终端，应该看到处理日志：
# Received message: topic=file-processing-topic1, ...
# Downloading file from storage: http://...
# File downloaded successfully, size: 1024000 bytes
# Parsing file: fileMd5=abc123
# ...
```

## 常见问题

### Q1: 为什么我上传文件后没有被处理？

**A**: Consumer 没有启动！请确保：
1. Consumer 进程正在运行（检查 Terminal 3）
2. Consumer 日志中显示 "listening for messages"
3. Kafka 服务正常运行

### Q2: 测试为什么能跑通？

**A**: 测试代码 `test_full_upload_integration.py` 中显式启动了 Consumer：

```python
consumer = FileProcessingConsumer(...)
consumer.start_consuming()  # 测试中手动启动
```

### Q3: 可以把 Consumer 和 API 放在一起运行吗？

**A**: 可以，但不推荐。参考 `app/main.py` 添加：

```python
@app.on_event("startup")
async def startup_event():
    # 后台线程启动 Consumer
    threading.Thread(target=start_consumer, daemon=True).start()
```

但这样做的缺点是：
- Consumer 崩溃可能影响 API
- 无法独立扩展
- 调试困难

### Q4: 生产环境如何部署？

**A**: 使用 Docker Compose 或 Kubernetes 部署为独立服务：

```yaml
# docker-compose.yml
services:
  api:
    image: your-app:latest
    command: uvicorn app.main:app --host 0.0.0.0
  
  consumer:
    image: your-app:latest
    command: python -m app.consumer.run_consumer
    deploy:
      replicas: 3  # 运行 3 个 Consumer 实例
```

## 监控 Consumer

### 检查 Consumer 状态

```bash
# 查看 Consumer 进程
ps aux | grep run_consumer

# 查看日志
tail -f backend/app/logs/app.log

# 查看 Kafka Consumer Group 状态
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group file-processing-group --describe
```

### Consumer 健康指标

- **Lag**：待处理消息数量（应该保持在低水平）
- **处理速度**：每秒处理的消息数
- **错误率**：发送到死信队列的消息比例

## 总结

**记住这个流程**：

1. ✅ API 发送消息到 Kafka（已完成，在 `upload.py` 中）
2. ⏳ Kafka 存储消息（自动）
3. ❗ **Consumer 必须手动启动**（`./start_consumer.sh`）
4. ✅ Consumer 处理消息（自动拉取并处理）

**开发时必须启动**：
- FastAPI 服务（`./start_server.sh`）
- Kafka Consumer（`./start_consumer.sh`）⭐

这样整个文件处理流程才能完整运行！

