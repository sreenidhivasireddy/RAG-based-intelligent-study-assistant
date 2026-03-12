import os
import inspect
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

class GPTClient:
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        )
        self.deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")

        # Optional defaults from env
        self.temperature = float(os.getenv("GPT_TEMPERATURE", "0.7"))
        self.top_p = float(os.getenv("GPT_TOP_P", "0.95"))
        self.max_tokens = int(os.getenv("GPT_MAX_TOKENS", "1200"))

    def generate(self, messages):
        resp = self.client.chat.completions.create(
            model=self.deployment,
            messages=messages,
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_tokens,
        )
        return resp.choices[0].message.content

    async def stream_response_async(self, user_message=None, messages=None, system_prompt=None, **kwargs) -> str:
        """
        Repo expects: `await gpt_client.stream_response_async(...)` -> returns full text.
        Compatible with either:
          - user_message="hi"
          - messages=[{role, content}, ...]
        """
        context = kwargs.get("context")
        history = kwargs.get("history") or []
        on_chunk = kwargs.get("on_chunk")

        if messages is None:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            # Keep context in a system message so the model can ground answers.
            if context:
                messages.append({
                    "role": "system",
                    "content": (
                        "Use the following retrieved document context to answer the user.\n"
                        "If context is insufficient, say what is missing.\n\n"
                        f"Context:\n{context}"
                    ),
                })

            # Include prior turns when provided.
            for turn in history:
                role = turn.get("role")
                content = turn.get("content")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})

            if user_message is None:
                user_message = ""
            messages.append({"role": "user", "content": user_message})

        # Return a full response (non-streaming) so it can be awaited
        resp = self.client.chat.completions.create(
            model=self.deployment,
            messages=messages,
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_tokens,
            stream=False,
        )
        text = resp.choices[0].message.content

        if on_chunk and text:
            chunk_size = 200
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i + chunk_size]
                callback_result = on_chunk(chunk)
                if inspect.isawaitable(callback_result):
                    await callback_result

        return text
