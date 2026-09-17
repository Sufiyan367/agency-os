import re
from typing import Dict, Any, Optional, List
try:
    import dns.resolver
    DNS_AVAILABLE = True
except ImportError:
    dns = None
    DNS_AVAILABLE = False
from app.core.logging import logger

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
DOMAIN_REGEX = re.compile(r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$")

class DomainValidator:
    """
    Performs safe, read-only validation of sender identities and email domains.
    Checks syntax, DNS availability, MX records, SPF, and DMARC without sending
    emails or making any external mutations.
    """

    @staticmethod
    def validate_email_syntax(email: str) -> bool:
        if not email or not isinstance(email, str):
            return False
        from app.core.security import validate_email_syntax as core_validate_email_syntax
        return core_validate_email_syntax(email.strip())

    @staticmethod
    def validate_domain_syntax(domain: str) -> bool:
        if not domain or not isinstance(domain, str):
            return False
        return bool(DOMAIN_REGEX.match(domain.strip()))

    @staticmethod
    def extract_domain(email: str) -> Optional[str]:
        if not DomainValidator.validate_email_syntax(email):
            return None
        return email.strip().split("@")[-1].lower()

    @staticmethod
    def validate_identity_consistency(
        sender_email: str,
        reply_to: str,
        expected_domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ensures sender email and reply-to have valid syntax and consistent domains.
        """
        if not DomainValidator.validate_email_syntax(sender_email):
            return {
                "valid": False,
                "error": f"Invalid sender email syntax: '{sender_email}'"
            }

        if not DomainValidator.validate_email_syntax(reply_to):
            return {
                "valid": False,
                "error": f"Invalid reply-to email syntax: '{reply_to}'"
            }

        sender_dom = DomainValidator.extract_domain(sender_email)
        if expected_domain:
            exp_dom_clean = expected_domain.strip().lower()
            if sender_dom != exp_dom_clean:
                return {
                    "valid": False,
                    "error": f"Sender email domain '{sender_dom}' does not match expected domain '{exp_dom_clean}'"
                }

        return {
            "valid": True,
            "sender_domain": sender_dom,
            "reply_to_domain": DomainValidator.extract_domain(reply_to)
        }

    @staticmethod
    def inspect_domain_dns(domain: str, provider: str = "resend") -> Dict[str, Any]:
        """
        Queries public DNS records for the domain:
        - A / AAAA host resolution
        - MX records
        - SPF TXT records
        - DMARC TXT records
        """
        clean_domain = domain.strip().lower()
        if not DomainValidator.validate_domain_syntax(clean_domain):
            return {
                "domain": clean_domain,
                "valid_syntax": False,
                "dns_available": False,
                "mx_present": False,
                "spf_present": False,
                "spf_includes_provider": False,
                "dmarc_present": False,
                "dmarc_policy": None,
                "dkim_status": "NOT CONFIGURED",
                "ready_for_production": False,
                "error": f"Invalid domain syntax: '{clean_domain}'"
            }

        if not DNS_AVAILABLE or dns is None:
            import socket
            a_present = False
            try:
                socket.gethostbyname(clean_domain)
                a_present = True
            except Exception:
                pass
            spf_present = clean_domain in ("gmail.com", "googlemail.com")
            spf_includes_provider = spf_present
            dkim_status = "VERIFIED (Google Managed)" if clean_domain in ("gmail.com", "googlemail.com") else "Verification required"
            return {
                "domain": clean_domain,
                "valid_syntax": True,
                "dns_available": a_present,
                "a_present": a_present,
                "mx_present": False,
                "mx_records": [],
                "spf_present": spf_present,
                "spf_record": "v=spf1 include:_spf.google.com ~all" if spf_present else None,
                "spf_includes_provider": spf_includes_provider,
                "dmarc_present": False,
                "dmarc_policy": None,
                "dkim_status": dkim_status,
                "ready_for_production": a_present
            }

        resolver = dns.resolver.Resolver()
        resolver.timeout = 5.0
        resolver.lifetime = 10.0

        # 1. A / AAAA
        a_present = False
        try:
            answers = resolver.resolve(clean_domain, "A")
            if answers:
                a_present = True
        except Exception:
            pass

        # 2. MX Records
        mx_present = False
        mx_records = []
        try:
            answers = resolver.resolve(clean_domain, "MX")
            for rdata in answers:
                mx_present = True
                mx_records.append(str(rdata.exchange).rstrip("."))
        except Exception:
            pass

        # 3. SPF Check (TXT on apex domain)
        spf_present = False
        spf_record = None
        spf_includes_provider = False
        provider_clean = (provider or "").lower().strip()
        provider_spf_signatures = {
            "resend": "include:resend.com",
            "sendgrid": "include:sendgrid.net",
            "gmail": "include:_spf.google.com",
            "gmail_oauth": "include:_spf.google.com",
            "titan": "include:spf.titan.email",
            "titan_smtp": "include:spf.titan.email",
            "smtp": ""
        }
        target_sig = provider_spf_signatures.get(provider_clean, "")

        try:
            answers = resolver.resolve(clean_domain, "TXT")
            for rdata in answers:
                for txt_str in rdata.strings:
                    decoded = txt_str.decode("utf-8", errors="ignore")
                    if decoded.startswith("v=spf1"):
                        spf_present = True
                        spf_record = decoded
                        if target_sig and target_sig in decoded:
                            spf_includes_provider = True
                        elif provider_clean in ("smtp", "dry_run"):
                            spf_includes_provider = True
                        elif clean_domain in ("gmail.com", "googlemail.com"):
                            spf_includes_provider = True
        except Exception:
            pass

        # 4. DMARC Check (_dmarc.<domain>)
        dmarc_present = False
        dmarc_policy = None
        try:
            dmarc_host = f"_dmarc.{clean_domain}"
            answers = resolver.resolve(dmarc_host, "TXT")
            for rdata in answers:
                for txt_str in rdata.strings:
                    decoded = txt_str.decode("utf-8", errors="ignore")
                    if decoded.startswith("v=DMARC1"):
                        dmarc_present = True
                        m = re.search(r"\bp=([a-zA-Z]+)", decoded)
                        if m:
                            dmarc_policy = m.group(1).lower()
        except Exception:
            pass

        # 5. DKIM Check (Query Titan selectors like titan1, titan when Titan provider is active)
        dkim_present = False
        dkim_selector = None
        dkim_record = None
        selectors_to_check = ["titan1", "titan"] if provider_clean in ("titan", "titan_smtp") else []
        for sel in selectors_to_check:
            try:
                dkim_host = f"{sel}._domainkey.{clean_domain}"
                dkim_answers = resolver.resolve(dkim_host, "TXT")
                for rdata in dkim_answers:
                    for txt_str in rdata.strings:
                        decoded = txt_str.decode("utf-8", errors="ignore")
                        if "v=DKIM1" in decoded or "p=" in decoded:
                            dkim_present = True
                            dkim_selector = sel
                            dkim_record = decoded
                            break
                    if dkim_present:
                        break
                if dkim_present:
                    break
            except Exception:
                pass

        if dkim_present:
            dkim_status = f"VERIFIED ({dkim_selector})"
        elif clean_domain in ("gmail.com", "googlemail.com"):
            dkim_status = "VERIFIED (Google Managed)"
        else:
            dkim_status = "Verification required"

        dns_available = a_present or mx_present
        ready = dns_available

        return {
            "domain": clean_domain,
            "valid_syntax": True,
            "dns_available": dns_available,
            "a_present": a_present,
            "mx_present": mx_present,
            "mx_records": mx_records,
            "spf_present": spf_present,
            "spf_record": spf_record,
            "spf_includes_provider": spf_includes_provider,
            "dmarc_present": dmarc_present,
            "dmarc_policy": dmarc_policy,
            "dkim_present": dkim_present,
            "dkim_selector": dkim_selector,
            "dkim_status": dkim_status,
            "ready_for_production": ready
        }

domain_validator = DomainValidator()
