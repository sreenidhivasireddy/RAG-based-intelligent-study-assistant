"""
Gemini Embedding API 客户端
对应 Java 的 EmbeddingClient.java
"""
import logging
import time
from typing import List
import numpy as np
import google.generativeai as genai

logger = logging.getLogger(__name__)

import os
api_key = os.getenv("GEMINI_API_KEY")
model_name_env = os.getenv("GEMINI_MODEL_NAME", "models/embedding-001")
batch_size_env = int(os.getenv("GEMINI_BATCH_SIZE", "100"))

# Configure Gemini API
if api_key:
    genai.configure(api_key=api_key)
    logger.info("Gemini API key configured successfully")
else:
    logger.warning("GEMINI_API_KEY environment variable not found")


class GeminiEmbeddingClient:
    """Gemini embedding vector generation client"""
    
    def __init__(
        self, 
        model_name: str = None,
        batch_size: int = None,
        max_retries: int = 3
    ):
        """
        Initialize Gemini client
        
        Args:
            model_name: model name, default from GEMINI_MODEL_NAME environment variable
            batch_size: batch size, default from GEMINI_BATCH_SIZE environment variable
            max_retries: maximum number of retries
        """
        # Use passed parameters if provided, otherwise use environment variables
        self.model_name = model_name if model_name is not None else model_name_env
        self.batch_size = batch_size if batch_size is not None else batch_size_env
        self.max_retries = max_retries
        
        logger.info(f"Initialized Gemini Embedding Client, model: {self.model_name}, batch size: {self.batch_size}")
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Call Gemini API to generate vectors
        
        Args:
            texts: input text list
            
        Returns:
            List of corresponding vectors
            
        Raises:
            RuntimeError: Raised when API call fails
        """
        try:
            logger.info(f"Generating vectors, text count: {len(texts)}")
            
            all_vectors = []
            
            # Batch processing
            for start in range(0, len(texts), self.batch_size):
                end = min(start + self.batch_size, len(texts))
                batch = texts[start:end]
                
                logger.debug(
                    f"Calling vector API, batch: {start}-{end-1} (size={len(batch)})"
                )
                
                # Call API (with retry)
                batch_vectors = self._call_api_with_retry(batch)
                all_vectors.extend(batch_vectors)
            
            logger.info(f"Successfully generated vectors, total count: {len(all_vectors)}")
            return all_vectors
            
        except Exception as e:
            logger.error(f"Calling vectorization API failed: {e}", exc_info=True)
            raise RuntimeError(f"Vector generation failed: {str(e)}") from e
    
    def _call_api_with_retry(self, texts: List[str]) -> List[List[float]]:
        """
        API call with retry
        
        Args:
            texts: text list
            
        Returns:
            List of vectors
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                # Call Gemini API
                result = genai.embed_content(
                    model=self.model_name,
                    content=texts,
                    task_type="retrieval_document"  # For document retrieval
                )
                
                # Extract vectors
                vectors = result['embedding']
                
                # If it's a single text, wrap it in a list
                if isinstance(texts, str):
                    vectors = [vectors]
                
                return vectors
                
            except Exception as e:
                last_error = e
                logger.warning(
                    f"API call failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                
                if attempt < self.max_retries - 1:
                    time.sleep(1)  # Wait for 1 second before retrying
                    continue
        
        # All retries failed
        raise RuntimeError(f"API call failed, tried {self.max_retries} times") from last_error