import hmac
import hashlib
import time
import uuid
import secrets
from typing import Dict, Any, Optional, Tuple, List
import httpx

from app.core.config import settings
from app.core.logging import logger

class RazorpayPaymentProvider:
    """
    Production Razorpay Payment Gateway integration.
    Supports Razorpay Payment Links API, HMAC-SHA256 webhook signature verification,
    and automated payment status detection with safe DRY_RUN fallback.
    """

    def __init__(
        self,
        key_id: Optional[str] = None,
        key_secret: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        currency: Optional[str] = None
    ):
        self.key_id = key_id or settings.RAZORPAY_KEY_ID
        self.key_secret = key_secret or settings.RAZORPAY_KEY_SECRET
        self.webhook_secret = webhook_secret or settings.RAZORPAY_WEBHOOK_SECRET
        self.currency = (currency or settings.RAZORPAY_CURRENCY or "USD").upper()
        self.enabled = (
            settings.PAYMENTS_ENABLED
            and not settings.DRY_RUN
            and settings.PAYMENT_PROVIDER == "razorpay"
        )

    async def create_payment_link(
        self,
        business_id: int,
        offer_id: int,
        title: str,
        amount_usd: float,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None,
        callback_url: str = "http://localhost:8000/?payment=success"
    ) -> Dict[str, Any]:
        """
        Creates a Razorpay Standard Payment Link or returns a simulated link in DRY_RUN mode.
        """
        # 1. Safe Dry Run / Simulation Mode
        if not self.enabled or not self.key_id or not self.key_secret:
            mock_id = f"plink_test_{uuid.uuid4().hex[:14]}"
            mock_url = f"https://rzp.io/i/{mock_id}"
            logger.info(
                f"[RAZORPAY DRY_RUN] Generated simulated Razorpay Payment Link for business #{business_id} "
                f"(${amount_usd:,.2f} {self.currency})"
            )
            return {
                "payment_link_id": mock_id,
                "checkout_url": mock_url,
                "amount": amount_usd,
                "currency": self.currency,
                "status": "created",
                "provider": "razorpay",
                "mode": "dry_run"
            }

        # 2. Live Razorpay Payment Links REST API
        url = "https://api.razorpay.com/v1/payment_links"
        amount_subunits = int(round(amount_usd * 100))  # Cents or Paise

        payload: Dict[str, Any] = {
            "amount": amount_subunits,
            "currency": self.currency,
            "accept_partial": False,
            "description": f"{title} — Project Retainer (Business #{business_id})",
            "customer": {
                "name": customer_name or f"Business #{business_id}",
                "email": customer_email or "billing@example.com",
            },
            "notify": {
                "sms": bool(customer_phone),
                "email": bool(customer_email)
            },
            "reminder_enable": True,
            "notes": {
                "business_id": str(business_id),
                "offer_id": str(offer_id),
                "source": "autonomous_agency",
                "service": title
            },
            "callback_url": callback_url,
            "callback_method": "get"
        }

        if customer_phone:
            payload["customer"]["contact"] = customer_phone

        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(
                url,
                json=payload,
                auth=(self.key_id, self.key_secret)
            )

            if resp.status_code not in (200, 201):
                logger.error(f"[Razorpay] Payment link creation failed {resp.status_code}: {resp.text}")
                raise RuntimeError(f"Razorpay API error: {resp.status_code} - {resp.text}")

            result = resp.json()
            return {
                "payment_link_id": result.get("id"),
                "checkout_url": result.get("short_url"),
                "amount": amount_usd,
                "currency": self.currency,
                "status": result.get("status", "created"),
                "provider": "razorpay",
                "mode": "live_razorpay"
            }

    async def create_checkout_session(
        self,
        business_id: int,
        offer_id: int,
        title: str,
        amount_usd: float,
        customer_email: Optional[str] = None,
        success_url: str = "http://localhost:8000/?payment=success",
        cancel_url: str = "http://localhost:8000/?payment=cancelled"
    ) -> Dict[str, Any]:
        """
        Unified alias for checkout session generation.
        """
        return await self.create_payment_link(
            business_id=business_id,
            offer_id=offer_id,
            title=title,
            amount_usd=amount_usd,
            customer_email=customer_email,
            callback_url=success_url
        )

    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        signature_header: Optional[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Verifies Razorpay's HMAC-SHA256 signature from the X-Razorpay-Signature header.
        Signature: hmac_sha256(webhook_secret, raw_payload_bytes)
        """
        if not self.webhook_secret:
            if settings.DRY_RUN or not settings.PAYMENTS_ENABLED:
                # In test or dry-run mode without configured secret, allow authorized test runs
                return True, "dry_run_authorized"
            return False, "RAZORPAY_WEBHOOK_SECRET is not configured."

        if not signature_header:
            return False, "Missing X-Razorpay-Signature header."

        try:
            expected_signature = hmac.new(
                self.webhook_secret.encode("utf-8"),
                payload_bytes,
                hashlib.sha256
            ).hexdigest()

            if secrets.compare_digest(expected_signature, signature_header):
                return True, "Valid signature"
            else:
                return False, "HMAC-SHA256 signature mismatch."
        except Exception as e:
            return False, f"Signature verification error: {str(e)}"

    async def fetch_paid_links(self, limit: int = 15) -> List[Dict[str, Any]]:
        """
        Polls Razorpay API for completed/paid payment links.
        Enables the autonomous background worker to detect confirmed payments even without webhooks.
        """
        if not self.enabled or not self.key_id or not self.key_secret:
            return []

        url = f"https://api.razorpay.com/v1/payment_links?limit={limit}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, auth=(self.key_id, self.key_secret))
                if resp.status_code == 200:
                    data = resp.json().get("payment_links", [])
                    paid_links = []
                    for link in data:
                        if link.get("status") == "paid":
                            notes = link.get("notes", {})
                            biz_id_str = notes.get("business_id")
                            if biz_id_str and str(biz_id_str).isdigit():
                                subunits = link.get("amount_paid", 0)
                                paid_links.append({
                                    "business_id": int(biz_id_str),
                                    "reference_id": link.get("id"),
                                    "amount_usd": float(subunits) / 100.0 if subunits else 0.0,
                                    "customer_email": link.get("customer", {}).get("email"),
                                    "gateway": "razorpay"
                                })
                    return paid_links
        except Exception as e:
            logger.warning(f"[Razorpay] Error fetching paid links: {e}")
        return []

    async def fetch_completed_payments(self, limit: int = 15) -> List[Dict[str, Any]]:
        return await self.fetch_paid_links(limit=limit)

razorpay_payment_provider = RazorpayPaymentProvider()

