"""
Conversation service - handles the conversation history and management.
currently focus on question-answer and create timestamp only.
"""

from typing import List, Optional, datetime
from app.repositories.conversation_repository import ConversationRepository
from app.models.conversation import Conversation

class ConversationService:
    """
    Conversation service - handles the conversation history and management.
    """

    def __init__(self,  conversation_repo: ConversationRepository):
        self.repository = conversation_repo

    def record_conversation(self, question: str, answer: str) -> Conversation:
        conv = Conversation(question=question, answer=answer)
        return self.repository.save(conv)

    def get_conversations(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Conversation]:
        return self.repository.find_all(start_date, end_date)


