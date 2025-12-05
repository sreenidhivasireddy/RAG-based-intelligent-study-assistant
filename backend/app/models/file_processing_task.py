"""
File processing task data model.
Corresponds to Java's FileProcessingTask.java
"""
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class FileProcessingTask:
    """
    wrapper class for the file processing task
    
    Attributes:
        file_md5: the MD5 hash of the file
        file_path: the path of the file
        file_name: the name of the file
    """
    file_md5: str
    file_path: str
    file_name: str
    
    def to_dict(self) -> dict:
        """
        convert the task to a dictionary
        """
        return {
            'file_md5': self.file_md5,
            'file_path': self.file_path,
            'file_name': self.file_name
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'FileProcessingTask':
        """
        create the task from a dictionary
        """
        return cls(
            file_md5=data.get('file_md5') or data.get('file_md5', ''),
            file_path=data.get('file_path') or data.get('file_path', ''),
            file_name=data.get('file_name') or data.get('file_name', '')
        )
    
    def __str__(self) -> str:
        return (
            f"FileProcessingTask(file_md5={self.file_md5}, "
            f"file_name={self.file_name})"
        )