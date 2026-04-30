"""
Configuration management for WhatsApp CV Analyzer.
Loads environment variables and provides typed configuration.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Uses Pydantic for validation and type safety.
    """

    # Pydantic v2 configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "WhatsApp CV Analyzer"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # WhatsApp Cloud API (REQUIRED from Render / .env)
    WHATSAPP_TOKEN: str
    WHATSAPP_PHONE_NUMBER_ID: str
    WHATSAPP_VERIFY_TOKEN: str

    # Supabase Configuration
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_BUCKET: str = "resumes"

    # AI Provider Configuration
    # Options: "rule_based", "ollama", "openai"
    AI_PROVIDER: str = "rule_based"

    # Ollama Configuration
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"

    # OpenAI Configuration (fallback)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Email Configuration
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "noreply@cvanalyzer.ai"

    # ATS Scoring Weights
    ATS_WEIGHT_KEYWORDS: float = 0.25
    ATS_WEIGHT_FORMAT: float = 0.20
    ATS_WEIGHT_SECTIONS: float = 0.25
    ATS_WEIGHT_LENGTH: float = 0.15
    ATS_WEIGHT_ACTION_VERBS: float = 0.15


@lru_cache()
def get_settings() -> Settings:
    """
    Cached settings instance.
    Raises validation errors if required environment variables are missing.
    """
    return Settings()


# Convenience export
settings = get_settings()