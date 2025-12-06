"""
Massage-related Data Transfer Objects (DTOs).
use dataclass to define the schemas for the messages.
"""

from dataclasses import dataclass

@dataclass
class Message:
    role: str
    content: str