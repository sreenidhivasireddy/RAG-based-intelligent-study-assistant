"""
Test script for Kafka producer and consumer
测试Kafka的生产和消费
"""
from app.clients.kafka import KafkaConfig
from app.models.file_processing_task import FileProcessingTask
from app.utils.logging import get_logger

logger = get_logger(__name__)


def test_send_tasks():
    """测试发送多个任务"""
    logger.info("=" * 60)
    logger.info("Testing Kafka Producer")
    logger.info("=" * 60)
    
    producer = KafkaConfig.get_producer()
    topic = KafkaConfig.get_file_processing_topic()
    
    # 创建测试任务
    test_tasks = [
        FileProcessingTask(
            file_md5="test_md5_001",
            file_path="http://localhost:9000/uploads/test1.pdf",
            file_name="test1.pdf"
        ),
        FileProcessingTask(
            file_md5="test_md5_002",
            file_path="http://localhost:9000/uploads/test2.docx",
            file_name="test2.docx"
        ),
    ]
    
    # 发送任务
    success_count = 0
    for i, task in enumerate(test_tasks, 1):
        logger.info(f"\n[{i}/{len(test_tasks)}] 发送任务: {task.file_name}")
        
        try:
            # 发送消息到Kafka
            future = producer.send(
                topic,
                key=task.file_md5,
                value=task.to_dict()
            )
            
            # 等待发送完成
            record_metadata = future.get(timeout=10)
            
            logger.info(
                f"✓ 任务发送成功: {task.file_name} "
                f"(partition={record_metadata.partition}, offset={record_metadata.offset})"
            )
            success_count += 1
            
        except Exception as e:
            logger.error(f"✗ 任务发送失败: {task.file_name}, 错误: {e}")
    
    logger.info("\n" + "=" * 60)
    logger.info(f"测试完成: 成功 {success_count}/{len(test_tasks)}")
    logger.info("=" * 60)


if __name__ == "__main__":
    test_send_tasks()