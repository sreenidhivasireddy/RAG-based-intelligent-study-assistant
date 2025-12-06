"""
Conversation repository - handles database operations for conversations.

This module provides CRUD operations for DocumentVector model
"""

from typing import List, datetime
from sqlalchemy.orm import Session
from app.models.conversation import Conversation
from app.utils.logging import get_logger

logger = get_logger(__name__)

def create_coversation(db: Session, question:str, answer:str) -> Conversation:
    conversation = Conversation(question,answer)

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    logger.debug(f"Created conversation: question={question}, answer={answer}")

    return conversation

def get_by_timestamp_between(db: Session, start_time: datetime, end_time: datetime) -> List[Conversation]:
    return db.query(Conversation).filter(Conversation.created_at >= start_time, Conversation.created_at <= end_time).all()


