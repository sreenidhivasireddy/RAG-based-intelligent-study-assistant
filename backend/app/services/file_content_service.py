"""
File content retrieval service.
Provides direct file reading capability as a fallback when search-based retrieval fails.

This service reads uploaded files directly from storage and extracts content,
allowing the agent to access file content even if indexing hasn't completed.
"""

import logging
from typing import List, Optional, Dict, Tuple
from io import BytesIO
from sqlalchemy.orm import Session
from pypdf import PdfReader

from app.storage.azure_blob import azure_blob_client, AZURE_STORAGE_CONTAINER
from app.services.parse_service import ParseService
from app.repositories.upload_repository import get_file_upload
from app.models.document_vector import DocumentVector
from app.database import SessionLocal

logger = logging.getLogger(__name__)


class FileContentService:
    """
    Service for retrieving file content directly from storage.
    Used as fallback when search-based retrieval fails or returns no results.
    """
    
    def __init__(self, parse_service: ParseService = None):
        """
        Initialize file content service.
        
        Args:
            parse_service: Optional parse service instance. If not provided, creates a new one.
        """
        self.parse_service = parse_service or ParseService()
        self.storage_client = azure_blob_client
        logger.info("FileContentService initialized")
    
    def get_file_content_by_md5(self, file_md5: str, db: Session) -> Optional[str]:
        """
        Retrieve complete file content by file MD5 hash.
        
        Priority:
        1. Check database for parsed chunks (fastest)
        2. Download and parse file from storage (if not indexed)
        
        Args:
            file_md5: MD5 hash of the file
            db: Database session
            
        Returns:
            Complete file content as string, or None if file not found
        """
        try:
            # Step 1: Try to get from database chunks (if already parsed)
            logger.info(f"Attempting to retrieve file content for MD5: {file_md5}")
            
            chunks = db.query(DocumentVector).filter(
                DocumentVector.file_md5 == file_md5
            ).order_by(DocumentVector.chunk_id).all()
            
            if chunks and len(chunks) > 0:
                logger.info(f"Found {len(chunks)} chunks in database for file {file_md5}")
                content = self._combine_chunks(chunks)
                return content
            
            # Step 2: File not in database, download and parse from storage
            logger.info(f"No chunks in database, attempting to download and parse file {file_md5}")
            
            file_record = get_file_upload(db, file_md5)
            if not file_record:
                logger.warning(f"File record not found for MD5: {file_md5}")
                return None
            
            file_content = self._download_and_parse_file(file_md5, file_record.file_name)
            return file_content
            
        except Exception as e:
            logger.error(f"Error retrieving file content for {file_md5}: {e}", exc_info=True)
            return None
    
    def get_file_content_by_filename(self, file_name: str, db: Session) -> Optional[str]:
        """
        Retrieve file content by filename.
        
        Args:
            file_name: Name of the file
            db: Database session
            
        Returns:
            File content as string, or None if not found
        """
        try:
            # First, find the file MD5 by name. The repository may not expose a direct
            # get-by-name helper, so query recent uploads and match by name or base name.
            from app.repositories.upload_repository import get_all_file_uploads

            uploads = get_all_file_uploads(db=db, skip=0, limit=1000)
            file_record = None
            target_lower = (file_name or "").strip().lower()
            for u in uploads:
                if not u or not getattr(u, 'file_name', None):
                    continue
                name = u.file_name.strip()
                name_lower = name.lower()
                base_lower = name_lower.rsplit('.', 1)[0]
                if name_lower == target_lower or base_lower == target_lower or target_lower in name_lower:
                    file_record = u
                    break

            if not file_record:
                logger.warning(f"File not found: {file_name}")
                return None

            return self.get_file_content_by_md5(file_record.file_md5, db)

        except Exception as e:
            logger.error(f"Error retrieving file by name {file_name}: {e}", exc_info=True)
            return None
    
    def get_file_snippets(self, file_md5: str, db: Session, max_snippets: int = 5) -> List[Dict[str, str]]:
        """
        Retrieve snippets (chunks) from a specific file.
        Useful for providing context when search returns no results.
        
        Args:
            file_md5: File MD5 hash
            db: Database session
            max_snippets: Maximum number of snippets to return
            
        Returns:
            List of snippet dictionaries with 'content' and 'chunk_id' keys
        """
        try:
            chunks = db.query(DocumentVector).filter(
                DocumentVector.file_md5 == file_md5
            ).order_by(DocumentVector.chunk_id).limit(max_snippets).all()
            
            if not chunks:
                logger.warning(f"No chunks found for file {file_md5}")
                return []
            
            snippets = [
                {
                    "chunk_id": chunk.chunk_id,
                    "content": chunk.text_content,
                    "file_md5": chunk.file_md5
                }
                for chunk in chunks
            ]
            
            logger.info(f"Retrieved {len(snippets)} snippets for file {file_md5}")
            return snippets
            
        except Exception as e:
            logger.error(f"Error retrieving file snippets for {file_md5}: {e}", exc_info=True)
            return []
    
    def search_within_file(self, file_md5: str, keyword: str, db: Session) -> List[Dict[str, str]]:
        """
        Search for keyword within a specific file's content.
        Useful when search index fails or is incomplete.
        
        Args:
            file_md5: File MD5 hash
            keyword: Search keyword
            db: Database session
            
        Returns:
            List of matching chunks with content and metadata
        """
        try:
            chunks = db.query(DocumentVector).filter(
                DocumentVector.file_md5 == file_md5
            ).order_by(DocumentVector.chunk_id).all()
            
            if not chunks:
                logger.warning(f"No chunks found for file {file_md5}")
                return []
            
            keyword_lower = keyword.lower()
            matching_chunks = [
                {
                    "chunk_id": chunk.chunk_id,
                    "content": chunk.text_content,
                    "file_md5": chunk.file_md5
                }
                for chunk in chunks
                if keyword in chunk.text_content or keyword_lower in chunk.text_content.lower()
            ]
            
            logger.info(f"Found {len(matching_chunks)} matching chunks for '{keyword}' in file {file_md5}")
            return matching_chunks
            
        except Exception as e:
            logger.error(f"Error searching within file {file_md5}: {e}", exc_info=True)
            return []
    
    # ============= Private Methods =============
    
    def _combine_chunks(self, chunks: List[DocumentVector]) -> str:
        """
        Combine multiple document vector chunks into a single document.
        
        Args:
            chunks: List of DocumentVector objects
            
        Returns:
            Combined text content
        """
        contents = []
        for chunk in chunks:
            if hasattr(chunk, 'text_content') and chunk.text_content:
                contents.append(chunk.text_content)
        
        return "\n".join(contents)
    
    def _download_and_parse_file(self, file_md5: str, file_name: str) -> Optional[str]:
        """
        Download file from storage and parse its content.
        
        Args:
            file_md5: File MD5 hash
            file_name: Original filename
            
        Returns:
            Parsed file content as string
        """
        try:
            # Construct storage path
            file_path = f"documents/{file_md5}/{file_name}"
            
            logger.info(f"Downloading file from storage: {file_path}")
            
            # Download file content
            file_stream = self._download_from_storage(file_path)
            if not file_stream:
                logger.error(f"Failed to download file: {file_path}")
                return None
            
            # Extract text from file
            logger.info(f"Parsing file content for: {file_name}")
            
            content_parts = []
            try:
                iterator = self.parse_service.get_iterator(file_name, file_stream)
                for block in iterator:
                    content_parts.append(block)
            except Exception as e:
                logger.warning(f"Error iterating file content: {e}")
                content_parts = []

            content = "".join(content_parts)

            # PDFs can sometimes return empty/near-empty text in the first pass.
            # Try a best-effort fallback extraction before giving up.
            if file_name.lower().endswith(".pdf") and len((content or "").strip()) < 80:
                logger.warning(
                    f"Primary PDF extraction returned sparse content for {file_name}. "
                    "Trying fallback extraction mode..."
                )
                try:
                    file_stream.seek(0)
                    fallback_pdf_text = self._extract_pdf_text_fallback(file_stream)
                    if fallback_pdf_text and len(fallback_pdf_text.strip()) > len((content or "").strip()):
                        content = fallback_pdf_text
                except Exception as e:
                    logger.warning(f"Fallback PDF extraction failed for {file_name}: {e}")

            logger.info(f"Successfully extracted {len(content)} characters from file {file_md5}")
            return content
            
        except Exception as e:
            logger.error(f"Error downloading and parsing file {file_md5}: {e}", exc_info=True)
            return None

    def _extract_pdf_text_fallback(self, file_stream: BytesIO) -> str:
        """
        Best-effort PDF text extraction:
        1) Standard extraction per page
        2) Layout-mode extraction when available
        Keeps text mostly raw to avoid over-cleaning encoded glyphs.
        """
        reader = PdfReader(file_stream)
        pages = []

        for page in reader.pages:
            text = page.extract_text() or ""
            if not text:
                try:
                    text = page.extract_text(extraction_mode="layout") or ""
                except TypeError:
                    # Older pypdf versions may not support extraction_mode
                    pass
            if text:
                pages.append(text)

        merged = "\n\n".join(pages)
        # Minimal cleanup only
        merged = merged.replace("\x00", "")
        return merged
    
    def _download_from_storage(self, file_path: str) -> Optional[BytesIO]:
        """
        Download file from Azure Blob Storage.
        
        Args:
            file_path: Path to file in storage (e.g., 'documents/md5/filename.pdf')
            
        Returns:
            BytesIO stream of file content, or None if download fails
        """
        try:
            logger.info(f"Downloading from Azure Blob Storage: {file_path}")
            
            blob_data = self.storage_client.download_bytes(file_path)
            
            if blob_data:
                logger.info(f"Successfully downloaded file: {file_path}")
                return BytesIO(blob_data)
            else:
                logger.warning(f"Blob returned None: {file_path}")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading from storage {file_path}: {e}", exc_info=True)
            return None
