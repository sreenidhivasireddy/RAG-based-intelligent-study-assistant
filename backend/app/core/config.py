"""
Application configuration and environment management.
Loads and validates all settings from environment variables.
"""

from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Provides validation and helpful error messages for missing configs.
    """

    # ==================== Server Configuration ====================
    PORT: int = 8000
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ==================== Database Configuration ====================
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "root"
    MYSQL_DATABASE: str = "rag"

    # ==================== Redis Configuration ====================
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # ==================== Azure Blob Storage Configuration ====================
    # For dev: use connection string from Storage Account > Access keys
    AZURE_STORAGE_CONNECTION_STRING: Optional[str] = None
    # Container name (bucket equivalent)
    AZURE_STORAGE_CONTAINER: str = "documents"

    # ==================== Kafka Configuration ====================
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"

    # ==================== Azure AI Search Configuration ====================
    AZURE_SEARCH_ENDPOINT: Optional[str] = None
    AZURE_SEARCH_ADMIN_KEY: Optional[str] = None
    AZURE_SEARCH_INDEX: Optional[str] = None

    # ==================== Azure OpenAI Configuration ====================
    AZURE_OPENAI_ENDPOINT: Optional[str] = None
    AZURE_OPENAI_API_KEY: Optional[str] = None
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: Optional[str] = None
    AZURE_OPENAI_CHAT_DEPLOYMENT: Optional[str] = None

    # ==================== OpenAI Configuration ====================
    OPENAI_API_KEY: Optional[str] = None
    GPT_MODEL: str = "gpt-4o-mini"
    GPT_TEMPERATURE: float = 0.7
    GPT_TOP_P: float = 0.95
    GPT_MAX_TOKENS: int = 2000

    def validate_azure_blob_config(self) -> None:
        """
        Validate required Azure Blob Storage configuration.

        Raises:
            ValueError: If required Azure Blob config is missing
        """
        # If you want to allow local mode, you can change this logic to be conditional
        if not self.AZURE_STORAGE_CONNECTION_STRING:
            error_msg = (
                "❌ Missing required Azure Blob Storage configuration:\n"
                "  • AZURE_STORAGE_CONNECTION_STRING: Storage connection string "
                "(Storage account > Access keys > Connection string)\n\n"
                "✅ Solution: Add these environment variables to your .env file:\n"
                "   AZURE_STORAGE_CONNECTION_STRING=\"DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net\"\n"
                "   AZURE_STORAGE_CONTAINER=documents\n"
            )
            raise ValueError(error_msg)

        if not self.AZURE_STORAGE_CONTAINER:
            error_msg = (
                "❌ Missing required Azure Blob Storage configuration:\n"
                "  • AZURE_STORAGE_CONTAINER: Container name (e.g., documents)\n\n"
                "✅ Solution: Add this environment variable to your .env file:\n"
                "   AZURE_STORAGE_CONTAINER=documents\n"
            )
            raise ValueError(error_msg)

    def validate_azure_search_config(self) -> None:
        """
        Validate required Azure AI Search configuration.

        Raises:
            ValueError: If any required Azure Search config is missing
        """
        required_fields = {
            "AZURE_SEARCH_ENDPOINT": "Azure Search service endpoint (e.g., https://your-service.search.windows.net)",
            "AZURE_SEARCH_ADMIN_KEY": "Azure Search admin API key",
            "AZURE_SEARCH_INDEX": "Azure Search index name",
        }

        missing_fields = []
        for field_name, description in required_fields.items():
            value = getattr(self, field_name, None)
            if not value:
                missing_fields.append(f"  • {field_name}: {description}")

        if missing_fields:
            error_msg = (
                "❌ Missing required Azure AI Search configuration:\n"
                + "\n".join(missing_fields)
                + "\n\n✅ Solution: Add these environment variables to your .env file:\n"
                "   AZURE_SEARCH_ENDPOINT=https://your-service.search.windows.net\n"
                "   AZURE_SEARCH_ADMIN_KEY=your-admin-key\n"
                "   AZURE_SEARCH_INDEX=your-index-name"
            )
            raise ValueError(error_msg)

    def validate_azure_openai_config(self) -> None:
        """
        Validate required Azure OpenAI configuration.

        Raises:
            ValueError: If any required Azure OpenAI config is missing
        """
        required_fields = {
            "AZURE_OPENAI_ENDPOINT": "Azure OpenAI service endpoint",
            "AZURE_OPENAI_API_KEY": "Azure OpenAI API key",
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "Embedding model deployment name",
            "AZURE_OPENAI_CHAT_DEPLOYMENT": "Chat model deployment name",
        }

        missing_fields = []
        for field_name, description in required_fields.items():
            value = getattr(self, field_name, None)
            if not value:
                missing_fields.append(f"  • {field_name}: {description}")

        if missing_fields:
            error_msg = (
                "❌ Missing required Azure OpenAI configuration:\n"
                + "\n".join(missing_fields)
                + "\n\n✅ Solution: Add these environment variables to your .env file"
            )
            raise ValueError(error_msg)

    class Config:
        env_file = ".env"
        case_sensitive = True


# Initialize settings
settings = Settings()

# Validate critical configurations
try:
    settings.validate_azure_search_config()
    settings.validate_azure_openai_config()
    settings.validate_azure_blob_config()
except ValueError as e:
    print(f"\n{e}\n")
    raise