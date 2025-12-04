"""
File processing task data model.
Corresponds to Java's FileProcessingTask.java
"""
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class FileProcessingTask:
    """
    文件处理任务类，用于Kafka消息传递
    
    Attributes:
        file_md5: 文件的 MD5 校验值
        file_path: 文件存储路径/URL
        file_name: 文件名
    """
    file_md5: str
    file_path: str
    file_name: str
    
    def to_dict(self) -> dict:
        """
        转换为字典，用于Kafka JSON序列化
        """
        return {
            'file_md5': self.file_md5,
            'file_path': self.file_path,
            'file_name': self.file_name
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'FileProcessingTask':
        """
        从字典创建对象，用于Kafka消息反序列化
        兼容驼峰和下划线命名
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