"""
Kafka consumer service for processing file tasks.
Corresponds to Java's FileProcessingConsumer.java
"""
import time
import requests
from io import BytesIO
from typing import Optional
from kafka.errors import KafkaError

from app.clients.kafka import KafkaConfig
from app.models.file_processing_task import FileProcessingTask
from app.utils.logging import get_logger

logger = get_logger(__name__)


class FileProcessingConsumer:
    """
    文件处理任务消费者
    监听Kafka主题并处理文件任务
    
    对应Java的 @KafkaListener 注解的消费者
    """
    
    def __init__(
        self,
        parse_service,
        vectorization_service,
        max_retries: int = 4,
        retry_backoff_seconds: int = 3
    ):
        """
        初始化消费者
        
        Args:
            parse_service: 文件解析服务实例
            vectorization_service: 向量化服务实例
            max_retries: 最大重试次数（对应Java的DefaultErrorHandler配置）
            retry_backoff_seconds: 重试间隔秒数（对应Java的FixedBackOff 3000ms）
        """
        self.parse_service = parse_service
        self.vectorization_service = vectorization_service
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff_seconds
        
        self.topic = KafkaConfig.get_file_processing_topic()
        self.dlt_topic = KafkaConfig.get_dlt_topic()
        
        # 创建消费者
        self.consumer = KafkaConfig.create_consumer([self.topic])
        
        # 创建DLT生产者（用于发送失败消息到死信队列）
        self.dlt_producer = KafkaConfig.get_producer()
        
        logger.info(
            f"FileProcessingConsumer initialized: topic={self.topic}, "
            f"max_retries={self.max_retries}, "
            f"retry_backoff={self.retry_backoff}s"
        )
    
    def download_file_from_storage(self, file_path: str) -> BytesIO:
        """
        从存储系统下载文件
        
        对应Java的 downloadFileFromStorage 方法
        
        Args:
            file_path: 文件路径或URL
            
        Returns:
            BytesIO: 文件流
            
        Raises:
            Exception: 下载失败时抛出异常
        """
        logger.info(f"Downloading file from storage: {file_path}")
        
        try:
            # 如果是HTTP/HTTPS URL
            if file_path.startswith('http://') or file_path.startswith('https://'):
                logger.info(f"Detected remote URL: {file_path}")
                
                response = requests.get(
                    file_path,
                    timeout=180,  # 3分钟超时（对应Java的180000ms）
                    headers={'User-Agent': 'SmartPAI-FileProcessor/1.0'},
                    stream=True
                )
                
                if response.status_code == 200:
                    logger.info("Successfully connected to URL, starting download...")
                    content = response.content
                    logger.info(f"File downloaded successfully, size: {len(content)} bytes")
                    return BytesIO(content)
                elif response.status_code == 403:
                    raise Exception("Access forbidden - the presigned URL may have expired")
                else:
                    raise Exception(
                        f"Failed to download file, HTTP response code: {response.status_code}"
                    )
            
            # 如果是本地文件路径
            else:
                logger.info(f"Detected file system path: {file_path}")
                with open(file_path, 'rb') as f:
                    content = f.read()
                logger.info(f"File read successfully, size: {len(content)} bytes")
                return BytesIO(content)
                
        except Exception as e:
            logger.error(f"Error downloading file from storage: {file_path}, error={e}")
            raise
    
    def process_task(self, task: FileProcessingTask) -> bool:
        """
        处理单个文件任务
        
        对应Java的 @KafkaListener processTask 方法:
        public void processTask(FileProcessingTask task) {
            // 下载文件
            fileStream = downloadFileFromStorage(task.getFilePath());
            // 解析文件
            parseService.parseAndSave(...);
            // 向量化处理
            vectorizationService.vectorize(...);
        }
        
        Args:
            task: 文件处理任务
            
        Returns:
            bool: 处理是否成功
        """
        logger.info(f"Received task: {task}")
        logger.info(
            f"文件权限信息: userId={task.user_id}, "
            f"orgTag={task.org_tag}, isPublic={task.is_public}"
        )
        
        file_stream = None
        
        try:
            # 1. 下载文件
            file_stream = self.download_file_from_storage(task.file_path)
            
            if file_stream is None:
                raise Exception("流为空")
            
            # 确保流支持mark/reset（对应Java的BufferedInputStream）
            if not file_stream.seekable():
                logger.warning("Stream is not seekable, converting to BytesIO")
                content = file_stream.read()
                file_stream = BytesIO(content)
            
            # 2. 解析文件
            logger.info(f"开始解析文件: fileMd5={task.file_md5}")
            
            # 创建数据库会话用于解析
            from app.database import SessionLocal
            db = SessionLocal()
            
            try:
                self.parse_service.parse_and_save(
                    file_md5=task.file_md5,
                    file_name=task.file_name,
                    file_stream=file_stream,
                    db=db
                )
                logger.info(f"文件解析完成，fileMd5: {task.file_md5}")
            finally:
                db.close()
            
            # 3. 向量化处理
            logger.info(f"开始向量化处理: fileMd5={task.file_md5}")
            self.vectorization_service.vectorize(
                file_md5=task.file_md5
            )
            logger.info(f"向量化完成，fileMd5: {task.file_md5}")
            
            return True
            
        except Exception as e:
            logger.error(
                f"Error processing task: {task}, error={e}",
                exc_info=True
            )
            # 抛出异常让重试机制捕获（对应Java的throw new RuntimeException）
            raise
            
        finally:
            # 确保关闭输入流
            if file_stream:
                try:
                    file_stream.close()
                except Exception as e:
                    logger.error(f"Error closing file stream: {e}")
    
    def send_to_dlt(self, message_value: dict, error_info: Exception):
        """
        发送失败消息到死信队列
        
        对应Java的 DeadLetterPublishingRecoverer
        
        Args:
            message_value: 原始消息内容
            error_info: 错误信息
        """
        try:
            logger.warning(
                f"发送消息到死信队列: topic={self.dlt_topic}, "
                f"原消息={message_value}"
            )
            
            dlt_message = {
                'originalMessage': message_value,
                'error': str(error_info),
                'errorType': type(error_info).__name__,
                'timestamp': time.time(),
                'retryCount': self.max_retries
            }
            
            future = self.dlt_producer.send(
                self.dlt_topic,
                value=dlt_message
            )
            future.get(timeout=5)  # 等待DLT发送完成
            
            logger.info(f"消息已发送到死信队列: {self.dlt_topic}")
            
        except Exception as e:
            logger.error(f"发送到死信队列失败: {e}", exc_info=True)
    
    def process_with_retry(
        self,
        task: FileProcessingTask,
        message_value: dict
    ) -> bool:
        """
        带重试机制的任务处理
        
        对应Java的 DefaultErrorHandler 和 FixedBackOff:
        DefaultErrorHandler errorHandler = new DefaultErrorHandler(
            recoverer, 
            new FixedBackOff(3000L, 4)
        );
        
        最多重试4次，每次间隔3秒
        
        Args:
            task: 文件处理任务
            message_value: 原始消息（用于发送到DLT）
            
        Returns:
            bool: 处理是否成功
        """
        retry_count = 0
        last_exception = None
        
        while retry_count <= self.max_retries:
            try:
                if retry_count > 0:
                    logger.info(
                        f"重试处理任务 (第{retry_count}/{self.max_retries}次): "
                        f"file_md5={task.file_md5}, file_name={task.file_name}"
                    )
                
                # 尝试处理任务
                self.process_task(task)
                
                # 成功则返回
                if retry_count > 0:
                    logger.info(
                        f"任务重试成功: file_md5={task.file_md5}, "
                        f"重试次数={retry_count}"
                    )
                return True
                
            except Exception as e:
                last_exception = e
                retry_count += 1
                
                logger.error(
                    f"处理失败 (尝试 {retry_count}/{self.max_retries + 1}): "
                    f"file_md5={task.file_md5}, error={e}"
                )
                
                if retry_count <= self.max_retries:
                    # 还有重试机会，等待后重试
                    logger.info(
                        f"等待 {self.retry_backoff} 秒后重试... "
                        f"(剩余重试次数: {self.max_retries - retry_count + 1})"
                    )
                    time.sleep(self.retry_backoff)
                else:
                    # 重试次数用尽，发送到死信队列
                    logger.error(
                        f"任务处理失败，已达最大重试次数({self.max_retries}次)，"
                        f"发送到死信队列: file_md5={task.file_md5}, "
                        f"fileName={task.file_name}"
                    )
                    self.send_to_dlt(message_value, last_exception)
                    return False
        
        return False
    
    def start_consuming(self):
        """
        开始消费消息
        
        这是主要的消费循环，对应Java的 @KafkaListener 自动监听
        """
        logger.info(f"开始监听Kafka主题: {self.topic}")
        logger.info(f"消费者组: {KafkaConfig.CONSUMER_CONFIG['group_id']}")
        
        try:
            for message in self.consumer:
                logger.info(
                    f"接收到消息: topic={message.topic}, "
                    f"partition={message.partition}, "
                    f"offset={message.offset}, "
                    f"key={message.key}"
                )
                
                try:
                    # 反序列化任务对象
                    task = FileProcessingTask.from_dict(message.value)
                    
                    logger.info(
                        f"解析任务成功: file_md5={task.file_md5}, "
                        f"file_name={task.file_name}"
                    )
                    
                    # 处理任务（带重试机制）
                    success = self.process_with_retry(task, message.value)
                    
                    if success:
                        logger.info(
                            f"任务处理成功: file_md5={task.file_md5}, "
                            f"file_name={task.file_name}"
                        )
                    else:
                        logger.error(
                            f"任务处理最终失败: file_md5={task.file_md5}, "
                            f"file_name={task.file_name}"
                        )
                    
                except Exception as e:
                    logger.error(
                        f"处理消息时发生错误: offset={message.offset}, error={e}",
                        exc_info=True
                    )
                    # 继续处理下一条消息（不让一条错误消息阻塞整个消费者）
                    
        except KeyboardInterrupt:
            logger.info("收到中断信号，停止消费...")
        except Exception as e:
            logger.error(f"消费循环出错: {e}", exc_info=True)
        finally:
            self.close()
    
    def close(self):
        """
        关闭消费者和相关资源
        
        对应Java中的资源清理
        """
        logger.info("正在关闭FileProcessingConsumer...")
        
        if self.consumer:
            try:
                self.consumer.close()
                logger.info("Kafka Consumer已关闭")
            except Exception as e:
                logger.error(f"关闭Consumer时出错: {e}")
        
        # 注意：不要关闭dlt_producer，因为它是全局共享的
        # KafkaConfig会在应用关闭时统一关闭
        
        logger.info("FileProcessingConsumer已关闭")