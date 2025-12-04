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
            'file_md5': self.file_md5,
            'chunk_id': self.chunk_id,
            'text_content': self.text_content,
            'vector': self.vector,
            'model_version': self.model_version
        }

    # Backwards-compatible alias used by ElasticsearchService
    def to_es_dict(self):
        return self.to_dict()