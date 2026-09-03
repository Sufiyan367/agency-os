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
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///agency.db")
    SYNC_DATABASE_URL: str = os.getenv("SYNC_DATABASE_URL", "sqlite:///agency.db")

    # Production Cloud & Security Settings
    AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "false").lower() in ("true", "1", "yes")
    DASHBOARD_USERNAME: str = os.getenv("DASHBOARD_USERNAME", "admin")
    DASHBOARD_PASSWORD: str = os.getenv("DASHBOARD_PASSWORD", "agency_admin_2026")
    API_SECRET_KEY: str = os.getenv("API_SECRET_KEY", "agency_master_secret_prod_key_2026")
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "agency_session_hmac_secret_2026")
    SESSION_MAX_AGE_DAYS: int = 14

    # Cloud VPS & Domain Configuration
    DOMAIN: str = os.getenv("DOMAIN", "localhost")
    TLS_EMAIL: str = os.getenv("TLS_EMAIL", "admin@localhost")
    BACKUP_DIR: str = os.getenv("BACKUP_DIR", "backups")
    BACKUP_RETENTION_DAYS: int = 30

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

    # Email Providers & Outreach Delivery
    EMAIL_PROVIDER: str = "dry_run"  # 'dry_run', 'resend', 'sendgrid', 'smtp'
    EMAIL_DRY_RUN: bool = True
    VOICE_DRY_RUN: bool = os.getenv("VOICE_DRY_RUN", "true").lower() in ("true", "1", "yes")
    VOICE_PROVIDER: str = os.getenv("VOICE_PROVIDER", "dry_run")  # 'dry_run', 'twilio', 'bland'
    VOICE_CALLER_ID: str = os.getenv("VOICE_CALLER_ID", "+15125550100")
    VOICE_RECORDING_ENABLED: bool = os.getenv("VOICE_RECORDING_ENABLED", "true").lower() in ("true", "1", "yes")
    VOICE_CONSENT_DISCLOSURE: str = os.getenv("VOICE_CONSENT_DISCLOSURE", "This call may be recorded for quality and diagnostic assurance.")
    VOICE_MAX_CALL_DURATION_MINUTES: int = int(os.getenv("VOICE_MAX_CALL_DURATION_MINUTES", "15"))
    TWILIO_ACCOUNT_SID: Optional[str] = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN: Optional[str] = os.getenv("TWILIO_AUTH_TOKEN")
    BLAND_API_KEY: Optional[str] = os.getenv("BLAND_API_KEY")
    AUTONOMOUS_OUTREACH: bool = os.getenv("AUTONOMOUS_OUTREACH", "false").lower() in ("true", "1", "yes")
    AUTONOMOUS_AGENT_ENABLED: bool = os.getenv("AUTONOMOUS_AGENT_ENABLED", "false").lower() in ("true", "1", "yes")
    MINIMUM_TARGET_SERVICE_VALUE_USD: float = float(os.getenv("MINIMUM_TARGET_SERVICE_VALUE_USD", "500.0"))
    
    # TCPA & Calling Hours Compliance
    CALLING_HOURS_START: int = int(os.getenv("CALLING_HOURS_START", "8"))  # 8:00 AM local
    CALLING_HOURS_END: int = int(os.getenv("CALLING_HOURS_END", "20"))     # 8:00 PM local
    ENFORCE_CALLING_HOURS: bool = os.getenv("ENFORCE_CALLING_HOURS", "true").lower() in ("true", "1", "yes")
    MAX_OUTREACH_RETRIES: int = int(os.getenv("MAX_OUTREACH_RETRIES", "3"))
    CONTROLLED_TEST_MODE: bool = os.getenv("CONTROLLED_TEST_MODE", "true").lower() in ("true", "1", "yes")
    
    RESEND_API_KEY: Optional[str] = os.getenv("RESEND_API_KEY")
    SENDGRID_API_KEY: Optional[str] = os.getenv("SENDGRID_API_KEY")
    SMTP_HOST: Optional[str] = os.getenv("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: Optional[str] = os.getenv("SMTP_USER")
    SMTP_USERNAME: Optional[str] = os.getenv("SMTP_USERNAME", os.getenv("SMTP_USER"))
    SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD")
    OUTREACH_FROM_EMAIL: str = os.getenv("OUTREACH_FROM_EMAIL", "prospects@agencygrowth.co")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", os.getenv("OUTREACH_FROM_EMAIL", "prospects@agencygrowth.co"))
    EMAIL_REPLY_TO: str = os.getenv("EMAIL_REPLY_TO", "replies@agencygrowth.co")
    OUTREACH_FROM_NAME: str = os.getenv("OUTREACH_FROM_NAME", "Elena Vance | Digital Strategy Director")
    EMAIL_FROM_NAME: str = os.getenv("EMAIL_FROM_NAME", os.getenv("OUTREACH_FROM_NAME", "Elena Vance | Digital Strategy Director"))

    # Payment Gateway (Razorpay Primary, Stripe Optional, Dry Run)
    PAYMENT_PROVIDER: str = os.getenv("PAYMENT_PROVIDER", "razorpay")  # 'razorpay' (primary), 'stripe', 'dry_run'
    PAYMENTS_ENABLED: bool = os.getenv("PAYMENTS_ENABLED", "false").lower() == "true"
    PAYMENT_DRY_RUN: bool = os.getenv("PAYMENT_DRY_RUN", "true").lower() in ("true", "1", "yes")
    MINIMUM_SERVICE_VALUE_USD: float = float(os.getenv("MINIMUM_SERVICE_VALUE_USD", "500.0"))
    RAZORPAY_MODE: str = os.getenv("RAZORPAY_MODE", "test")
    DEFAULT_ADVANCE_PERCENTAGE: float = float(os.getenv("DEFAULT_ADVANCE_PERCENTAGE", "40.0"))
    
    # Razorpay (Primary)
    RAZORPAY_KEY_ID: Optional[str] = os.getenv("RAZORPAY_KEY_ID")
    RAZORPAY_KEY_SECRET: Optional[str] = os.getenv("RAZORPAY_KEY_SECRET")
    RAZORPAY_WEBHOOK_SECRET: Optional[str] = os.getenv("RAZORPAY_WEBHOOK_SECRET")
    RAZORPAY_CURRENCY: str = os.getenv("RAZORPAY_CURRENCY", "USD")

    # Stripe (Optional Secondary)
    STRIPE_SECRET_KEY: Optional[str] = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_WEBHOOK_SECRET: Optional[str] = os.getenv("STRIPE_WEBHOOK_SECRET")

    # Inbound Inbox Polling (IMAP & Webhooks)
    IMAP_HOST: Optional[str] = os.getenv("IMAP_HOST")
    IMAP_PORT: int = int(os.getenv("IMAP_PORT", "993"))
    IMAP_USER: Optional[str] = os.getenv("IMAP_USER")
    IMAP_PASSWORD: Optional[str] = os.getenv("IMAP_PASSWORD")
    INBOX_POLL_INTERVAL_SECONDS: int = 120

    # Background Autonomous Worker / Scheduler
    WORKER_ENABLED: bool = True
    WORKER_CYCLE_INTERVAL_MINUTES: int = 30

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
