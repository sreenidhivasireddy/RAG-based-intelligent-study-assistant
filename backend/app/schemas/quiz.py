from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


DifficultyLevel = Literal["easy", "medium", "hard"]
BloomLevel = Literal["understand", "apply", "analyze"]
QuestionType = Literal["MCQ"]


class QuizGenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200)
    difficulty: DifficultyLevel
    number_of_questions: int = Field(..., ge=1, le=20)
    bloom_level: BloomLevel
    retrieved_chunks: List[str] = Field(..., min_length=1)


class QuizQuestion(BaseModel):
    type: QuestionType
    question: str = Field(..., min_length=1)

    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    explanation: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_mcq_fields(self):
        if not self.options or len(self.options) != 4:
            raise ValueError("MCQ requires exactly 4 options.")
        if not self.correct_answer:
            raise ValueError("MCQ requires correct_answer.")
        return self


class QuizGenerateResponse(BaseModel):
    quiz_title: str = Field(..., min_length=1)
    difficulty: DifficultyLevel
    questions: List[QuizQuestion] = Field(..., min_length=1)
