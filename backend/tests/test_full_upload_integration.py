"""
完整的文件上传集成测试
测试流程：
1. 分片上传文件
2. 合并文件
3. Kafka 发送任务
4. Consumer 消费并处理（parse + vectorize）
5. 验证 MySQL 和 Elasticsearch 中的数据
6. 清理测试数据

测试文件：Desktop/NLP_lab06_QA.pdf
"""

import os
import io
import time
import hashlib
import threading
from pathlib import Path
from typing import Optional
import sys

# Add backend to PYTHONPATH
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.database import SessionLocal
from app.clients.kafka import KafkaConfig
from app.clients.minio import minio_client, MINIO_BUCKET
from app.services.parse_service import ParseService
from app.services.vectorize_service import VectorizationService
from app.services.es_service import ElasticsearchService
from app.services.upload import upload_chunk_service, merge_file_service
from app.repositories import upload_repository, document_vector_repository
from app.consumer.file_processing_consumer import FileProcessingConsumer
from app.clients.gemini_embedding_client import GeminiEmbeddingClient
from app.models.file_processing_task import FileProcessingTask
from app.schemas.upload import ChunkUploadRequest
import app.clients.elastic as es
from app.clients.elastic import ES_INDEX
from app.utils.logging import get_logger

logger = get_logger(__name__)

# 测试配置
TEST_FILE_PATH = os.path.expanduser("~/Desktop/NLP_lab06_QA.pdf")
CHUNK_SIZE = 5 * 1024 * 1024  # 5MB per chunk
TEST_USER_ID = "test_user_001"
TEST_ORG_TAG = "test_org"
TEST_IS_PUBLIC = False

# 全局变量
test_file_md5: Optional[str] = None
consumer_thread: Optional[threading.Thread] = None
consumer_running = False


def calculate_file_md5(file_path: str) -> str:
    """计算文件的 MD5"""
    logger.info(f"计算文件 MD5: {file_path}")
    
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)
    
    file_md5 = md5_hash.hexdigest()
    logger.info(f"文件 MD5: {file_md5}")
    return file_md5


def split_file_to_chunks(file_path: str) -> list[bytes]:
    """将文件分片"""
    chunks = []
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            chunks.append(chunk)
    
    logger.info(f"文件分片完成: {len(chunks)} 个分片")
    return chunks


def test_step_1_upload_chunks():
    """步骤1：分片上传文件"""
    global test_file_md5
    
    logger.info("=" * 80)
    logger.info("步骤 1: 分片上传文件")
    logger.info("=" * 80)
    
    # 检查文件是否存在
    if not os.path.exists(TEST_FILE_PATH):
        raise FileNotFoundError(f"测试文件不存在: {TEST_FILE_PATH}")
    
    # 获取文件大小
    file_size = os.path.getsize(TEST_FILE_PATH)
    logger.info(f"文件路径: {TEST_FILE_PATH}")
    logger.info(f"文件大小: {file_size / 1024 / 1024:.2f} MB")
    
    # 计算文件 MD5
    test_file_md5 = calculate_file_md5(TEST_FILE_PATH)
    
    # 分片文件
    chunks = split_file_to_chunks(TEST_FILE_PATH)
    total_chunks = len(chunks)
    
    db = SessionLocal()
    
    try:
        # 上传每个分片
        for chunk_index, chunk_data in enumerate(chunks):
            logger.info(f"上传分片 {chunk_index + 1}/{total_chunks} (大小: {len(chunk_data) / 1024:.2f} KB)")
            
            # 创建请求对象
            request = ChunkUploadRequest(
                file_md5=test_file_md5,
                chunk_index=chunk_index,
                total_chunks=total_chunks,
                file_name=os.path.basename(TEST_FILE_PATH),
                total_size=file_size
            )
            
            # 上传分片
            result = upload_chunk_service(
                db=db,
                request=request,
                file_data=chunk_data
            )
            
            logger.info(f"✓ 分片 {chunk_index} 上传成功")
        
        logger.info(f"\n✅ 所有分片上传完成: {total_chunks} 个分片")
        
    finally:
        db.close()


def test_step_2_merge_file_and_send_to_kafka():
    """步骤2：合并文件并发送到 Kafka"""
    logger.info("\n" + "=" * 80)
    logger.info("步骤 2: 合并文件并发送到 Kafka")
    logger.info("=" * 80)
    
    db = SessionLocal()
    
    try:
        # 1. 合并文件
        logger.info(f"开始合并文件: {test_file_md5}")
        
        result = merge_file_service(
            db=db,
            file_md5=test_file_md5,
            file_name=os.path.basename(TEST_FILE_PATH)
        )
        
        logger.info(f"✅ 文件合并成功")
        logger.info(f"   MinIO 路径: {result.get('object_url', 'N/A')}")
        logger.info(f"   文件大小: {result.get('file_size', 0) / 1024:.2f} KB")
        
        # 2. 生成 MinIO 预签名 URL
        object_name = result['object_url']
        logger.info(f"object_name: {object_name}")
        logger.info(f"minio_client is None: {minio_client is None}")
        logger.info(f"starts with http: {object_name.startswith('http')}")
        
        if minio_client and not object_name.startswith('http'):
            # 生成预签名 URL (有效期 7天)
            from datetime import timedelta
            logger.info(f"正在为 MinIO 对象生成预签名 URL: {object_name}")
            presigned_url = minio_client.presigned_get_object(
                MINIO_BUCKET,
                object_name,
                expires=timedelta(days=7)
            )
            file_url = presigned_url
            logger.info(f"✅ 生成预签名 URL成功")
            logger.info(f"   URL: {file_url[:150]}...")
        else:
            logger.info(f"使用原始路径: {object_name}")
            file_url = object_name
        
        # 3. 发送任务到 Kafka
        task = FileProcessingTask(
            file_md5=test_file_md5,
            file_path=file_url,
            file_name=os.path.basename(TEST_FILE_PATH),
            user_id=TEST_USER_ID,
            org_tag=TEST_ORG_TAG,
            is_public=TEST_IS_PUBLIC
        )
        
        producer = KafkaConfig.get_producer()
        topic = KafkaConfig.get_file_processing_topic()
        
        logger.info(f"发送任务到 Kafka: topic={topic}")
        
        future = producer.send(
            topic,
            key=task.file_md5,
            value=task.to_dict()
        )
        
        record_metadata = future.get(timeout=10)
        
        logger.info(
            f"✅ Kafka 消息发送成功: "
            f"partition={record_metadata.partition}, "
            f"offset={record_metadata.offset}"
        )
        
        return result
        
    finally:
        db.close()


def start_consumer_thread():
    """启动 Consumer 线程"""
    global consumer_running
    
    logger.info("\n" + "=" * 80)
    logger.info("步骤 3: 启动 Kafka Consumer")
    logger.info("=" * 80)
    
    # 创建服务实例
    db = SessionLocal()
    parse_service = ParseService(chunk_size=500)
    
    # 创建 embedding 客户端
    if not GeminiEmbeddingClient.is_configured():
        raise RuntimeError("GEMINI_API_KEY 未配置")
    embedding_client = GeminiEmbeddingClient()
    
    # 创建 ES 服务
    es_client = es.get_client()
    es_service = ElasticsearchService(es_client)
    
    # 创建向量化服务
    vectorization_service = VectorizationService(
        embedding_client=embedding_client,
        elasticsearch_service=es_service,
        db=db
    )
    
    # 创建 consumer
    consumer = FileProcessingConsumer(
        parse_service=parse_service,
        vectorization_service=vectorization_service,
        max_retries=4,
        retry_backoff_seconds=3
    )
    
    consumer_running = True
    
    def consume_messages():
        """消费消息的函数"""
        logger.info("Consumer 开始监听 Kafka 消息...")
        
        try:
            # 只处理我们的测试消息
            processed = 0
            max_messages = 10  # 最多处理10条消息
            max_wait_seconds = 30  # 最多等待30秒
            
            import time as time_module
            start_time = time_module.time()
            
            for message in consumer.consumer:
                if not consumer_running:
                    break
                
                # 检查超时
                if time_module.time() - start_time > max_wait_seconds:
                    logger.info("Consumer 等待超时，退出")
                    break
                
                logger.info(f"收到 Kafka 消息: file_md5={message.value.get('file_md5', 'N/A')}")
                
                # 处理消息
                task = FileProcessingTask.from_dict(message.value)
                
                # 只处理我们的测试文件
                if task.file_md5 == test_file_md5:
                    logger.info(f"✓ 找到目标消息，开始处理: {task.file_name}")
                    success = consumer.process_task(task)
                    
                    if success:
                        logger.info(f"✅ 任务处理成功: {task.file_name}")
                    else:
                        logger.error(f"❌ 任务处理失败: {task.file_name}")
                    
                    # 处理完我们的消息后退出
                    break
                else:
                    logger.info(f"跳过其他消息: {task.file_md5}")
                
                processed += 1
                if processed >= max_messages:
                    logger.info(f"已处理 {processed} 条消息，停止 consumer")
                    break
                    
        except Exception as e:
            logger.error(f"Consumer 处理消息失败: {e}", exc_info=True)
        finally:
            consumer.close()
            db.close()
    
    # 启动线程
    thread = threading.Thread(target=consume_messages, daemon=True)
    thread.start()
    
    logger.info("✓ Consumer 线程已启动")
    
    return thread


def test_step_3_wait_for_processing():
    """步骤3：等待 Kafka Consumer 处理"""
    global consumer_thread
    
    # 启动 consumer
    consumer_thread = start_consumer_thread()
    
    # 等待处理完成
    logger.info("\n等待 Consumer 处理任务...")
    
    # 最多等待 60 秒
    consumer_thread.join(timeout=60)
    
    if consumer_thread.is_alive():
        logger.warning("Consumer 线程仍在运行，可能需要更多时间")
    else:
        logger.info("✅ Consumer 处理完成")


def test_step_4_verify_mysql():
    """步骤4：验证 MySQL 中的数据"""
    logger.info("\n" + "=" * 80)
    logger.info("步骤 4: 验证 MySQL 数据")
    logger.info("=" * 80)
    
    db = SessionLocal()
    
    try:
        # 查询文本块
        chunks = document_vector_repository.find_by_file_md5(db, test_file_md5)
        
        if not chunks:
            raise AssertionError(f"❌ MySQL 中未找到文档块: {test_file_md5}")
        
        logger.info(f"✅ MySQL 验证成功")
        logger.info(f"   找到 {len(chunks)} 个文本块")
        logger.info(f"   示例块内容: {chunks[0].text_content[:100]}...")
        
        return len(chunks)
        
    finally:
        db.close()


def test_step_5_verify_elasticsearch():
    """步骤5：验证 Elasticsearch 中的数据"""
    logger.info("\n" + "=" * 80)
    logger.info("步骤 5: 验证 Elasticsearch 数据")
    logger.info("=" * 80)
    
    es_client = es.get_client()
    
    # 等待 ES 索引刷新
    time.sleep(2)
    
    # 查询 ES
    resp = es_client.search(
        index=ES_INDEX,
        query={"term": {"file_md5": {"value": test_file_md5}}},
        size=1000
    )
    
    hits = resp["hits"]["hits"]
    
    if not hits:
        raise AssertionError(f"❌ Elasticsearch 中未找到文档: {test_file_md5}")
    
    logger.info(f"✅ Elasticsearch 验证成功")
    logger.info(f"   找到 {len(hits)} 个文档")
    
    # 验证文档结构
    doc = hits[0]["_source"]
    logger.info(f"   文档字段: {list(doc.keys())}")
    logger.info(f"   示例文本: {doc.get('text_content', '')[:100]}...")
    
    assert "file_md5" in doc
    assert "chunk_id" in doc
    assert "text_content" in doc
    assert "model_version" in doc
    
    return len(hits)


def test_step_6_cleanup():
    """步骤6：清理测试数据"""
    logger.info("\n" + "=" * 80)
    logger.info("步骤 6: 清理测试数据")
    logger.info("=" * 80)
    
    db = SessionLocal()
    
    try:
        # 1. 清理 MySQL 文档向量
        deleted_chunks = document_vector_repository.delete_by_file_md5(db, test_file_md5)
        logger.info(f"✓ 清理 MySQL: 删除 {deleted_chunks} 个文本块")
        
        # 2. 清理 MinIO（可选）
        try:
            if minio_client:
                # 删除合并后的文件（注意路径包含 "documents/" 前缀）
                object_name = f"documents/{test_file_md5}/{os.path.basename(TEST_FILE_PATH)}"
                minio_client.remove_object(MINIO_BUCKET, object_name)
                logger.info(f"✓ 清理 MinIO 合并文件: {object_name}")
        except Exception as e:
            logger.warning(f"MinIO 合并文件清理失败: {e}")
        
        # 5. 清理 MinIO 分片文件
        try:
            if minio_client:
                # 删除所有分片
                objects = minio_client.list_objects(
                    MINIO_BUCKET, 
                    prefix=f"chunks/{test_file_md5}/", 
                    recursive=True
                )
                deleted_count = 0
                for obj in objects:
                    minio_client.remove_object(MINIO_BUCKET, obj.object_name)
                    deleted_count += 1
                
                if deleted_count > 0:
                    logger.info(f"✓ 清理 MinIO 分片文件: 删除 {deleted_count} 个分片")
                else:
                    logger.info("✓ 清理 MinIO 分片文件: 无需清理")
        except Exception as e:
            logger.warning(f"MinIO 分片文件清理失败: {e}")
        
        # 6. 清理 Elasticsearch
        es_client = es.get_client()
        result = es_client.delete_by_query(
            index=ES_INDEX,
            query={"term": {"file_md5": {"value": test_file_md5}}}
        )
        logger.info(f"✓ 清理 Elasticsearch: 删除 {result.get('deleted', 0)} 个文档")
        
        logger.info("✅ 所有测试数据已清理")
        
    finally:
        db.close()


def run_full_integration_test():
    """运行完整的集成测试"""
    global consumer_running
    
    logger.info("\n")
    logger.info("=" * 80)
    logger.info("🚀 完整文件上传集成测试")
    logger.info("=" * 80)
    logger.info(f"测试文件: {TEST_FILE_PATH}")
    logger.info("=" * 80)
    
    start_time = time.time()
    
    try:
        # 步骤 1：上传分片
        test_step_1_upload_chunks()
        
        # 步骤 2：合并文件并发送到 Kafka
        merge_result = test_step_2_merge_file_and_send_to_kafka()
        
        # 步骤 3：启动 Consumer 并等待处理
        test_step_3_wait_for_processing()
        
        # 给予一些时间让处理完成
        time.sleep(5)
        
        # 步骤 4：验证 MySQL
        chunk_count = test_step_4_verify_mysql()
        
        # 步骤 5：验证 Elasticsearch
        es_doc_count = test_step_5_verify_elasticsearch()
        
        # 验证数量一致性
        if chunk_count != es_doc_count:
            logger.warning(
                f"⚠️ 警告: MySQL 块数 ({chunk_count}) 与 ES 文档数 ({es_doc_count}) 不一致"
            )
        
        elapsed_time = time.time() - start_time
        
        logger.info("\n" + "=" * 80)
        logger.info("🎉 集成测试全部通过！")
        logger.info("=" * 80)
        logger.info(f"✓ 文件 MD5: {test_file_md5}")
        logger.info(f"✓ MySQL 文本块: {chunk_count}")
        logger.info(f"✓ ES 文档数: {es_doc_count}")
        logger.info(f"✓ 总耗时: {elapsed_time:.2f} 秒")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"\n❌ 集成测试失败: {e}", exc_info=True)
        raise
        
    finally:
        # 停止 consumer
        consumer_running = False
        
        # 清理测试数据
        if test_file_md5:
            try:
                test_step_6_cleanup()
            except Exception as e:
                logger.error(f"清理测试数据失败: {e}")


if __name__ == "__main__":
    run_full_integration_test()

