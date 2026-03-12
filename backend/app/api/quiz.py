import json
import re
from fastapi import APIRouter, HTTPException

from app.clients.gpt_client import GPTClient
from app.schemas.quiz import QuizGenerateRequest, QuizGenerateResponse
from app.utils.logging import get_logger


router = APIRouter(prefix="/quiz", tags=["quiz"])
logger = get_logger(__name__)
gpt_client = GPTClient()


def _format_chunks(chunks: list[str]) -> str:
    formatted = []
    for i, c in enumerate(chunks, 1):
        text = (c or "").strip()
        if text:
            formatted.append(f"[Chunk {i}]\n{text}")
    return "\n\n".join(formatted)


def _extract_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model response does not contain a valid JSON object.")
    return json.loads(raw[start:end + 1])


@router.post("/generate", response_model=QuizGenerateResponse)
async def generate_quiz(request: QuizGenerateRequest):
    try:
        chunks_text = _format_chunks(request.retrieved_chunks)
        if not chunks_text:
            raise HTTPException(status_code=400, detail="retrieved_chunks must include non-empty text.")

        prompt = f"""You are an intelligent assessment engine.

Your task is to generate a knowledge-testing quiz strictly based on the provided context.
Do NOT use external knowledge.
Do NOT hallucinate information not present in the context.

CONTEXT:
{chunks_text}

USER PROFILE:
- Topic: {request.topic}
- Difficulty Level: {request.difficulty}
- Number of Questions: {request.number_of_questions}
- Question Types: MCQ only
- Bloom's Level: {request.bloom_level}

INSTRUCTIONS:
1. Generate conceptual questions, not copy-paste factual recall.
2. Ensure answers are fully supported by the context.
3. Increase reasoning complexity if difficulty is "hard".
4. Avoid ambiguous wording.
5. Do not mention the word "context" in output.

Return output strictly in the following JSON format:

{{
  "quiz_title": "",
  "difficulty": "",
  "questions": [
    {{
      "type": "MCQ",
      "question": "",
      "options": ["A", "B", "C", "D"],
      "correct_answer": "",
      "explanation": ""
    }}
  ]
}}

Output only valid JSON. No markdown. No extra text."""

        response_text = gpt_client.generate(
            messages=[
                {"role": "system", "content": "You generate strict JSON outputs only."},
                {"role": "user", "content": prompt},
            ]
        )
        parsed = _extract_json_object(response_text)
        quiz = QuizGenerateResponse.model_validate(parsed)

        if len(quiz.questions) != request.number_of_questions:
            raise HTTPException(
                status_code=500,
                detail=f"Model returned {len(quiz.questions)} questions, expected {request.number_of_questions}."
            )
        if any(q.type != "MCQ" for q in quiz.questions):
            raise HTTPException(
                status_code=500,
                detail="Model returned non-MCQ questions; expected MCQ-only quiz."
            )

        return quiz
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Quiz generation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Quiz generation failed: {str(e)}")
