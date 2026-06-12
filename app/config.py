import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Port to run FastAPI server on
    PORT: int = 8000

    # LLM CONFIGURATION (OpenAI-Compatible Providers)
    LLM_PROVIDER: str = "openai"
    LLM_MODEL: str = "gpt-4o"
    LLM_API_KEY: str = "mock-key-for-local-testing"
    LLM_BASE_URL: Optional[str] = None

    # GOOGLE APIS CONFIGURATION
    USE_MOCK_SERVICES: bool = True
    GOOGLE_SHEETS_SPREADSHEET_ID: Optional[str] = None
    GOOGLE_CALENDAR_ID: str = "primary"
    GOOGLE_SERVICE_ACCOUNT_JSON: Optional[str] = None

    # Read from .env file if it exists
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
