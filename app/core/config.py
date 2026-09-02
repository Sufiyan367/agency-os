import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "Autonomous B2B Lead-Gen & Sales Agency"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///agency.db"
    SYNC_DATABASE_URL: str = "sqlite:///agency.db"

    # Pipeline Safeguards & Compliance
    DRY_RUN: bool = True
    MAX_OUTREACH_PER_DAY: int = 50
    MAX_FOLLOWUPS: int = 3
    REPLY_STOP_RULE: bool = True
    BOUNCE_STOP_RULE: bool = True
    OPT_OUT_STOP_RULE: bool = True

    # Pricing Defaults ($ USD)
    DEFAULT_SERVICE_PRICE_MIN: float = 450.0
    DEFAULT_SERVICE_PRICE_MAX: float = 1200.0

    # LLM Settings
    LLM_PROVIDER: str = "auto"  # 'nvidia', 'openai', 'openrouter', 'heuristic'
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    NVIDIA_API_KEY: Optional[str] = os.getenv("NVIDIA_API_KEY")
    OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")
    LLM_MODEL: str = "gpt-4o-mini"
    NVIDIA_MODEL: str = "meta/llama-3.1-70b-instruct"

    # Sender Info
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    OUTREACH_FROM_EMAIL: str = "prospects@agencygrowth.co"
    OUTREACH_FROM_NAME: str = "Elena Vance | Digital Strategy Director"

    # Lead Scoring Weights (must sum to 1.0)
    WEIGHT_WEBSITE_WEAKNESS: float = 0.25
    WEIGHT_SEO_OPPORTUNITY: float = 0.20
    WEIGHT_A11Y_OPPORTUNITY: float = 0.15
    WEIGHT_PERFORMANCE_OPPORTUNITY: float = 0.15
    WEIGHT_CONVERSION_OPPORTUNITY: float = 0.15
    WEIGHT_ABILITY_TO_PAY: float = 0.10

    # Market Opportunity Weights
    WEIGHT_MKT_NEED: float = 1.0
    WEIGHT_MKT_ABILITY_TO_PAY: float = 1.2
    WEIGHT_MKT_DIGITAL_WEAKNESS: float = 1.1
    WEIGHT_MKT_SEARCH_DEMAND: float = 0.9
    WEIGHT_MKT_BUSINESS_DENSITY: float = 0.8
    WEIGHT_MKT_SERVICE_FIT: float = 1.0
    WEIGHT_MKT_EXPECTED_DEAL_VALUE: float = 1.2
    WEIGHT_MKT_COMPETITION: float = 0.8
    WEIGHT_MKT_OUTREACH_DIFFICULTY: float = 0.7
    WEIGHT_MKT_COMPLIANCE_RISK: float = 0.9

settings = Settings()
