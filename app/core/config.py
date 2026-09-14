import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

def get_env_file() -> Optional[str]:
    """Returns the environment file path, or None during test execution to prevent production leakage."""
    if os.getenv("TESTING", "").lower() in ("true", "1", "yes") or os.getenv("APP_ENV") == "test":
        return os.getenv("ENV_FILE", None)
    return os.getenv("ENV_FILE", ".env")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=get_env_file(),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "Autonomous B2B Lead-Gen & Sales Agency"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite+aiosqlite:////app/data/agency.db" if os.path.exists("/app/data") else "sqlite+aiosqlite:///agency.db"
    )
    SYNC_DATABASE_URL: str = os.getenv(
        "SYNC_DATABASE_URL",
        "sqlite:////app/data/agency.db" if os.path.exists("/app/data") else "sqlite:///agency.db"
    )
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "1800"))

    # Production Cloud & Security Settings
    AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "false").lower() in ("true", "1", "yes")
    DASHBOARD_USERNAME: str = os.getenv("DASHBOARD_USERNAME", "admin")
    DASHBOARD_PASSWORD: str = os.getenv("DASHBOARD_PASSWORD", "")
    VIEWER_USERNAME: str = os.getenv("VIEWER_USERNAME", "viewer")
    VIEWER_PASSWORD: str = os.getenv("VIEWER_PASSWORD", "")
    API_SECRET_KEY: str = os.getenv("API_SECRET_KEY", "")
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "")
    SESSION_MAX_AGE_DAYS: int = 14
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "yes")
    WEBHOOK_REPLAY_WINDOW_SECONDS: int = int(os.getenv("WEBHOOK_REPLAY_WINDOW_SECONDS", "300"))
    WEBHOOK_SHARED_SECRET: Optional[str] = os.getenv("WEBHOOK_SHARED_SECRET")

    # Cloud VPS & Domain Configuration
    DOMAIN: str = os.getenv("DOMAIN", "localhost")
    TLS_EMAIL: str = os.getenv("TLS_EMAIL", "admin@localhost")
    BACKUP_DIR: str = os.getenv("BACKUP_DIR", "backups")
    BACKUP_RETENTION_DAYS: int = 30

    # Pipeline Safeguards & Compliance
    DRY_RUN: bool = True
    RESEARCH_ONLY: bool = os.getenv("RESEARCH_ONLY", "true").lower() in ("true", "1", "yes")
    MAX_OUTREACH_PER_DAY: int = int(os.getenv("MAX_OUTREACH_PER_DAY", "70"))
    MAX_FOLLOWUPS: int = 3
    REPLY_STOP_RULE: bool = True
    BOUNCE_STOP_RULE: bool = True
    OPT_OUT_STOP_RULE: bool = True

    # Pricing Defaults ($ USD)
    DEFAULT_SERVICE_PRICE_MIN: float = 500.0
    DEFAULT_SERVICE_PRICE_MAX: float = 1200.0

    # LLM Settings
    LLM_PROVIDER: str = "auto"  # 'nvidia', 'openai', 'openrouter', 'heuristic'
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    NVIDIA_API_KEY: Optional[str] = os.getenv("NVIDIA_API_KEY")
    OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")
    LLM_MODEL: str = "gpt-4o-mini"
    NVIDIA_MODEL: str = "meta/llama-3.1-70b-instruct"

    # Email Providers & Outreach Delivery
    EMAIL_PROVIDER: str = os.getenv("EMAIL_PROVIDER", "titan")  # 'titan', 'resend', 'sendgrid', 'smtp', 'gmail_oauth', 'dry_run'
    PRIMARY_EMAIL_PROVIDER: str = os.getenv("PRIMARY_EMAIL_PROVIDER", "titan")
    FALLBACK_EMAIL_PROVIDER: Optional[str] = os.getenv("FALLBACK_EMAIL_PROVIDER")
    EMAIL_DRY_RUN: bool = os.getenv("EMAIL_DRY_RUN", "true").lower() in ("true", "1", "yes")
    VOICE_DRY_RUN: bool = os.getenv("VOICE_DRY_RUN", "true").lower() in ("true", "1", "yes")
    VOICE_CALLING_ENABLED: bool = os.getenv("VOICE_CALLING_ENABLED", "false").lower() in ("true", "1", "yes")
    VOICE_PROVIDER: str = os.getenv("VOICE_PROVIDER", "dry_run")  # 'dry_run', 'twilio', 'bland'
    VOICE_CALLER_ID: str = os.getenv("VOICE_CALLER_ID", "+15125550100")
    VOICE_RECORDING_ENABLED: bool = os.getenv("VOICE_RECORDING_ENABLED", "true").lower() in ("true", "1", "yes")
    VOICE_CONSENT_DISCLOSURE: str = os.getenv("VOICE_CONSENT_DISCLOSURE", "This call may be recorded for quality and diagnostic assurance.")
    VOICE_MAX_CALL_DURATION_MINUTES: int = int(os.getenv("VOICE_MAX_CALL_DURATION_MINUTES", "15"))
    TWILIO_ACCOUNT_SID: Optional[str] = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN: Optional[str] = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER: Optional[str] = os.getenv("TWILIO_PHONE_NUMBER", os.getenv("VOICE_CALLER_ID", "+15125550100"))
    VOICEBOX_API_URL: Optional[str] = os.getenv("VOICEBOX_API_URL")
    VOICEBOX_API_KEY: Optional[str] = os.getenv("VOICEBOX_API_KEY")

    # Asterisk ARI Telephony Configuration
    ASTERISK_ARI_URL: str = os.getenv("ASTERISK_ARI_URL", "http://localhost:8088/ari")
    ASTERISK_ARI_USER: Optional[str] = os.getenv("ASTERISK_ARI_USER")
    ASTERISK_ARI_PASSWORD: Optional[str] = os.getenv("ASTERISK_ARI_PASSWORD")
    ASTERISK_APP_NAME: str = os.getenv("ASTERISK_APP_NAME", "agency_os_stasis")
    ASTERISK_SIP_TRUNK: str = os.getenv("ASTERISK_SIP_TRUNK", "PJSIP")

    # FreeSWITCH ESL Telephony Configuration
    FREESWITCH_ESL_HOST: str = os.getenv("FREESWITCH_ESL_HOST", "127.0.0.1")
    FREESWITCH_ESL_PORT: int = int(os.getenv("FREESWITCH_ESL_PORT", "8021"))
    FREESWITCH_ESL_PASSWORD: Optional[str] = os.getenv("FREESWITCH_ESL_PASSWORD")
    FREESWITCH_GATEWAY: str = os.getenv("FREESWITCH_GATEWAY", "default_gateway")

    # WhatsApp Business Platform (Cloud API)
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    WHATSAPP_ACCESS_TOKEN: Optional[str] = os.getenv("WHATSAPP_ACCESS_TOKEN")
    WHATSAPP_BUSINESS_ACCOUNT_ID: Optional[str] = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
    WHATSAPP_APP_SECRET: Optional[str] = os.getenv("WHATSAPP_APP_SECRET")
    WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "agency_os_wa_verify_token")
    WHATSAPP_DRY_RUN: bool = os.getenv("WHATSAPP_DRY_RUN", "true").lower() in ("true", "1", "yes")
    WHATSAPP_API_VERSION: str = os.getenv("WHATSAPP_API_VERSION", "v18.0")
    WHATSAPP_DEFAULT_TEMPLATE: str = os.getenv("WHATSAPP_DEFAULT_TEMPLATE", "agency_diagnostic_intro")

    BLAND_API_KEY: Optional[str] = os.getenv("BLAND_API_KEY")
    AUTONOMOUS_OUTREACH: bool = os.getenv("AUTONOMOUS_OUTREACH", "true").lower() in ("true", "1", "yes")
    AUTONOMOUS_AGENT_ENABLED: bool = os.getenv("AUTONOMOUS_AGENT_ENABLED", "true").lower() in ("true", "1", "yes")
    AUTONOMOUS_FIRST_CLIENT: bool = os.getenv("AUTONOMOUS_FIRST_CLIENT", "false").lower() in ("true", "1", "yes")
    AUTONOMOUS_AUTO_DISCOVERY: bool = os.getenv("AUTONOMOUS_AUTO_DISCOVERY", "true").lower() in ("true", "1", "yes")
    FOLLOWUPS_ENABLED: bool = os.getenv("FOLLOWUPS_ENABLED", "false").lower() in ("true", "1", "yes")
    MAX_ACTIVE_OUTREACH_PROSPECTS: int = int(os.getenv("MAX_ACTIVE_OUTREACH_PROSPECTS", "1"))
    EMERGENCY_STOP: bool = os.getenv("EMERGENCY_STOP", "false").lower() in ("true", "1", "yes")
    MINIMUM_TARGET_SERVICE_VALUE_USD: float = float(os.getenv("MINIMUM_TARGET_SERVICE_VALUE_USD", "500.0"))
    COMMERCIAL_FLOOR_USD: float = float(os.getenv("COMMERCIAL_FLOOR_USD", "500.0"))
    ONE_AT_A_TIME_PROSPECTING: bool = True
    
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
    OUTREACH_FROM_EMAIL: str = os.getenv("OUTREACH_FROM_EMAIL", "hello@automatedagencyos.tech")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", os.getenv("OUTREACH_FROM_EMAIL", "hello@automatedagencyos.tech"))
    EMAIL_REPLY_TO: str = os.getenv("EMAIL_REPLY_TO", "hello@automatedagencyos.tech")
    OUTREACH_FROM_NAME: str = os.getenv("OUTREACH_FROM_NAME", os.getenv("EMAIL_FROM_NAME", "Agency OS | Autonomous Growth Engine"))
    EMAIL_FROM_NAME: str = os.getenv("EMAIL_FROM_NAME", os.getenv("OUTREACH_FROM_NAME", "Agency OS | Autonomous Growth Engine"))
    PHYSICAL_POSTAL_ADDRESS: Optional[str] = os.getenv("PHYSICAL_POSTAL_ADDRESS")
    PUBLIC_DEMO_BASE_URL: Optional[str] = os.getenv("PUBLIC_DEMO_BASE_URL")

    # Gmail OAuth2 Provider Configuration
    GMAIL_CLIENT_ID: Optional[str] = os.getenv("GMAIL_CLIENT_ID")
    GMAIL_CLIENT_SECRET: Optional[str] = os.getenv("GMAIL_CLIENT_SECRET")
    GMAIL_REFRESH_TOKEN: Optional[str] = os.getenv("GMAIL_REFRESH_TOKEN")
    GMAIL_SENDER_EMAIL: Optional[str] = os.getenv("GMAIL_SENDER_EMAIL")
    GMAIL_DAILY_CAPACITY: int = int(os.getenv("GMAIL_DAILY_CAPACITY", "20"))

    # Titan Business Email Configuration (Primary Outbound Provider)
    TITAN_SMTP_HOST: str = os.getenv("TITAN_SMTP_HOST", "smtp.titan.email")
    TITAN_SMTP_PORT: int = int(os.getenv("TITAN_SMTP_PORT", "465"))
    TITAN_SMTP_USER: Optional[str] = os.getenv("TITAN_SMTP_USER", "hello@automatedagencyos.tech")
    TITAN_SMTP_PASSWORD: Optional[str] = os.getenv("TITAN_SMTP_PASSWORD")
    TITAN_IMAP_HOST: str = os.getenv("TITAN_IMAP_HOST", "imap.titan.email")
    TITAN_IMAP_PORT: int = int(os.getenv("TITAN_IMAP_PORT", "993"))
    TITAN_IMAP_USER: Optional[str] = os.getenv("TITAN_IMAP_USER", "hello@automatedagencyos.tech")
    TITAN_IMAP_PASSWORD: Optional[str] = os.getenv("TITAN_IMAP_PASSWORD")

    # Autonomous Outbound Approval
    AUTO_APPROVAL_ENABLED: bool = os.getenv("AUTO_APPROVAL_ENABLED", "true").lower() in ("true", "1", "yes")

    # Payment Architecture & Provider Strategy
    PREFERRED_PAYMENT_METHOD: str = os.getenv("PREFERRED_PAYMENT_METHOD", "google_pay")
    GOOGLE_PAY_VPA: str = os.getenv("GOOGLE_PAY_VPA", "agencyos@okhdfcbank")
    GOOGLE_PAY_MERCHANT_NAME: str = os.getenv("GOOGLE_PAY_MERCHANT_NAME", "Autonomous Agency OS")
    GOOGLE_PAY_MERCHANT_ID: Optional[str] = os.getenv("GOOGLE_PAY_MERCHANT_ID")
    
    PAYMENT_PROVIDER: str = os.getenv("PAYMENT_PROVIDER", "google_pay")  # 'google_pay' (default), 'razorpay', 'dry_run'
    PAYMENTS_ENABLED: bool = os.getenv("PAYMENTS_ENABLED", "false").lower() == "true"
    PAYMENT_DRY_RUN: bool = os.getenv("PAYMENT_DRY_RUN", "true").lower() in ("true", "1", "yes")
    MINIMUM_SERVICE_VALUE_USD: float = float(os.getenv("MINIMUM_SERVICE_VALUE_USD", "500.0"))
    TARGET_OFFER_MINIMUM_USD: float = float(os.getenv("TARGET_OFFER_MINIMUM_USD", "1000.0"))
    DEFAULT_ADVANCE_PERCENTAGE: float = float(os.getenv("DEFAULT_ADVANCE_PERCENTAGE", "40.0"))
    
    # Razorpay Gateway (Inactive unless explicitly configured and approved)
    RAZORPAY_ENABLED: bool = os.getenv("RAZORPAY_ENABLED", "false").lower() in ("true", "1", "yes")
    RAZORPAY_MODE: str = os.getenv("RAZORPAY_MODE", "test")
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

    # Discovery & Web Research Providers (Zyte & ScrapeGraphAI)
    SCRAPEGRAPH_API_KEY: Optional[str] = os.getenv("SCRAPEGRAPH_API_KEY")
    ZYTE_API_KEY: Optional[str] = os.getenv("ZYTE_API_KEY")
    ZYTE_MODE: str = os.getenv("ZYTE_MODE", "evaluation")
    ZYTE_TIMEOUT_SECONDS: float = float(os.getenv("ZYTE_TIMEOUT_SECONDS", "15.0"))
    ZYTE_CREDIT_BUDGET: int = int(os.getenv("ZYTE_CREDIT_BUDGET", "50"))

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
