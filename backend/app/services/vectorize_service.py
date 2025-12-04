"""
Vectorization service class
Corresponding to Java's VectorizationService.java
"""
import logging
import uuid
from typing import List
from sqlalchemy.orm import Session
import numpy as np

from app.clients.gemini_embedding_client import GeminiEmbeddingClient
from app.services.es_service import ElasticsearchService
from app.models.es_document import EsDocument
from app.models.text_chunk import TextChunk
from app.repositories import document_vector_repository

logger = logging.getLogger(__name__)


class VectorizationService:
    """Vectorization service"""
    
    def __init__(
        self,
        embedding_client: GeminiEmbeddingClient,
        elasticsearch_service: ElasticsearchService,
        db: Session
    ):
        self.embedding_client = embedding_client
        self.elasticsearch_service = elasticsearch_service
        self.db = db
    
    def vectorize(
        self, 
        file_md5: str
    ) -> None:
        """
        Execute vectorization operation
        
        Args:
            file_md5: file fingerprint
            
        Raises:
            RuntimeError: Raised when vectorization fails
        """
        try:
            print("DEBUG: USING VECTORIZE VERSION WITH BULK INDEX")
            # 1. Get file chunks
            chunks = self._fetch_text_chunks(file_md5)
            if not chunks:
                logger.warning(f"No chunks found for fileMd5: {file_md5}")
                return
            
            # 2. Extract text content
            texts = [chunk.content for chunk in chunks]
            
            # 3. Call Gemini model to generate vectors
            logger.info(f"Calling Gemini model to generate vectors, text count: {len(texts)}")
            vectors = self.embedding_client.embed(texts)

            # ==== DEBUG 向量结构 ====
            print("DEBUG: embed() 返回类型 =", type(vectors))
            print("DEBUG: embed() 长度 =", len(vectors) if hasattr(vectors, "__len__") else "no len")

            for i, v in enumerate(vectors[:3]):
                print(f"  vector[{i}] type = {type(v)}")
                try:
                    print(f"  vector[{i}] len  = {len(v) if hasattr(v, '__len__') else 'no len'}")
                    arr = np.array(v)
                    print(f"  vector[{i}] numpy.shape = {arr.shape}")
                except Exception as e:
                    print(f"  vector[{i}] 转 numpy 失败: {e}")
            # ==== DEBUG END ====
            
            # 4. Build Elasticsearch documents and store
            es_documents = [
                EsDocument(
                    id=str(uuid.uuid4()),
                    file_md5=file_md5,
                    chunk_id=chunk.chunk_id,
                    text_content=chunk.content,
                    vector=vector.tolist() if hasattr(vector, 'tolist') else vector,
                    model_version="gemini-embedding-001"
                )
                for chunk, vector in zip(chunks, vectors)
            ]
            
            # 5. Bulk store to Elasticsearch
            self.elasticsearch_service.bulk_index(es_documents)

            
            logger.info(f"Vectorization completed, fileMd5: {file_md5}")
            
        except Exception as e:
            logger.error(f"Vectorization failed, fileMd5: {file_md5}", exc_info=True)
            raise RuntimeError(f"Vectorization failed: {str(e)}") from e
    
    def _fetch_text_chunks(self, file_md5: str) -> List[TextChunk]:
        """
        Get file chunks from database
        
        Args:
            file_md5: file fingerprint
            
        Returns:
            List of text chunks
        """
        # Call Repository to query data
        vectors = document_vector_repository.find_by_file_md5(self.db, file_md5)
        
        # Convert to TextChunk list
        return [
            TextChunk(
                chunk_id=vector.chunk_id,
                content=vector.text_content
            )
            for vector in vectors
        ]