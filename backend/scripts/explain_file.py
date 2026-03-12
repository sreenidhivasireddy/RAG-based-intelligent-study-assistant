import asyncio
from typing import Optional, List, Dict
from app.database import SessionLocal
from app.services.file_content_service import FileContentService
from app.clients.gpt_client import GPTClient
from app.repositories.upload_repository import get_file_upload
from app.clients.azure_search import get_azure_search_client
from app.services.azure_search_service import AzureSearchService
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def explain_document(
    file_md5: str,
    question: Optional[str] = None,
    db: Optional[object] = None,
    llm_client: Optional[GPTClient] = None,
    max_chars: int = 15000,
) -> Dict:
    """
    Explain a document by MD5. Returns a dict with keys: response, citations (list).
    Uses FileContentService and AzureSearchService to prepare context and then calls LLM.
    """
    own_db = False
    if db is None:
        db = SessionLocal()
        own_db = True

    try:
        file_content_service = FileContentService()

        # 1) try to get snippets from DB
        snippets = file_content_service.get_file_snippets(file_md5=file_md5, db=db, max_snippets=5)

        # 2) try to get Azure Search top chunks for the question (if provided)
        citations = []
        search_preview = []
        try:
            search_client = get_azure_search_client()
            azure_search_service = AzureSearchService(search_client)
            if question:
                results = azure_search_service.search(query=question, top_k=5, filter_expr=f"fileMd5 eq '{file_md5}'")
            else:
                results = azure_search_service.search(query=None, top_k=5, filter_expr=f"fileMd5 eq '{file_md5}'")

            for r in results:
                txt = r.get('content') or ''
                cid = r.get('chunk_id')
                fname = r.get('file_name')
                citations.append({"file_name": fname, "chunk_id": cid})
                if txt:
                    search_preview.append(txt[:1000])
        except Exception as e:
            logger.debug(f"Azure search lookup failed in explain_document: {e}")

        # 3) If snippets empty, fallback to full file content
        combined_text = ''
        if snippets:
            for s in snippets:
                combined_text += s.get('content', '') + '\n'
        else:
            full = file_content_service.get_file_content_by_md5(file_md5=file_md5, db=db)
            combined_text = (full or '')

        # also append search_preview to combined context
        if search_preview:
            combined_text = '\n'.join(search_preview) + '\n\n' + combined_text

        if not combined_text:
            return {"response": "", "citations": [], "error": "No content available for this file"}

        prompt_body = combined_text[:max_chars]
        question_text = question or f"Please summarize and explain the key points of this document ({file_md5})."

        prompt = (
            "You are a helpful assistant. Use the provided document excerpts to answer the user's question.\n"
            "Include brief citations in the format [fileName:chunkId] where appropriate.\n\n"
            f"Context:\n{prompt_body}\n\nQuestion:\n{question_text}\n\nAnswer concisely."
        )

        client = llm_client or GPTClient()
        # call LLM (non-streaming) and return full response
        resp = await client.stream_response_async(user_message=prompt)

        return {"response": resp, "citations": citations}

    finally:
        if own_db:
            db.close()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--md5', required=True)
    parser.add_argument('--question', required=False)
    args = parser.parse_args()

    res = asyncio.run(explain_document(args.md5, question=args.question))
    print('\n--- AI Explanation ---\n')
    print(res.get('response'))
