from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class CountryProfileDTO(BaseModel):
    code: str
    name: str
    timezone: str
    currency: str = "USD"
    language: str = "en"
    daily_quota: int = 10
    enabled: bool = True
    sending_window_start: int = 9
    sending_window_end: int = 17
    compliance_framework: str = "CAN-SPAM"
    requires_postal_address: bool = True
    requires_opt_out_link: bool = True
    b2b_exemption_notes: str = ""


class RolloutLevelDTO(BaseModel):
    level: int
    name: str
    daily_max_real_emails: int
    description: str


class RolloutConfigDTO(BaseModel):
    current_level: int = 0
    current_level_name: str = "Simulation (Dry Run)"
    daily_max_real_emails: int = 0
    is_simulation: bool = True
    levels: List[RolloutLevelDTO] = Field(default_factory=list)


class CampaignDTO(BaseModel):
    id: Optional[int] = None
    name: str
    country_code: str
    country_name: str = ""
    status: str = "ACTIVE"  # ACTIVE, PAUSED, DRAFT, COMPLETED
    timezone: str = "UTC"
    daily_quota: int = 10
    service_type: str = "web_turnaround"
    sender_identity: Optional[str] = None
    sender_name: Optional[str] = None
    reply_to: Optional[str] = None
    postal_address: Optional[str] = None
    sending_window_start: int = 9
    sending_window_end: int = 17
    approval_policy: str = "MANUAL_CEO_APPROVAL"
    enabled: bool = True
    today_sent: int = 0
    today_remaining: int = 10
    total_sent: int = 0
    replies_count: int = 0
    interested_count: int = 0
    bounces_count: int = 0
    bounce_rate: float = 0.0
    is_in_sending_window: bool = True
    local_time_formatted: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class QuotaCheckResult(BaseModel):
    allowed: bool
    effective_limit: int
    country_quota: int
    campaign_quota: int
    global_quota: int
    provider_quota: int
    sender_quota: int
    rollout_level_limit: int
    limiting_factor: str
    reason: str
    country_sent_today: int = 0
    global_sent_today: int = 0
    campaign_sent_today: int = 0
    rollout_limit: int = 0
    effective_remaining: int = 0


class ComplianceCheckItem(BaseModel):
    check_name: str
    passed: bool
    detail: str


class ComplianceGateResult(BaseModel):
    is_eligible: bool
    checks: List[ComplianceCheckItem] = Field(default_factory=list)
    failure_reasons: List[str] = Field(default_factory=list)
    quota_result: Optional[QuotaCheckResult] = None
