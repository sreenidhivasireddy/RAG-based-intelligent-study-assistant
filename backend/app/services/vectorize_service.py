"""
Vectorization service class
Corresponding to Java's VectorizationService.java
"""
import logging
from typing import List
from sqlalchemy.orm import Session
import numpy as np

from app.clients.azure_openai_embedding_client import AzureOpenAIEmbeddingClient
from app.services.azure_search_service import AzureSearchService
from app.models.es_document import EsDocument
from app.models.text_chunk import TextChunk
from app.repositories import document_vector_repository

logger = logging.getLogger(__name__)


class VectorizationService:
    """Vectorization service"""

    def __init__(
        self,
        embedding_client: AzureOpenAIEmbeddingClient,
        search_service: AzureSearchService,   # ✅ rename
    ):
        self.embedding_client = embedding_client
        self.search_service = search_service  # ✅ rename

    def vectorize(self, file_md5: str, db: Session) -> None:
        try:
            print("DEBUG: USING VECTORIZE VERSION WITH BULK INDEX")

            # 1) Fetch chunks
            chunks = self._fetch_text_chunks(file_md5, db)
            if not chunks:
                logger.warning(f"No chunks found for fileMd5: {file_md5}")
                return

            # 2) Deduplicate by chunk_id
            unique = {}
            for c in chunks:
                if str(c.chunk_id) not in unique:
                    unique[str(c.chunk_id)] = c
            chunks = list(unique.values())

            logger.info(f"Chunks after dedupe: {len(chunks)}")

            # ✅ IMPORTANT CHANGE:
            # DO NOT delete_by_file_md5 (your Azure index doesn't have fileMd5 filter field)
            # Make indexing idempotent via deterministic IDs instead.

            texts = [c.content for c in chunks]

            logger.info(f"Calling embedding model to generate vectors, text count: {len(texts)}")
            vectors = self.embedding_client.embed(texts)

            # Guardrail: verify embedding dimension matches expected dimension
            import os
            expected_dim = int(os.getenv("AZURE_EMBEDDING_DIM", "1536"))
            if vectors and hasattr(vectors[0], '__len__'):
                got_dim = len(vectors[0])
                if got_dim != expected_dim:
                    logger.error(f"Embedding dimension mismatch: expected={expected_dim}, got={got_dim}")
                    raise RuntimeError(f"Embedding dimension mismatch: expected={expected_dim}, got={got_dim}")

            # Debug vector structure
            print("DEBUG: embed() return type =", type(vectors))
            print("DEBUG: embed() length =", len(vectors) if hasattr(vectors, "__len__") else "no len")
            for i, v in enumerate(vectors[:3]):
                print(f"  vector[{i}] type = {type(v)}")
                try:
                    print(f"  vector[{i}] len  = {len(v) if hasattr(v, '__len__') else 'no len'}")
                    arr = np.array(v)
                    print(f"  vector[{i}] numpy.shape = {arr.shape}")
                except Exception as e:
                    print(f"  vector[{i}] numpy conversion failed: {e}")

            if len(vectors) != len(chunks):
                raise RuntimeError(f"Embedding count mismatch: vectors={len(vectors)} chunks={len(chunks)}")

            # 4) Fetch file metadata for enriching documents
            file_name = "unknown"
            chunk_index_map = {}  # map chunk_id to chunk_index
            
            # Try to get file_name from FileUpload table
            try:
                from app.models.file_upload import FileUpload
                file_rec = db.query(FileUpload).filter(FileUpload.file_md5 == file_md5).first()
                if file_rec:
                    file_name = file_rec.file_name
                logger.info(f"Retrieved file_name: {file_name}")
            except Exception as e:
                logger.warning(f"Could not fetch file_name from DB, using default: {e}")
            
            # Try to get chunk_index from ChunkInfo table
            try:
                from app.models.chunk import ChunkInfo
                chunk_infos = db.query(ChunkInfo).filter(ChunkInfo.file_md5 == file_md5).all()
                for chunk_info in chunk_infos:
                    chunk_index_map[chunk_info.chunk_md5] = chunk_info.chunk_index
                logger.info(f"Retrieved chunk_index mappings: {len(chunk_index_map)} chunks")
            except Exception as e:
                logger.warning(f"Could not fetch chunk_index from DB: {e}")
            
            # 4) Build docs with deterministic IDs (idempotent upsert)
            docs: List[EsDocument] = []
            for chunk, vector in zip(chunks, vectors):
                chunk_id = str(chunk.chunk_id)

                # ✅ deterministic ID => retries overwrite, no duplicates
                doc_id = f"{file_md5}_{chunk_id}"
                
                # Get chunk_index if available
                chunk_index = chunk_index_map.get(chunk.chunk_id)

                docs.append(
                    EsDocument(
                        id=doc_id,
                        file_md5=file_md5,
                        chunk_id=chunk_id,
                        content=chunk.content,
                        embedding=vector.tolist() if hasattr(vector, "tolist") else vector,
                        file_name=file_name,
                        chunk_index=chunk_index,
                    )
                )

            # 5) Bulk upsert into Azure AI Search
            self.search_service.bulk_index(docs)

            logger.info(f"Vectorization completed, fileMd5: {file_md5}")

        except Exception as e:
            logger.error(f"Vectorization failed, fileMd5: {file_md5}", exc_info=True)
            raise RuntimeError(f"Vectorization failed: {str(e)}") from e

    def _fetch_text_chunks(self, file_md5: str, db: Session) -> List[TextChunk]:
        vectors = document_vector_repository.find_by_file_md5(db, file_md5)
        return [TextChunk(chunk_id=v.chunk_id, content=v.text_content) for v in vectors]
