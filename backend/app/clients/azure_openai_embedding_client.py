import os
from typing import List

from openai import AzureOpenAI

from app.utils.logging import setup_logger

logger = setup_logger(__name__)


class AzureOpenAIEmbeddingClient:
    """
    Embeddings via Azure OpenAI.

    Required env vars:
      AZURE_OPENAI_ENDPOINT (e.g. https://<resource>.openai.azure.com/)
      AZURE_OPENAI_API_KEY
      AZURE_OPENAI_API_VERSION (e.g. 2024-02-15-preview or 2024-05-01-preview)
      AZURE_OPENAI_EMBEDDING_DEPLOYMENT (deployment name)
    """

    def __init__(self):
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

        if not endpoint or not api_key or not deployment:
            raise RuntimeError(
                "Azure OpenAI embeddings not configured. Please set "
                "AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_EMBEDDING_DEPLOYMENT "
                "(and optionally AZURE_OPENAI_API_VERSION) in backend/.env"
            )

        self.deployment = deployment
        self.client = AzureOpenAI(
            azure_endpoint=endpoint.rstrip("/"),
            api_key=api_key,
            api_version=api_version,
        )

        logger.info(f"Initialized AzureOpenAIEmbeddingClient, deployment: {self.deployment}")

    def is_configured(self) -> bool:
        return bool(
            os.getenv("AZURE_OPENAI_ENDPOINT")
            and os.getenv("AZURE_OPENAI_API_KEY")
            and os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        # Azure OpenAI accepts list[str] input
        resp = self.client.embeddings.create(
            model=self.deployment,   # NOTE: Azure uses *deployment name* here
            input=texts,
        )
        return [item.embedding for item in resp.data]
