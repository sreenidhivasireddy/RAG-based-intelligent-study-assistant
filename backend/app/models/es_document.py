from dataclasses import dataclass
from typing import List
import numpy as np

@dataclass
class EsDocument:
    """Elasticsearch document entity class"""
    id: str
    file_md5: str
    chunk_id: int
    text_content: str
    vector: List[float]  # or np.ndarray
    model_version: str
    
    def to_dict(self):
        """Convert to dictionary for Elasticsearch storage"""
        return {
            'fileMd5': self.file_md5,
            'chunkId': self.chunk_id,
            'textContent': self.text_content,
            'vector': self.vector,
            'modelVersion': self.model_version
        }