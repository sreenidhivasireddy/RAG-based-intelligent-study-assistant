import asyncio
import pytest
from types import SimpleNamespace

from app.services.chat_handler import ChatHandler

# Dummy websocket to collect sent JSON messages
class DummyWebSocket:
    def __init__(self):
        self.messages = []
    async def send_json(self, data):
        # store shallow copy
        self.messages.append(data)

class DummyRedis:
    def get(self, key):
        return None
    def setex(self, key, ttl, value):
        pass

class DummyLLM:
    async def stream_response_async(self, user_message, context=None, history=None, on_chunk=None):
        if on_chunk:
            await on_chunk("ok")
        return "ok"

class DummySearch:
    def hybrid_search(self, query, top_k=5, file_md5_filter=None):
        return [], {}

@pytest.mark.asyncio
async def test_chat_handler_explain_triggers_explain_and_streams(monkeypatch):
    async def fake_explain(file_md5, question=None):
        return {"response": "This is the explanation text.", "citations": [{"file_name": "PPA_2_MB.txt", "chunk_id": "1"}]}

    monkeypatch.setattr('app.services.chat_handler.explain_document', fake_explain)

    # Create ChatHandler with dummy deps
    redis_client = DummyRedis()
    llm_client = DummyLLM()
    search_service = DummySearch()

    handler = ChatHandler(redis_client=redis_client, llm_client=llm_client, search_service=search_service)

    # Provide a fake upload list in DB: monkeypatch get_all_file_uploads to return one candidate
    from app.repositories.upload_repository import get_all_file_uploads
    class FakeUpload:
        def __init__(self, md5, name, created_at):
            self.file_md5 = md5
            self.file_name = name
            self.created_at = created_at
    def fake_get_all(db, skip=0, limit=1000, status_filter=None):
        return [FakeUpload('md5-ppa', 'PPA_2_MB.txt', 12345)]
    monkeypatch.setattr('app.services.chat_handler.get_all_file_uploads', fake_get_all)

    ws = DummyWebSocket()

    # Act: call process_message with Explain command
    resp = await handler.process_message("Explain PPA_2_MB.txt", websocket=ws)

    # Assert: websocket received info, chunks, completion
    types = [m.get('type') or ('chunk' if 'chunk' in m else None) for m in ws.messages]
    # Expect an info message then at least one chunk then completion
    assert any(m.get('type') == 'info' for m in ws.messages)
    assert any('chunk' in m for m in ws.messages)
    assert any(m.get('type') == 'completion' for m in ws.messages)
    assert resp == "This is the explanation text."


@pytest.mark.asyncio
async def test_chat_handler_summarize_this_file_uses_latest_uploaded_file(monkeypatch):
    class FakeUpload:
        def __init__(self, md5, name, created_at, status=2, total_size=9_000_000):
            self.file_md5 = md5
            self.file_name = name
            self.created_at = created_at
            self.status = status
            self.total_size = total_size

    def fake_get_all(db, skip=0, limit=1000, status_filter=None):
        if status_filter == 1:
            return []
        if status_filter == 2:
            return [
                FakeUpload("old-md5", "old.pdf", 1),
                FakeUpload("new-md5", "new.pdf", 2),
            ]
        return []

    monkeypatch.setattr('app.services.chat_handler.get_all_file_uploads', fake_get_all)

    # Avoid opening real DB sessions
    class DummyDb:
        def close(self):
            pass
    monkeypatch.setattr('app.services.chat_handler.SessionLocal', lambda: DummyDb())

    captured = {}

    class CapturingLLM:
        async def stream_response_async(self, user_message, context=None, history=None, on_chunk=None):
            captured["context"] = context
            if on_chunk:
                await on_chunk("done")
            return "done"

    handler = ChatHandler(
        redis_client=DummyRedis(),
        llm_client=CapturingLLM(),
        search_service=DummySearch()
    )

    monkeypatch.setattr(
        handler.file_content_service,
        "get_file_content_by_md5",
        lambda file_md5, db: "content from latest file" if file_md5 == "new-md5" else None
    )

    ws = DummyWebSocket()
    resp = await handler.process_message("summarize this file", websocket=ws)

    assert resp == "done"
    assert "new.pdf" in (captured.get("context") or "")
    assert "content from latest file" in (captured.get("context") or "")
