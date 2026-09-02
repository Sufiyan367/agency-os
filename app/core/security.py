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
from app.core.config import settings

def create_session_token(username: str, expires_in_days: int = 14) -> str:
    """Creates a cryptographically signed HMAC-SHA256 session token."""
    expires_at = int(time.time()) + (expires_in_days * 86400)
    data = f"{username}:{expires_at}"
    sig = hmac.new(
        settings.SESSION_SECRET.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return f"{username}.{expires_at}.{sig}"

def verify_session_token(token: str) -> Optional[str]:
    """
    Verifies the HMAC signature and expiration of a session token.
    Returns username if valid, None if expired, tampered, or invalid.
    """
    if not token or not isinstance(token, str):
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    username, expires_at_str, sig = parts
    try:
        expires_at = int(expires_at_str)
    except ValueError:
        return None

    if time.time() > expires_at:
        return None  # Expired

    expected_data = f"{username}:{expires_at}"
    expected_sig = hmac.new(
        settings.SESSION_SECRET.encode("utf-8"),
        expected_data.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    if secrets.compare_digest(sig, expected_sig):
        return username
    return None

def verify_login_credentials(username: str, password: str) -> bool:
    """Constant-time credential verification against configured dashboard credentials."""
    user_match = secrets.compare_digest(username.strip(), settings.DASHBOARD_USERNAME.strip())
    pass_match = secrets.compare_digest(password.strip(), settings.DASHBOARD_PASSWORD.strip())
    return user_match and pass_match

def verify_api_key(token: str) -> bool:
    """Verifies a bearer token or API key against settings.API_SECRET_KEY."""
    if not token:
        return False
    return secrets.compare_digest(token.strip(), settings.API_SECRET_KEY.strip())

