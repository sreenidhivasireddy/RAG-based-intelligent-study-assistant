import pytest
from types import SimpleNamespace

from app.clients.gpt_client import GPTClient


class _FakeCompletions:
    def __init__(self):
        self.last_messages = None

    def create(self, **kwargs):
        self.last_messages = kwargs.get("messages", [])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok from model"))]
        )


@pytest.mark.asyncio
async def test_stream_response_async_includes_context_and_history_and_calls_on_chunk():
    fake_completions = _FakeCompletions()
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=fake_completions))

    client = GPTClient.__new__(GPTClient)
    client.client = fake_client
    client.deployment = "dummy"
    client.temperature = 0.7
    client.top_p = 0.95
    client.max_tokens = 1200

    seen_chunks = []

    def on_chunk(chunk):
        seen_chunks.append(chunk)

    result = await client.stream_response_async(
        user_message="summarize this file",
        context="File has important notes.",
        history=[{"role": "user", "content": "previous q"}, {"role": "assistant", "content": "previous a"}],
        on_chunk=on_chunk,
    )

    assert result == "ok from model"
    assert seen_chunks == ["ok from model"]

    msgs = fake_completions.last_messages
    assert any(m["role"] == "system" and "Context:" in m["content"] for m in msgs)
    assert any(m["role"] == "user" and m["content"] == "previous q" for m in msgs)
    assert any(m["role"] == "assistant" and m["content"] == "previous a" for m in msgs)
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "summarize this file"
