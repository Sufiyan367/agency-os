import enum
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class NotificationPriority(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class NotificationCategory(str, enum.Enum):
    SECURITY = "SECURITY"
    PRODUCTION = "PRODUCTION"
    FINANCIAL = "FINANCIAL"
    COMPLIANCE = "COMPLIANCE"
    SALES = "SALES"
    DELIVERY = "DELIVERY"
    SUPPORT = "SUPPORT"
    SYSTEM = "SYSTEM"


class NotificationEventPayload(BaseModel):
    """Normalized, sanitized event ready for policy evaluation and dispatch."""
    event_id: str
    event_type: str
    category: NotificationCategory = NotificationCategory.SYSTEM
    priority: NotificationPriority = NotificationPriority.NORMAL
    severity: Optional[str] = None  # SEV-1, SEV-2, etc.
    title: str
    body: str
    deep_link: Optional[str] = None
    action_required: bool = False
    action_url: Optional[str] = None
    business_id: Optional[int] = None
    customer_id: Optional[int] = None
    project_id: Optional[int] = None
    incident_id: Optional[int] = None
    payment_id: Optional[int] = None
    deduplication_key: str
    metadata_safe: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DeviceRegistrationRequest(BaseModel):
    """Client request to register browser / mobile Web Push device."""
    device_name: str = Field(default="Mobile Device", max_length=100)
    device_type: str = Field(default="mobile_web", max_length=50)  # mobile_android, mobile_ios, desktop_chrome, tablet
    endpoint: str = Field(description="Push subscription endpoint URL")
    p256dh: str = Field(description="Client public key")
    auth_token: str = Field(description="Client auth secret token")


class DeviceDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    device_name: str
    device_type: str
    is_active: bool
    last_seen_at: Optional[datetime] = None
    created_at: datetime


class PreferenceDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    critical_enabled: bool = True
    high_enabled: bool = True
    normal_enabled: bool = True
    low_enabled: bool = False
    payment_alerts: bool = True
    sales_alerts: bool = True
    delivery_alerts: bool = True
    support_alerts: bool = True
    security_alerts: bool = True
    compliance_alerts: bool = True
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "08:00"
    timezone: str = "UTC"


class PreferenceUpdateRequest(BaseModel):
    high_enabled: Optional[bool] = None
    normal_enabled: Optional[bool] = None
    low_enabled: Optional[bool] = None
    payment_alerts: Optional[bool] = None
    sales_alerts: Optional[bool] = None
    delivery_alerts: Optional[bool] = None
    support_alerts: Optional[bool] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    timezone: Optional[str] = None


class NotificationDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    event_id: Optional[str] = None
    deduplication_key: str
    event_type: str
    category: str
    priority: str
    severity: Optional[str] = None
    title: str
    body: str
    deep_link: Optional[str] = None
    action_required: bool
    action_url: Optional[str] = None
    business_id: Optional[int] = None
    customer_id: Optional[int] = None
    project_id: Optional[int] = None
    incident_id: Optional[int] = None
    payment_id: Optional[int] = None
    is_read: bool
    read_at: Optional[datetime] = None
    metadata_safe: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: List[NotificationDTO]
    total: int
    unread_count: int
    page: int
    page_size: int


class TestNotificationRequest(BaseModel):
    """Controlled internal test event trigger for verification."""
    __test__ = False

    event_type: str  # TEST_PAYMENT_VERIFIED, TEST_SEV1, TEST_POSITIVE_REPLY, TEST_DELIVERY_COMPLETE, TEST_NORMAL
    title: Optional[str] = None
    body: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    business_id: Optional[int] = None
    customer_name: Optional[str] = None
    amount_usd: Optional[float] = None
