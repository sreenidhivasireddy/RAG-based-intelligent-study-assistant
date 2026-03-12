from dataclasses import dataclass
from typing import List
import numpy as np

@dataclass
class EsDocument:
    """Azure Search document entity class (formerly Elasticsearch)"""
    id: str
    file_md5: str
    chunk_id: str
    content: str  # matches Azure schema
    embedding: List[float]  # matches Azure schema (formerly 'vector')
    file_name: str = None  # optional, for Azure schema
    chunk_index: int = None  # optional, for Azure schema
    
    def to_dict(self):
        """Convert to dictionary for Azure Search storage"""
        doc = {
            'id': self.id,
            'file_md5': self.file_md5,
            'chunk_id': self.chunk_id,
            'content': self.content,
            'embedding': self.embedding,
        }
        if self.file_name:
            doc['file_name'] = self.file_name
        if self.chunk_index is not None:
            doc['chunk_index'] = self.chunk_index
        return doc

    # Backwards-compatible alias used by ElasticsearchService
    def to_es_dict(self):
        return self.to_dict()