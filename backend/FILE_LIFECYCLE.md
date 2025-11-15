# 文件上传与处理生命周期设计

## 📊 Status 字段完整定义

| Status | 状态名称 | 含义 | 触发时机 | 后续动作 |
|--------|---------|------|---------|---------|
| **0** | `uploading` | 分片上传中 | 用户开始上传第一个分片 | 继续上传剩余分片 |
| **2** | `merged` | 已合并，待解析 | 所有分片合并成功 | 发送 Kafka 消息触发解析 |
| **3** | `parsing` | 解析中（可选） | 解析服务开始处理 | 文本提取、分块、向量化 |
| **1** | `completed` | 已完成，可检索 | 向量写入 ES 成功 | 用户可以搜索此文档 |
| **-1** | `failed` | 处理失败（可选） | 任意环节失败 | 人工介入或重试 |

---

## 🔄 完整生命周期流程

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. 用户上传分片                                                  │
│    POST /api/v1/upload/chunk (多次调用)                         │
│    ↓                                                            │
│    status = 0 (uploading)                                      │
│    Redis bitmap 记录进度                                        │
│    MySQL chunk_info 记录元数据                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. 用户调用合并接口                                              │
│    POST /api/v1/upload/merge                                   │
│    ↓                                                            │
│    • 验证所有分片已上传（Redis bitmap）                          │
│    • 从 MinIO 下载所有分片                                       │
│    • 按顺序拼接分片                                              │
│    • 上传完整文件到 documents/{md5}/{filename}                   │
│    • 更新 status = 2 (merged) ✅ 已修改                         │
│    • 发送 Kafka 消息到 "file-parse-topic"                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. Kafka 消费者：解析服务（待实现）                              │
│    Topic: file-parse-topic                                     │
│    ↓                                                            │
│    • 可选：更新 status = 3 (parsing)                            │
│    • 从 MinIO 下载完整文件                                       │
│    • 根据文件类型（PDF/Word/TXT）提取文本                        │
│    • 文本分块（chunking）                                        │
│    • 生成向量（embedding）                                       │
│    • 写入 Elasticsearch                                         │
│    • 更新 status = 1 (completed) ✅                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. 用户可以检索                                                  │
│    查询条件：WHERE status = 1                                   │
│    ↓                                                            │
│    • 前端显示"可搜索"状态                                        │
│    • 用户输入问题，向量检索命中此文档                            │
│    • RAG 流程返回相关内容                                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. 后台清理任务（定时任务，待实现）                              │
│    Cron: 每天凌晨 2 点运行                                       │
│    ↓                                                            │
│    • 查询 status = 1 且 merged_at < NOW() - 24h 的记录          │
│    • 删除 MinIO 中的临时分片（chunks/{md5}/*）                   │
│    • 保留完整文件（documents/{md5}/{filename}）                  │
│    • 记录清理日志                                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚨 关键设计原则

### ✅ status=1 的严格含义
`status=1` 表示文件**完全就绪，可被检索**，必须满足：

1. ✅ 文件已合并
2. ✅ 文本已提取
3. ✅ 向量已生成
4. ✅ 向量已写入 Elasticsearch
5. ✅ 用户可以通过 RAG 搜索到此文档

### ❌ status=1 不应该在合并时设置
如果在 `merge_file_service` 中设置 `status=1`，会导致：

- ❌ 用户看到"可搜索"，但实际还在解析中
- ❌ 前端调用检索 API，找不到内容（因为 ES 还没写入）
- ❌ 用户体验差：显示"已完成"但搜索不到

### ✅ 正确的做法
- 合并成功 → `status=2`（已合并，待解析）
- 解析成功 → `status=1`（完全就绪，可检索）

---

## 🛠️ 待实现的功能

### 1️⃣ 解析服务（优先级：高）

**位置**: `backend/app/services/parse_service.py`

**功能**:
```python
def parse_and_index_file(file_md5: str, file_name: str, storage_path: str):
    """
    解析文件并写入 Elasticsearch.
    
    Steps:
    1. Download file from MinIO
    2. Extract text based on file type (PDF/Word/TXT)
    3. Split text into chunks
    4. Generate embeddings for each chunk
    5. Write to Elasticsearch with vector field
    6. Update file_upload.status = 1
    """
    pass
```

**Kafka 消费者**:
```python
# backend/app/consumers/file_parser_consumer.py
from kafka import KafkaConsumer
import json

consumer = KafkaConsumer(
    'file-parse-topic',
    bootstrap_servers='localhost:9092',
    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
)

for message in consumer:
    data = message.value
    file_md5 = data['file_md5']
    file_name = data['file_name']
    storage_path = data['storage_path']
    
    try:
        parse_and_index_file(file_md5, file_name, storage_path)
    except Exception as e:
        logger.error(f"Failed to parse {file_md5}: {e}")
        # 可选：更新 status = -1 (failed)
```

---

### 2️⃣ 后台清理任务（优先级：中）

**位置**: `backend/app/tasks/cleanup_chunks.py`

**功能**:
```python
from apscheduler.schedulers.background import BackgroundScheduler
from app.clients.minio import minio_client, MINIO_BUCKET
from app.database import SessionLocal
from app.models.file_upload import FileUpload
from datetime import datetime, timedelta

def cleanup_old_chunks():
    """
    Clean up temporary chunks for files that have been successfully merged
    and indexed more than 24 hours ago.
    """
    db = SessionLocal()
    try:
        # Find files completed more than 24 hours ago
        cutoff_time = datetime.now() - timedelta(hours=24)
        files = db.query(FileUpload).filter(
            FileUpload.status == 1,
            FileUpload.merged_at < cutoff_time
        ).all()
        
        for file in files:
            # Delete chunks from MinIO
            chunk_prefix = f"chunks/{file.file_md5}/"
            objects = minio_client.list_objects(
                MINIO_BUCKET, 
                prefix=chunk_prefix, 
                recursive=True
            )
            
            for obj in objects:
                minio_client.remove_object(MINIO_BUCKET, obj.object_name)
                logger.info(f"Deleted chunk: {obj.object_name}")
            
            logger.info(f"Cleaned up chunks for {file.file_md5}")
            
    finally:
        db.close()

# Schedule task to run daily at 2:00 AM
scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_old_chunks, 'cron', hour=2, minute=0)
scheduler.start()
```

**启动方式**:
```bash
# 在 main.py 中启动调度器
from app.tasks.cleanup_chunks import scheduler

@app.on_event("startup")
def startup_event():
    logger.info("Starting background cleanup scheduler")
    # scheduler already started in cleanup_chunks.py
```

---

### 3️⃣ 前端状态展示

**API 响应示例**:
```json
GET /api/v1/upload/status?file_md5={md5}

{
  "code": 200,
  "data": {
    "file_md5": "...",
    "file_name": "年度报告.pdf",
    "status": 2,
    "status_text": "已合并，解析中...",
    "progress": 100.0,
    "created_at": "2025-11-14 10:00:00",
    "merged_at": "2025-11-14 10:05:00"
  }
}
```

**前端显示逻辑**:
```javascript
function getStatusDisplay(status) {
  switch(status) {
    case 0: return { text: "上传中", color: "blue", icon: "upload" };
    case 2: return { text: "解析中", color: "orange", icon: "loading" };
    case 1: return { text: "可检索", color: "green", icon: "check" };
    case -1: return { text: "失败", color: "red", icon: "error" };
  }
}
```

---

## 📝 修改总结

### 已修改 ✅
1. `app/services/upload.py` - `merge_file_service()` 
   - 状态更新从 `status=1` 改为 `status=2`
   - 注释更新，说明状态流转逻辑

2. `app/models/file_upload.py` - `FileUpload` 模型
   - status 字段注释更新，明确三种状态含义

### 待实现 🔜
1. 解析服务（`parse_service.py`）
2. Kafka 消费者（`file_parser_consumer.py`）
3. 后台清理任务（`cleanup_chunks.py`）
4. 前端状态展示优化

---

## 🎯 下一步建议

1. **立即验证修改**：重新运行测试，确认合并后 `status=2`
2. **实现解析服务**：创建 `parse_service.py`（优先级最高）
3. **集成 Kafka**：取消注释 `merge_file_service` 中的 Kafka 发送代码
4. **实现清理任务**：避免磁盘空间浪费
5. **前端对接**：展示不同状态给用户

需要我帮你实现解析服务吗？
