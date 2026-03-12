import json
import math
import threading
import time
from typing import Any, Dict, List, Optional

from app.clients.azure_openai_embedding_client import AzureOpenAIEmbeddingClient
from app.clients.gpt_client import GPTClient
from app.database import SessionLocal, ensure_tables
from app.repositories.document_vector_repository import find_by_file_md5
from app.repositories.upload_repository import get_file_upload, get_file_uploads_with_vectors
from app.repositories.synthetic_eval_repository import (
    create_many_synthetic_eval_rows,
    delete_synthetic_eval_rows_by_document_id,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


PROMPT_TEMPLATE = """
You are an expert question generator. Given the following text chunk,
generate exactly 3 diverse questions that can be answered strictly from the text.

The 3 questions must cover these types when possible:
- 1 factual question
- 1 inferential question
- 1 comparative question

For each question, also provide the exact answer from the text.

Return ONLY valid JSON in this format, no preamble, no markdown:
{
  "qa_pairs": [
    {"question": "...", "answer": "...", "chunk_id": "<chunk_id>"},
    ...
  ]
}

Text chunk:
<chunk_text>
""".strip()


def _safe_json_parse(content: str) -> Optional[Dict[str, Any]]:
    if not content:
        return None
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(content[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _sample_chunks(chunks: List[Any], max_direct: int = 20, target_min: int = 15, target_max: int = 20) -> List[Any]:
    total = len(chunks)
    if total <= max_direct:
        return chunks

    step = max(1, math.ceil(total / target_max))
    sampled = chunks[::step]
    if len(sampled) < target_min and step > 1:
        sampled = chunks[:: (step - 1)]
    if len(sampled) > target_max:
        sampled = sampled[:target_max]
    return sampled


def _build_prompt(chunk_text: str) -> str:
    return PROMPT_TEMPLATE.replace("<chunk_text>", chunk_text or "")


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _deduplicate_rows_by_similarity(
    rows: List[Dict[str, str]],
    similarity_threshold: float = 0.85,
) -> List[Dict[str, str]]:
    if len(rows) < 2:
        return rows

    questions = [row["question"] for row in rows if row.get("question")]
    if len(questions) != len(rows):
        rows = [row for row in rows if row.get("question")]
        if len(rows) < 2:
            return rows
        questions = [row["question"] for row in rows]

    try:
        embedding_client = AzureOpenAIEmbeddingClient()
        embeddings = embedding_client.embed(questions)
    except Exception as e:
        logger.warning("Synthetic eval deduplication fallback to exact-text dedupe: %s", e)
        seen: set[str] = set()
        deduped_rows: List[Dict[str, str]] = []
        for row in rows:
            key = row["question"].strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped_rows.append(row)
        return deduped_rows

    kept_rows: List[Dict[str, str]] = []
    kept_embeddings: List[List[float]] = []
    for row, embedding in zip(rows, embeddings):
        if any(_cosine_similarity(embedding, existing) > similarity_threshold for existing in kept_embeddings):
            continue
        kept_rows.append(row)
        kept_embeddings.append(embedding)

    logger.info(
        "Synthetic eval deduplication completed rows_before=%d rows_after=%d threshold=%.2f",
        len(rows),
        len(kept_rows),
        similarity_threshold,
    )
    return kept_rows


def generate_synthetic_eval_for_document(
    document_id: str,
    pipeline_version: Optional[str] = None,
    replace_existing: bool = False,
    delay_seconds: float = 0.5,
) -> int:
    ensure_tables()

    db = SessionLocal()
    try:
        file_record = get_file_upload(db, document_id)
        if not file_record:
            logger.warning(
                "Synthetic eval generation skipped: file_upload row not found for document_id=%s",
                document_id,
            )
            return 0

        if replace_existing:
            deleted = delete_synthetic_eval_rows_by_document_id(db, document_id=document_id)
            logger.info(
                "Synthetic eval generation: deleted old rows for document_id=%s count=%d",
                document_id,
                deleted,
            )

        chunks = find_by_file_md5(db, file_md5=document_id)
        if not chunks:
            logger.warning("Synthetic eval generation skipped: no chunks found for document_id=%s", document_id)
            return 0

        selected_chunks = _sample_chunks(chunks)
        logger.info(
            "Synthetic eval generation started for document_id=%s total_chunks=%d selected_chunks=%d",
            document_id,
            len(chunks),
            len(selected_chunks),
        )

        client = GPTClient()
        rows_to_insert: List[Dict[str, str]] = []
        for idx, chunk in enumerate(selected_chunks, 1):
            chunk_text = str(getattr(chunk, "text_content", "") or "").strip()
            if not chunk_text:
                logger.warning(
                    "Synthetic eval generation skipped empty chunk document_id=%s chunk_id=%s",
                    document_id,
                    getattr(chunk, "chunk_id", ""),
                )
                continue

            prompt = _build_prompt(chunk_text)
            try:
                response = client.generate(messages=[{"role": "user", "content": prompt}])
                payload = _safe_json_parse(response)
                if not payload or not isinstance(payload.get("qa_pairs"), list):
                    logger.warning(
                        "Synthetic eval generation malformed JSON skipped document_id=%s chunk_id=%s chunk_index=%d",
                        document_id,
                        getattr(chunk, "chunk_id", ""),
                        idx,
                    )
                    time.sleep(delay_seconds)
                    continue

                for pair in payload["qa_pairs"]:
                    if not isinstance(pair, dict):
                        continue
                    question = str(pair.get("question", "")).strip()
                    answer = str(pair.get("answer", "")).strip()
                    if not question or not answer:
                        continue
                    rows_to_insert.append(
                        {
                            "document_id": document_id,
                            "chunk_id": str(pair.get("chunk_id") or getattr(chunk, "chunk_id", "")),
                            "question": question,
                            "answer": answer,
                        }
                    )
            except Exception as e:
                logger.warning(
                    "Synthetic eval generation failed for document_id=%s chunk_id=%s error=%s",
                    document_id,
                    getattr(chunk, "chunk_id", ""),
                    e,
                )
            finally:
                time.sleep(delay_seconds)

        rows_to_insert = _deduplicate_rows_by_similarity(rows_to_insert)

        inserted = create_many_synthetic_eval_rows(
            db,
            rows=rows_to_insert,
            pipeline_version=pipeline_version,
        )
        logger.info(
            "Synthetic eval generation finished for document_id=%s generated_rows=%d",
            document_id,
            len(inserted),
        )
        return len(inserted)
    finally:
        db.close()


def trigger_synthetic_eval_generation_background(
    document_id: str,
    pipeline_version: Optional[str] = None,
    replace_existing: bool = False,
) -> None:
    def _run() -> None:
        try:
            generate_synthetic_eval_for_document(
                document_id=document_id,
                pipeline_version=pipeline_version,
                replace_existing=replace_existing,
            )
        except Exception as e:
            logger.error(
                "Background synthetic eval generation failed for document_id=%s error=%s",
                document_id,
                e,
                exc_info=True,
            )

    thread = threading.Thread(target=_run, daemon=True, name=f"synthetic-eval-{document_id}")
    thread.start()
    logger.info("Synthetic eval background generation triggered for document_id=%s", document_id)


def trigger_synthetic_eval_backfill_background(
    max_documents: int = 2,
    pipeline_version: Optional[str] = None,
) -> None:
    def _run() -> None:
        try:
            generated = backfill_synthetic_eval_for_completed_documents(
                max_documents=max_documents,
                pipeline_version=pipeline_version,
            )
            logger.info(
                "Background synthetic eval backfill finished. max_documents=%d generated_rows=%d",
                max_documents,
                generated,
            )
        except Exception as e:
            logger.error(
                "Background synthetic eval backfill failed. max_documents=%d error=%s",
                max_documents,
                e,
                exc_info=True,
            )

    thread = threading.Thread(target=_run, daemon=True, name="synthetic-eval-backfill")
    thread.start()
    logger.info(
        "Synthetic eval background backfill triggered max_documents=%d pipeline_version=%s",
        max_documents,
        pipeline_version,
    )


def backfill_synthetic_eval_for_completed_documents(
    max_documents: int = 2,
    pipeline_version: Optional[str] = None,
) -> int:
    ensure_tables()

    db = SessionLocal()
    try:
        valid_files = get_file_uploads_with_vectors(db=db, limit=max_documents)
        document_ids = [item.file_md5 for item in valid_files if getattr(item, "file_md5", None)]
    finally:
        db.close()

    if not document_ids:
        logger.warning(
            "Synthetic eval backfill skipped: no uploaded documents with parsed chunks found"
        )
        return 0

    total_generated = 0
    for document_id in document_ids:
        try:
            generated = generate_synthetic_eval_for_document(
                document_id=document_id,
                pipeline_version=pipeline_version,
                replace_existing=False,
            )
            total_generated += generated
        except Exception as e:
            logger.warning(
                "Synthetic eval backfill failed for document_id=%s error=%s",
                document_id,
                e,
            )

    logger.info(
        "Synthetic eval backfill finished. documents=%d generated_rows=%d",
        len(document_ids),
        total_generated,
    )
    return total_generated
