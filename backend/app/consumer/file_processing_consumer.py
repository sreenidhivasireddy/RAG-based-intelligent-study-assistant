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
from app.repositories.upload_repository import update_file_status
from app.utils.logging import get_logger
from app.services.blob_storage import blob_storage_client
from app.repositories.document_vector_repository import count_by_file_md5, find_by_file_md5
from app.database import SessionLocal
from app.repositories.upload_repository import update_file_status
from app.services.synthetic_eval_generation import trigger_synthetic_eval_generation_background

logger = get_logger(__name__)


class FileProcessingConsumer:
    """
    consumer for the file processing task
    listen to the Kafka topic and process the file task
    
    corresponds to the @KafkaListener annotation in Java
    """
    
    def __init__(
        self,
        parse_service,
        vectorization_service,
        max_retries: int = 4,
        retry_backoff_seconds: int = 3
    ):
        """
        initialize the consumer
        
        Args:
            parse_service: the parse service instance
            vectorization_service: the vectorization service instance
            max_retries: the maximum number of retries(corresponds to Java's DefaultErrorHandler configuration)
            retry_backoff_seconds: the retry interval in seconds(corresponds to Java's FixedBackOff 3000ms)
        """
        self.parse_service = parse_service
        self.vectorization_service = vectorization_service
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff_seconds
        
        self.topic = KafkaConfig.get_file_processing_topic()
        self.dlt_topic = KafkaConfig.get_dlt_topic()
        
        # create the consumer with topic(if not topic, consumer will not consume the message)
        self.consumer = KafkaConfig.create_consumer([self.topic])
        
        # create the DLT producer(for sending failed messages to the dead letter queue)
        self.dlt_producer = KafkaConfig.get_producer()
        
        logger.info(
            f"FileProcessingConsumer initialized: topic={self.topic}, "
            f"max_retries={self.max_retries}, "
            f"retry_backoff={self.retry_backoff}s"
        )
    
    def download_file_from_storage(self, file_path: str) -> BytesIO:
        """
        download the file from the storage system
    
        Args:
            file_path: the path or URL of the file
            
        Returns:
            BytesIO: the file stream
            
        Raises:
            Exception: raised when the file download fails
        """
        logger.info(f"Downloading file from storage: {file_path}")
        
        try:
            # if the file path is a HTTP/HTTPS URL
            if file_path.startswith('http://') or file_path.startswith('https://'):
                logger.info(f"Detected remote URL: {file_path}")
                
                response = requests.get(
                    file_path,
                    timeout=180,  # 3 minutes timeout(corresponds to Java's 180000ms)
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
            
            # If this is an Azure Blob path (e.g. 'documents/<md5>/<name>')
            else:
                # Heuristic: treat paths starting with the configured container prefix as blobs
                try:
                    if blob_storage_client and (file_path.startswith("documents/") or '/' in file_path):
                        logger.info(f"Detected blob storage path: {file_path}, downloading from blob storage")
                        data = blob_storage_client.download_bytes(file_path)
                        logger.info(f"Blob download succeeded, size: {len(data)} bytes")
                        return BytesIO(data)
                except Exception as be:
                    logger.warning(f"Blob storage download failed for {file_path}: {be}")

                # Fallback: local filesystem path
                logger.info(f"Detected file system path (fallback): {file_path}")
                with open(file_path, 'rb') as f:
                    content = f.read()
                logger.info(f"File read successfully, size: {len(content)} bytes")
                return BytesIO(content)
                
        except Exception as e:
            logger.error(f"Error downloading file from storage: {file_path}, error={e}")
            raise
    
    def process_task(self, task: FileProcessingTask) -> bool:
        """
        process the single file task
        
        
        Args:
            task: the file processing task
            
        Returns:
            bool: whether the task is processed successfully
        """
        logger.info(f"Received task: {task}")
        
        file_stream = None
        
        try:
            # 1. download the file
            file_stream = self.download_file_from_storage(task.file_path)
            
            if file_stream is None:
                raise Exception("The file stream is empty")
            
            # ensure the stream is seekable 
            if not file_stream.seekable():
                logger.warning("Stream is not seekable, converting to BytesIO")
                content = file_stream.read()
                file_stream = BytesIO(content)
            
            # 2. parse the file
            logger.info(f"Parsing file: fileMd5={task.file_md5}")
            
            # create the database session for parsing
            db = SessionLocal()
            
            try:
                chunk_count = self.parse_service.parse_and_save(
                    file_md5=task.file_md5,
                    file_name=task.file_name,
                    file_stream=file_stream,
                    db=db
                )
                # Log parsed chunk count and total characters
                try:
                    vectors = find_by_file_md5(db, task.file_md5)
                    total_chars = sum(len(v.text_content or "") for v in vectors)
                    logger.info(f"File parsed successfully, fileMd5: {task.file_md5}, chunks: {len(vectors)}, chars: {total_chars}")
                except Exception:
                    logger.info(f"File parsed successfully, fileMd5: {task.file_md5}")
            finally:
                db.close()
            
            # 3. Vectorize the file with a fresh DB session so newly parsed data is visible.
            logger.info(f"Vectorizing file: fileMd5={task.file_md5}")
            vectorize_db = SessionLocal()
            try:
                self.vectorization_service.vectorize(
                        file_md5=task.file_md5,
                        db=vectorize_db
                )
            finally:
                vectorize_db.close()
            logger.info(f"Vectorization completed, fileMd5: {task.file_md5}")
            logger.info(f"Update file status to completed: fileMd5={task.file_md5}")
            try:
                update_file_status(db, task.file_md5, status=1)
            except Exception as e:
                logger.warning(f"Could not update file status in DB: {e}")
            logger.info(f"File processing completed: fileMd5={task.file_md5}")
            
            # 4. Update the file status to completed (status=1).
            # The file has been parsed, vectorized, and indexed, and is now searchable.
            db = SessionLocal()
            try:
                update_file_status(db, task.file_md5, status=1)
                logger.info(f"File status updated to completed (status=1): fileMd5={task.file_md5}")
            finally:
                db.close()

            # Trigger synthetic QA generation in background after chunking + indexing completion.
            trigger_synthetic_eval_generation_background(
                document_id=task.file_md5,
                pipeline_version="synthetic-v1",
                replace_existing=True,
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Error processing task: {task}, error={e}",
                exc_info=True
            )
            raise
            
        finally:
            # ensure the input stream is closed
            if file_stream:
                try:
                    file_stream.close()
                except Exception as e:
                    logger.error(f"Error closing file stream: {e}")
    
    def send_to_dlt(self, message_value: dict, error_info: Exception):
        """
        send the failed message to the dead letter queue
        
        Args:
            message_value: the original message content
            error_info: the error information
        """
        try:
            logger.warning(
                f"Sending message to the dead letter queue: topic={self.dlt_topic}, "
                f"Original message={message_value}"
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
            future.get(timeout=5)  # wait for the DLT to send the message
            
            logger.info(f"Message sent to the dead letter queue: {self.dlt_topic}")
            
        except Exception as e:
            logger.error(f"Failed to send message to the dead letter queue: {e}", exc_info=True)
    
    def process_with_retry(
        self,
        task: FileProcessingTask,
        message_value: dict
    ) -> bool:
        """
        process the task with retry mechanism
        
        max 4 retries, 3 seconds interval
        
        Args:
            task: the file processing task
            message_value: the original message (for sending to DLT)
            
        Returns:
            bool: whether the task is processed successfully
        """
        retry_count = 0
        last_exception = None
        
        while retry_count <= self.max_retries:
            try:
                if retry_count > 0:
                    logger.info(
                        f"Retrying task (attempt {retry_count}/{self.max_retries}): "
                        f"file_md5={task.file_md5}, file_name={task.file_name}"
                    )
                
                # try to process the task
                self.process_task(task)
                
                # if successful, return
                if retry_count > 0:
                    logger.info(
                        f"Task retry successful: file_md5={task.file_md5}, "
                        f"Retry count={retry_count}"
                    )
                return True
                
            except Exception as e:
                last_exception = e
                retry_count += 1
                
                logger.error(
                    f"Task processing failed (attempt {retry_count}/{self.max_retries + 1}): "
                    f"file_md5={task.file_md5}, error={e}"
                )
                
                if retry_count <= self.max_retries:
                    # there are still retry opportunities, wait and retry
                    logger.info(
                        f"Waiting {self.retry_backoff} seconds before retrying... "
                        f"(Remaining retry attempts: {self.max_retries - retry_count + 1})"
                    )
                    time.sleep(self.retry_backoff)
                else:
                    # retry attempts exhausted, send to the dead letter queue
                    logger.error(
                        f"Task processing failed, max retry attempts reached ({self.max_retries} times), "
                        f"Sending to the dead letter queue: file_md5={task.file_md5}, "
                        f"fileName={task.file_name}"
                    )
                    self.send_to_dlt(message_value, last_exception)
                    return False
        
        return False
    
    def start_consuming(self):
        """
        start consuming messages
        """
        logger.info(f"Listening to Kafka topic: {self.topic}")
        logger.info(f"Consumer group: {KafkaConfig.CONSUMER_CONFIG['group_id']}")
        
        try:
            for message in self.consumer:
                logger.info(
                    f"Received message: topic={message.topic}, "
                    f"partition={message.partition}, "
                    f"offset={message.offset}, "
                    f"key={message.key}"
                )
                
                try:
                    # deserialize the task object
                    task = FileProcessingTask.from_dict(message.value)
                    
                    logger.info(
                        f"Task parsed successfully: file_md5={task.file_md5}, "
                        f"file_name={task.file_name}"
                    )
                    
                    # process the task (with retry mechanism)
                    success = self.process_with_retry(task, message.value)
                    
                    if success:
                        logger.info(
                            f"Task processed successfully: file_md5={task.file_md5}, "
                            f"file_name={task.file_name}"
                        )
                    else:
                        logger.error(
                            f"Task processing failed: file_md5={task.file_md5}, "
                            f"file_name={task.file_name}"
                        )
                    
                except Exception as e:
                    logger.error(
                        f"Error processing message: offset={message.offset}, error={e}",
                        exc_info=True
                    )
                    # continue processing the next message (don't block the entire consumer)
                    
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, stopping consumption...")
        except Exception as e:
            logger.error(f"Error in consumption loop: {e}", exc_info=True)
        finally:
            self.close()
    
    def close(self):
        """
        close the consumer and related resources
        """
        logger.info("Closing FileProcessingConsumer...")
        
        if self.consumer:
            try:
                self.consumer.close()
                logger.info("Kafka Consumer closed")
            except Exception as e:
                logger.error(f"Error closing Consumer: {e}")
        
        # note: don't close dlt_producer, it is globally shared
        # KafkaConfig will be closed when the application is closed
        
        logger.info("FileProcessingConsumer closed")
