import os
import ipaddress
import re
import socket
from urllib.parse import urlparse
from typing import Tuple, Optional

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,12}$")
PHONE_CLEAN_REGEX = re.compile(r"[^\d+]")

DISALLOWED_EMAIL_PREFIXES = ("you@company", "test@", "example@", "sentry@", "wixpress", "domain@domain")

PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

def is_safe_url(url: str) -> Tuple[bool, str]:
    """
    Validates that a URL is safe to fetch and protects against SSRF attacks.
    Prevents requests to internal infrastructure, link-local addresses, and loopbacks.
    """
    if not url or not isinstance(url, str):
        return False, "URL is empty or invalid"
    
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return False, "URL must use http or https protocol"
        
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False, "URL lacks valid hostname"

        # Disallow localhost directly
        if hostname.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False, "Loopback address is disallowed"

        # Resolve IP to check for internal/private networks
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for item in addr_info:
                ip_str = item[4][0]
                ip_obj = ipaddress.ip_address(ip_str)
                for net in PRIVATE_NETWORKS:
                    if ip_obj in net:
                        return False, f"Target IP {ip_str} is in private/restricted network"
        except socket.gaierror:
            # If resolution fails, let caller decide or block
            pass

        return True, "URL is safe"
    except Exception as e:
        return False, f"URL parse error: {str(e)}"

def normalize_domain(domain_or_url: str) -> str:
    """Extracts and normalizes clean root domain/host without www or scheme."""
    if not domain_or_url:
        return ""
    d = domain_or_url.strip().lower()
    if "://" in d:
        d = urlparse(d).netloc
    d = d.split(":")[0]  # strip port
    if d.startswith("www."):
        d = d[4:]
    return d.strip("/")

def validate_email_syntax(email: str) -> bool:
    """Verifies email syntax conforms to standard and is not a placeholder/script."""
    if not email or not isinstance(email, str):
        return False
    email = email.strip()
    if len(email) > 254:
        return False
    if any(p in email.lower() for p in DISALLOWED_EMAIL_PREFIXES):
        return False
    return bool(EMAIL_REGEX.match(email))

def sanitize_phone(phone: str) -> str:
    """Normalizes phone numbers to readable clean format."""
    if not phone:
        return ""
    cleaned = PHONE_CLEAN_REGEX.sub("", phone)
    return cleaned

# --- Production Dashboard & Cloud Authentication ---
import hmac
import hashlib
import time
import secrets
import asyncio
from typing import Dict, List, Any
from fastapi import HTTPException
from app.core.config import settings

class SecurityConfigurationError(RuntimeError):
    """Raised when application security configuration fails closed."""
    pass

FORBIDDEN_SECRET_PATTERNS = (
    "agency_admin_2026",
    "agency_viewer_2026",
    "agency_master_secret",
    "agency_secret_master",
    "agency_session_hmac",
    "admin123",
    "password",
    "changeme",
    "replace_with",
    "secret_prod_key",
    "default",
    "123456",
)

def validate_production_configuration(raise_on_error: bool = True, allow_initial_setup: bool = False) -> List[str]:
    """
    Validates that production environment configuration complies with security standards.
    Fails closed by raising SecurityConfigurationError if running in production mode
    or when AUTH_ENABLED=True and secrets are insecure, missing, or predictable defaults.
    """
    errors = []
    is_prod = getattr(settings, "APP_ENV", "development").lower() == "production"
    auth_enabled = getattr(settings, "AUTH_ENABLED", False)

    # 1. In production, AUTH_ENABLED must be True
    if is_prod and not auth_enabled:
        errors.append("AUTH_ENABLED must be True when APP_ENV=production.")

    # 2. In production, DEBUG must be False
    if is_prod and getattr(settings, "DEBUG", False):
        errors.append("DEBUG must be False when APP_ENV=production.")

    # 3. Secret validation when AUTH_ENABLED=True or when in production
    if auth_enabled or is_prod:
        required_secrets = {
            "DASHBOARD_USERNAME": getattr(settings, "DASHBOARD_USERNAME", ""),
            "DASHBOARD_PASSWORD": getattr(settings, "DASHBOARD_PASSWORD", ""),
            "VIEWER_USERNAME": getattr(settings, "VIEWER_USERNAME", ""),
            "VIEWER_PASSWORD": getattr(settings, "VIEWER_PASSWORD", ""),
            "API_SECRET_KEY": getattr(settings, "API_SECRET_KEY", ""),
            "SESSION_SECRET": getattr(settings, "SESSION_SECRET", ""),
        }

        # Check for missing/empty
        for name, val in required_secrets.items():
            if name in ("DASHBOARD_PASSWORD", "VIEWER_PASSWORD") and allow_initial_setup:
                continue
            if not val or not str(val).strip():
                errors.append(f"Missing required security configuration: {name} cannot be empty when AUTH_ENABLED=True.")

        # Check for forbidden defaults/placeholders
        for name, val in required_secrets.items():
            if not val or not str(val).strip():
                continue
            val_clean = str(val).lower().strip()
            for forbidden in FORBIDDEN_SECRET_PATTERNS:
                if forbidden in val_clean:
                    errors.append(
                        f"Insecure default or example placeholder detected in {name}. "
                        "Fallback credentials and placeholders are strictly prohibited."
                    )
                    break

        # Check key lengths/entropy
        api_key = str(getattr(settings, "API_SECRET_KEY", "")).strip()
        if api_key and len(api_key) < 32:
            errors.append("API_SECRET_KEY must be at least 32 characters long.")

        session_secret = str(getattr(settings, "SESSION_SECRET", "")).strip()
        if session_secret and len(session_secret) < 32:
            errors.append("SESSION_SECRET must be at least 32 characters long.")

        # Passwords must use PBKDF2 format in production
        if is_prod:
            dash_pw = str(getattr(settings, "DASHBOARD_PASSWORD", "")).strip()
            if dash_pw and not dash_pw.startswith("pbkdf2:sha256:"):
                errors.append(
                    "DASHBOARD_PASSWORD must use the PBKDF2 hashed format (pbkdf2:sha256:...) in production. "
                    "Plaintext passwords are prohibited."
                )
            viewer_pw = str(getattr(settings, "VIEWER_PASSWORD", "")).strip()
            if viewer_pw and not viewer_pw.startswith("pbkdf2:sha256:"):
                errors.append(
                    "VIEWER_PASSWORD must use the PBKDF2 hashed format (pbkdf2:sha256:...) in production. "
                    "Plaintext passwords are prohibited."
                )

    if errors and raise_on_error:
        error_msg = "CRITICAL SECURITY CONFIGURATION FAILURE (FAIL CLOSED):\n" + "\n".join(f" - {e}" for e in errors)
        raise SecurityConfigurationError(error_msg)

    return errors

def create_session_token(username: str, role: str = "admin", expires_in_days: int = 14) -> str:
    """Creates a cryptographically signed HMAC-SHA256 session token with embedded role."""
    session_secret = settings.SESSION_SECRET or ""
    if not session_secret:
        raise SecurityConfigurationError("SESSION_SECRET is empty. Cannot create session token.")
    expires_at = int(time.time()) + (expires_in_days * 86400)
    data = f"{username}:{role}:{expires_at}"
    sig = hmac.new(
        session_secret.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return f"{username}.{role}.{expires_at}.{sig}"

def verify_session_token_with_role(token: str) -> Optional[Dict[str, str]]:
    """
    Verifies the HMAC signature and expiration of a session token.
    Supports both 4-part (username.role.expires_at.sig) and 3-part legacy tokens.
    Uses rsplit to correctly handle usernames containing dots (e.g. email addresses).
    Returns dict with {"username": username, "role": role} or None.
    """
    if not token or not isinstance(token, str):
        return None
    session_secret = settings.SESSION_SECRET or ""
    if not session_secret:
        return None
    
    # Try 4-part format first: username.role.expires_at.sig
    parts = token.rsplit(".", 3)
    if len(parts) == 4:
        username, role, expires_at_str, sig = parts
        try:
            expires_at = int(expires_at_str)
            if time.time() <= expires_at:
                expected_data = f"{username}:{role}:{expires_at}"
                expected_sig = hmac.new(
                    session_secret.encode("utf-8"),
                    expected_data.encode("utf-8"),
                    hashlib.sha256
                ).hexdigest()
                if secrets.compare_digest(sig, expected_sig):
                    return {"username": username, "role": role}
        except (ValueError, TypeError):
            pass

    # Fallback to legacy 3-part format: username.expires_at.sig
    parts_legacy = token.rsplit(".", 2)
    if len(parts_legacy) == 3:
        username, expires_at_str, sig = parts_legacy
        try:
            expires_at = int(expires_at_str)
            if time.time() <= expires_at:
                expected_data = f"{username}:{expires_at}"
                expected_sig = hmac.new(
                    session_secret.encode("utf-8"),
                    expected_data.encode("utf-8"),
                    hashlib.sha256
                ).hexdigest()
                if secrets.compare_digest(sig, expected_sig):
                    return {"username": username, "role": "admin"}
        except (ValueError, TypeError):
            pass

    return None

def verify_session_token(token: str) -> Optional[str]:
    """
    Backward-compatible verification returning username string if valid, None otherwise.
    """
    info = verify_session_token_with_role(token)
    return info["username"] if info else None

def get_user_role(username: str) -> str:
    """Resolves user role based on username."""
    clean_user = username.strip()
    if hasattr(settings, "VIEWER_USERNAME") and clean_user == settings.VIEWER_USERNAME.strip():
        return "viewer"
    return "admin"

def hash_password(password: str) -> str:
    """Generates a secure PBKDF2-HMAC-SHA256 password hash with a random 16-byte salt."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"pbkdf2:sha256:100000${salt}${key.hex()}"

def verify_password(plain_password: str, stored_credential: str) -> bool:
    """Verifies a plain password against either a PBKDF2 hash or fallback constant-time comparison."""
    if not stored_credential:
        return False
    if stored_credential.startswith("pbkdf2:sha256:"):
        try:
            parts = stored_credential.split("$")
            meta = parts[0]
            salt = parts[1]
            expected_hex = parts[2]
            iterations = int(meta.split(":")[-1])
            computed_key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), iterations)
            return secrets.compare_digest(computed_key.hex(), expected_hex)
        except Exception:
            return False
    return secrets.compare_digest(plain_password.strip(), stored_credential.strip())

def verify_login_credentials(username: str, password: str) -> bool:
    """Constant-time credential verification supporting both PBKDF2 hashes and secure secrets."""
    user_clean = username.strip()
    pass_clean = password.strip()
    
    # Check admin credentials
    admin_u_match = secrets.compare_digest(user_clean, settings.DASHBOARD_USERNAME.strip())
    admin_p_match = verify_password(pass_clean, settings.DASHBOARD_PASSWORD)
    if admin_u_match and admin_p_match:
        return True
        
    # Check viewer credentials if configured
    if hasattr(settings, "VIEWER_USERNAME") and hasattr(settings, "VIEWER_PASSWORD"):
        viewer_u_match = secrets.compare_digest(user_clean, settings.VIEWER_USERNAME.strip())
        viewer_p_match = verify_password(pass_clean, settings.VIEWER_PASSWORD)
        if viewer_u_match and viewer_p_match:
            return True
            
    return False

def verify_api_key(token: str) -> bool:
    """Verifies a bearer token or API key against settings.API_SECRET_KEY."""
    if not token or not getattr(settings, "API_SECRET_KEY", ""):
        return False
    return secrets.compare_digest(token.strip(), settings.API_SECRET_KEY.strip())

# --- IDOR & Parameter Validation ---
DOMAIN_SAFE_REGEX = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,12}$")

def validate_safe_domain(domain: str) -> str:
    """
    Validates domain string against IDOR / path traversal / injection attacks.
    Raises HTTPException(400) if invalid.
    """
    if not domain or not isinstance(domain, str):
        raise HTTPException(status_code=400, detail="Domain parameter is required and must be a valid string.")
    d = domain.strip().lower()
    # Reject traversal, control characters, null bytes, schemes
    if ".." in d or "/" in d or "\\" in d or "\x00" in d or "://" in d:
        raise HTTPException(status_code=400, detail="Invalid domain format: Traversal characters disallowed.")
    if not DOMAIN_SAFE_REGEX.match(d):
        raise HTTPException(status_code=400, detail="Invalid domain format.")
    return d

def validate_safe_id(entity_id: Any, name: str = "ID") -> int:
    """
    Validates integer identifier parameter.
    Raises HTTPException(400) if invalid.
    """
    try:
        val = int(entity_id)
        if val <= 0:
            raise ValueError()
        return val
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid {name} parameter: Must be a positive integer.")

from abc import ABC, abstractmethod

def validate_safe_path_within_root(file_subpath: str, allowed_root: str) -> str:
    """
    Validates that a file path is strictly contained within the allowed root directory.
    Prevents path traversal, directory escapes, and absolute path injection.
    Raises HTTPException(400) if malformed or escaping root.
    """
    if not file_subpath or not isinstance(file_subpath, str):
        raise HTTPException(status_code=400, detail="Invalid file path.")
    if "\x00" in file_subpath or ".." in file_subpath:
        raise HTTPException(status_code=400, detail="Path traversal sequences disallowed.")
    if os.path.isabs(file_subpath) or file_subpath.startswith(("/", "\\")) or (len(file_subpath) > 1 and file_subpath[1] == ":"):
        raise HTTPException(status_code=400, detail="Absolute paths disallowed.")
        
    abs_root = os.path.abspath(allowed_root)
    abs_file = os.path.abspath(os.path.join(abs_root, file_subpath.lstrip("/\\")))
    
    try:
        common = os.path.commonpath([abs_file, abs_root])
        if common != abs_root:
            raise HTTPException(status_code=403, detail="Access denied: Path escapes root directory.")
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: Cross-drive path disallowed.")
        
    return abs_file

# --- Rate Limiter Abstraction ---
class BaseRateLimiter(ABC):
    """Abstract interface for rate limiting across single-process or distributed deployments."""
    @abstractmethod
    async def is_allowed(self, key: str, max_requests: int, window_seconds: int = 60) -> Tuple[bool, int]:
        """Returns (is_allowed, retry_after_seconds)."""
        pass

    @abstractmethod
    async def reset(self) -> None:
        """Resets rate limit records (useful for test resets)."""
        pass

class SlidingWindowRateLimiter(BaseRateLimiter):
    """
    Thread-safe in-memory sliding window rate limiter.
    Note: In-memory rate limiting is scoped to a single process/container.
    For multi-replica deployments, replace with a RedisRateLimiter implementing BaseRateLimiter.
    """
    def __init__(self):
        self._records: Dict[str, List[float]] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str, max_requests: int, window_seconds: int = 60) -> Tuple[bool, int]:
        if not getattr(settings, "RATE_LIMIT_ENABLED", True):
            return True, 0

        now = time.time()
        cutoff = now - window_seconds
        
        async with self._lock:
            timestamps = self._records.get(key, [])
            valid_timestamps = [t for t in timestamps if t > cutoff]
            
            if len(valid_timestamps) >= max_requests:
                earliest = valid_timestamps[0]
                retry_after = max(1, int(earliest + window_seconds - now))
                self._records[key] = valid_timestamps
                return False, retry_after

            valid_timestamps.append(now)
            self._records[key] = valid_timestamps
            return True, 0

    async def reset(self) -> None:
        async with self._lock:
            self._records.clear()

InMemoryRateLimiter = SlidingWindowRateLimiter
rate_limiter: BaseRateLimiter = SlidingWindowRateLimiter()

# --- Webhook Replay Protection Abstraction ---
class BaseWebhookReplayProtection(ABC):
    """Abstract interface for webhook idempotency and replay protection."""
    @abstractmethod
    async def record_and_verify(self, unique_key: str) -> bool:
        """Returns True if event is fresh, False if already processed within window."""
        pass

    @abstractmethod
    async def reset(self) -> None:
        pass

class WebhookReplayProtection(BaseWebhookReplayProtection):
    """
    In-memory webhook replay cache tracking recent signatures/event IDs.
    Note: Scoped to single container process. For multi-replica clusters,
    replace with a RedisWebhookReplayProtection implementing BaseWebhookReplayProtection.
    """
    def __init__(self, window_seconds: int = 300):
        self._seen: Dict[str, float] = {}
        self.window_seconds = window_seconds
        self._lock = asyncio.Lock()

    async def record_and_verify(self, unique_key: str) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds
        
        async with self._lock:
            self._seen = {k: ts for k, ts in self._seen.items() if ts > cutoff}
            if unique_key in self._seen:
                return False  # Replay detected
            self._seen[unique_key] = now
            return True

    async def reset(self) -> None:
        async with self._lock:
            self._seen.clear()

InMemoryWebhookReplayProtection = WebhookReplayProtection
webhook_replay_guard: BaseWebhookReplayProtection = WebhookReplayProtection()

# --- Agent Input Safety & Prompt Injection Guard ---
class PromptInjectionGuard:
    """
    Detects prompt injection, jailbreak attempts, and safety bypass patterns
    in untrusted external text (emails, websites, transcripts, webhooks).
    """
    INJECTION_PATTERNS = [
        re.compile(r'(?i)\b(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|prior|system)\s+(?:instruction|prompt|rule|command)s?\b'),
        re.compile(r'(?i)\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be)\s+(?:DAN|developer\s+mode|jailbreak|unrestricted|god\s+mode)\b'),
        re.compile(r'(?i)\b(?:reveal|show|print|leak|output|export)\s+(?:all\s+)?(?:secret|password|api[_-]?key|system\s+prompt|instruction|credential)s?\b'),
        re.compile(r'(?i)\b(?:bypass|disable|turn\s+off|override)\s+(?:safety|compliance|commercial\s+floor|kill[_-]?switch|guardrail|rule|pricing)s?\b'),
        re.compile(r'(?i)\b(?:set|change|update|override)\s+(?:price|pricing|floor|fee)\s+(?:to\s+)?(?:\$0|0|free|zero)\b'),
        re.compile(r'(?i)\b(?:delete|drop|truncate|alter)\s+(?:database|table|record|prospect)s?\b'),
        re.compile(r'(?i)<script\b[^>]*>'),
        re.compile(r'(?i)(?:system\s*:\s*you\s+are|assistant\s*:\s*sure|human\s*:\s*ignore)'),
    ]

    @classmethod
    def scan_text(cls, text: str) -> Tuple[bool, Optional[str]]:
        """
        Scans text for prompt injection vectors.
        Returns (is_safe, threat_reason).
        """
        if not text or not isinstance(text, str):
            return True, None
            
        for pattern in cls.INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                return False, f"Prompt injection attack detected: '{match.group(0)}'"
                
        return True, None


