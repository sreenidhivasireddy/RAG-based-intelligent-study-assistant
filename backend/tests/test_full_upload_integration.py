"""
Full Upload Integration Test
Test Flow:
1. Upload chunks
2. Merge file and send to Kafka
3. Consumer consume and process (parse + vectorize)
4. Verify MySQL and Elasticsearch data
5. Cleanup test data

Test File: Desktop/NLP_lab06_QA.pdf
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

# Test Configuration
TEST_FILE_PATH = os.path.expanduser("~/Downloads/Day19 - DevSecOps (1).pdf")
CHUNK_SIZE = 5 * 1024 * 1024  # 5MB per chunk

# Global variables
test_file_md5: Optional[str] = None
consumer_thread: Optional[threading.Thread] = None
consumer_running = False


def calculate_file_md5(file_path: str) -> str:
    """calculate the MD5 of the file"""
    logger.info(f"Calculating MD5 of the file: {file_path}")
    
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)
    
    file_md5 = md5_hash.hexdigest()
    logger.info(f"MD5: {file_md5}")
    return file_md5


def split_file_to_chunks(file_path: str) -> list[bytes]:
    """split the file into chunks"""
    chunks = []
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            chunks.append(chunk)
    
    logger.info(f"File split completed: {len(chunks)} chunks")
    return chunks


def test_step_1_upload_chunks():
    """step 1: upload chunks"""
    global test_file_md5
    
    logger.info("=" * 80)
    logger.info("step 1: upload chunks")
    logger.info("=" * 80)
    
    # check if the file exists
    if not os.path.exists(TEST_FILE_PATH):
        raise FileNotFoundError(f"Test file not found: {TEST_FILE_PATH}")
    
    # get the file size
    file_size = os.path.getsize(TEST_FILE_PATH)
    logger.info(f"File path: {TEST_FILE_PATH}")
    logger.info(f"File size: {file_size / 1024 / 1024:.2f} MB")
    
    # calculate the MD5 of the file
    test_file_md5 = calculate_file_md5(TEST_FILE_PATH)
    
    # split the file into chunks
    chunks = split_file_to_chunks(TEST_FILE_PATH)
    total_chunks = len(chunks)
    
    db = SessionLocal()
    
    try:
        # upload each chunk
        for chunk_index, chunk_data in enumerate(chunks):
            logger.info(f"Uploading chunk {chunk_index + 1}/{total_chunks} (size: {len(chunk_data) / 1024:.2f} KB)")
            
            # create the request object
            request = ChunkUploadRequest(
                file_md5=test_file_md5,
                chunk_index=chunk_index,
                total_chunks=total_chunks,
                file_name=os.path.basename(TEST_FILE_PATH),
                total_size=file_size
            )
            
            # upload the chunk
            result = upload_chunk_service(
                db=db,
                request=request,
                file_data=chunk_data
            )
            
            logger.info(f"✓ Chunk {chunk_index} uploaded successfully")
        
        logger.info(f"\n✅ All chunks uploaded successfully: {total_chunks} chunks")
        
    finally:
        db.close()


def test_step_2_merge_file_and_send_to_kafka():
    """step 2: merge file and send to Kafka"""
    logger.info("\n" + "=" * 80)
    logger.info("step 2: merge file and send to Kafka")
    logger.info("=" * 80)
    
    db = SessionLocal()
    
    try:
        # 1. merge the file
        logger.info(f"Merging file: {test_file_md5}")
        
        result = merge_file_service(
            db=db,
            file_md5=test_file_md5,
            file_name=os.path.basename(TEST_FILE_PATH)
        )
        
        logger.info(f"✅ File merged successfully")
        logger.info(f"   MinIO path: {result.get('object_url', 'N/A')}")
        logger.info(f"    File size: {result.get('file_size', 0) / 1024:.2f} KB")
        
        # 2. generate the presigned URL for the file
        object_name = result['object_url']
        logger.info(f"object_name: {object_name}")
        logger.info(f"minio_client is None: {minio_client is None}")
        logger.info(f"starts with http: {object_name.startswith('http')}")
        
        if minio_client and not object_name.startswith('http'):
            # generate the presigned URL (valid for 7 days)
            from datetime import timedelta
            logger.info(f"Generating the presigned URL for the file: {object_name}")
            presigned_url = minio_client.presigned_get_object(
                MINIO_BUCKET,
                object_name,
                expires=timedelta(days=7)
            )
            file_url = presigned_url
            logger.info(f"✅ generated the presigned URL successfully")
            logger.info(f"   URL: {file_url[:150]}...")
        else:
            logger.info(f"using the original path: {object_name}")
            file_url = object_name
        
        # 3. send the task to Kafka
        task = FileProcessingTask(
            file_md5=test_file_md5,
            file_path=file_url,
            file_name=os.path.basename(TEST_FILE_PATH)
        )
        
        producer = KafkaConfig.get_producer()
        topic = KafkaConfig.get_file_processing_topic()
        
        logger.info(f"Sending task to Kafka: topic={topic}")
        
        future = producer.send(
            topic,
            key=task.file_md5,
            value=task.to_dict()
        )
        
        record_metadata = future.get(timeout=10)
        
        logger.info(
            f"✅ Kafka message sent successfully: "
            f"partition={record_metadata.partition}, "
            f"offset={record_metadata.offset}"
        )
        
        return result
        
    finally:
        db.close()


def start_consumer_thread():
    """start the Consumer thread"""
    global consumer_running
    
    logger.info("\n" + "=" * 80)
    logger.info("step 3: start the Kafka Consumer")
    logger.info("=" * 80)
    
    # create the service instance
    db = SessionLocal()
    parse_service = ParseService(chunk_size=500)
    
    # create the embedding client
    if not GeminiEmbeddingClient.is_configured():
        raise RuntimeError("GEMINI_API_KEY 未配置")
    embedding_client = GeminiEmbeddingClient()
    
    # create the ES service
    es_client = es.get_client()
    es_service = ElasticsearchService(es_client)
    
    # create the vectorization service
    vectorization_service = VectorizationService(
        embedding_client=embedding_client,
        elasticsearch_service=es_service
    )
    
    # create the consumer
    consumer = FileProcessingConsumer(
        parse_service=parse_service,
        vectorization_service=vectorization_service,
        max_retries=4,
        retry_backoff_seconds=3
    )
    
    consumer_running = True
    
    def consume_messages():
        """consume the messages"""
        logger.info("Consumer is listening to Kafka messages...")
        
        try:
            # only process our test messages
            processed = 0
            max_messages = 10  # maximum number of messages to process
            max_wait_seconds = 30  # maximum wait time in seconds
            
            import time as time_module
            start_time = time_module.time()
            
            for message in consumer.consumer:
                if not consumer_running:
                    break
                
                # check if the timeout is reached
                if time_module.time() - start_time > max_wait_seconds:
                    logger.info("Consumer timeout, exiting")
                    break
                
                logger.info(f"Received Kafka message: file_md5={message.value.get('file_md5', 'N/A')}")
                
                # process the message
                task = FileProcessingTask.from_dict(message.value)
                
                # only process our test file
                if task.file_md5 == test_file_md5:
                    logger.info(f"✓ Found target message, starting to process: {task.file_name}")
                    success = consumer.process_task(task)
                    
                    if success:
                        logger.info(f"✅ Task processed successfully: {task.file_name}")
                    else:
                        logger.error(f"❌ Task processed failed: {task.file_name}")
                    
                    # after processing our message, exit
                    break
                else:
                    logger.info(f"Skipping other messages: {task.file_md5}")
                
                processed += 1
                if processed >= max_messages:
                    logger.info(f"Processed {processed} messages, stopping consumer")
                    break
                    
        except Exception as e:
            logger.error(f"Consumer processing message failed: {e}", exc_info=True)
        finally:
            consumer.close()
            db.close()
    
    # start the thread
    thread = threading.Thread(target=consume_messages, daemon=True)
    thread.start()
    
    logger.info("✓ Consumer thread started")
    
    return thread


def test_step_3_wait_for_processing():
    """step 3: wait for the Kafka Consumer to process"""
    global consumer_thread
    
    # start the consumer
    consumer_thread = start_consumer_thread()
    
    # wait for the processing to complete
    logger.info("\nWaiting for the Consumer to process the task...")
    
    # maximum wait time in seconds
    consumer_thread.join(timeout=60)
    
    if consumer_thread.is_alive():
        logger.warning("Consumer thread is still running, may need more time")
    else:
        logger.info("✅ Consumer processed successfully")


def test_step_4_verify_mysql():
    """step 4: verify the data in MySQL"""
    logger.info("\n" + "=" * 80)
    logger.info("step 4: verify the data in MySQL")
    logger.info("=" * 80)
    
    db = SessionLocal()
    
    try:
        # query the chunks
        chunks = document_vector_repository.find_by_file_md5(db, test_file_md5)
        
        if not chunks:
            raise AssertionError(f"❌ No chunks found in MySQL: {test_file_md5}")
        
        logger.info(f"✅ MySQL verification successful")
        logger.info(f"    Found {len(chunks)} chunks")
        logger.info(f"    Example chunk content: {chunks[0].text_content[:100]}...")
        
        return len(chunks)
        
    finally:
        db.close()


def test_step_5_verify_elasticsearch():
    """step 5: verify the data in Elasticsearch"""
    logger.info("\n" + "=" * 80)
    logger.info("step 5: verify the data in Elasticsearch")
    logger.info("=" * 80)
    
    es_client = es.get_client()
    
    # wait for the ES index to be refreshed
    time.sleep(2)
    
    # query the ES
    resp = es_client.search(
        index=ES_INDEX,
        query={"term": {"file_md5": {"value": test_file_md5}}},
        size=1000
    )
    
    hits = resp["hits"]["hits"]
    
    if not hits:
        raise AssertionError(f"❌ No documents found in Elasticsearch: {test_file_md5}")
    
    logger.info(f"✅ Elasticsearch verification successful")
    logger.info(f"    Found {len(hits)} documents")
    
    # verify the document structure
    doc = hits[0]["_source"]
    logger.info(f"    Document fields: {list(doc.keys())}")
    logger.info(f"    Example text: {doc.get('text_content', '')[:100]}...")
    
    assert "file_md5" in doc
    assert "chunk_id" in doc
    assert "text_content" in doc
    assert "model_version" in doc
    
    return len(hits)


def test_step_6_cleanup():
    """step 6: cleanup the test data"""
    logger.info("\n" + "=" * 80)
    logger.info("step 6: cleanup the test data")
    logger.info("=" * 80)
    
    db = SessionLocal()
    
    try:
        # 1. cleanup the MySQL document vectors
        deleted_chunks = document_vector_repository.delete_by_file_md5(db, test_file_md5)
        logger.info(f"✓ Cleanup MySQL: deleted {deleted_chunks} chunks")
        
        # 2. cleanup the MinIO (optional)
        try:
            if minio_client:
                # delete the merged file (note the path contains the "documents/" prefix)
                object_name = f"documents/{test_file_md5}/{os.path.basename(TEST_FILE_PATH)}"
                minio_client.remove_object(MINIO_BUCKET, object_name)
                logger.info(f"✓ Cleanup MinIO merged file: {object_name}")
        except Exception as e:
            logger.warning(f"MinIO merged file cleanup failed: {e}")
        
        # 5. cleanup the MinIO chunks
        try:
            if minio_client:
                # delete all chunks
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
                    logger.info(f"✓ Cleanup MinIO chunks: deleted {deleted_count} chunks")
                else:
                    logger.info("✓ Cleanup MinIO chunks: no need to cleanup")
        except Exception as e:
            logger.warning(f"MinIO chunks cleanup failed: {e}")
        
        # 6. cleanup the Elasticsearch
        es_client = es.get_client()
        result = es_client.delete_by_query(
            index=ES_INDEX,
            query={"term": {"file_md5": {"value": test_file_md5}}}
        )
        logger.info(f"✓ Cleanup Elasticsearch: deleted {result.get('deleted', 0)} documents")
        
        logger.info("✅ All test data cleaned")
        
    finally:
        db.close()


def run_full_integration_test():
    """run the full integration test"""
    global consumer_running
    
    logger.info("\n")
    logger.info("=" * 80)
    logger.info("🚀 Full file upload integration test")
    logger.info("=" * 80)
    logger.info(f"Test file: {TEST_FILE_PATH}")
    logger.info("=" * 80)
    
    start_time = time.time()
    
    try:
        # step 1: upload chunks
        test_step_1_upload_chunks()
        
        # step 2: merge file and send to Kafka
        merge_result = test_step_2_merge_file_and_send_to_kafka()
        
        # step 3: start the Consumer and wait for the processing
        test_step_3_wait_for_processing()
        
        # give some time for the processing to complete
        time.sleep(5)
        
        # step 4: verify the data in MySQL
        chunk_count = test_step_4_verify_mysql()
        
        # step 5: verify the data in Elasticsearch
        es_doc_count = test_step_5_verify_elasticsearch()
        
        # verify the consistency of the counts
        if chunk_count != es_doc_count:
            logger.warning(
                f"⚠️ Warning: MySQL chunks ({chunk_count}) and ES documents ({es_doc_count}) are not consistent"
            )
        
        elapsed_time = time.time() - start_time
        
        logger.info("\n" + "=" * 80)
        logger.info("🎉 All integration tests passed!")
        logger.info("=" * 80)
        logger.info(f"✓ File MD5: {test_file_md5}")
        logger.info(f"✓ MySQL chunks: {chunk_count}")
        logger.info(f"✓ ES documents: {es_doc_count}")
        logger.info(f"✓ Total time: {elapsed_time:.2f} seconds")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"\n❌ Integration test failed: {e}", exc_info=True)
        raise
        
    finally:
        # stop the consumer
        consumer_running = False
        
        # cleanup the test data
        if test_file_md5:
            try:
                test_step_6_cleanup()
            except Exception as e:
                logger.error(f"Cleanup test data failed: {e}")


if __name__ == "__main__":
    run_full_integration_test()

