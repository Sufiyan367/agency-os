import ipaddress
import re
import socket
from urllib.parse import urlparse
from typing import Tuple

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
