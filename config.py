"""
Configuration management for WhatsApp CV Analyzer.
Loads environment variables and provides typed configuration.
"""
import os
from typing import Literal
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Uses Pydantic for validation and type safety.
    """
    
    # Application
    APP_NAME: str = "WhatsApp CV Analyzer"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    
    # WhatsApp Cloud API
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "cv_analyzer_verify_token"
    
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
    
    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    """
    Cached settings instance.
    Use this to access configuration throughout the app.
    """
    return Settings()

# Convenience export
settings = get_settings()