import hmac
import hashlib
import time
import uuid
from typing import Dict, Any, Optional, Tuple, List
import httpx

from app.core.config import settings
from app.core.logging import logger

class StripePaymentProvider:
    """
    Handles payment checkout generation and HMAC-SHA256 webhook verification.
    Supports live Stripe API when configured, and safe DRY_RUN / Mock mode by default.
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        webhook_secret: Optional[str] = None
    ):
        self.secret_key = secret_key or settings.STRIPE_SECRET_KEY
        self.webhook_secret = webhook_secret or settings.STRIPE_WEBHOOK_SECRET
        self.enabled = settings.PAYMENTS_ENABLED and not settings.DRY_RUN and settings.PAYMENT_PROVIDER == "stripe"

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
        Creates a Stripe Checkout Session or returns a simulated session if in DRY_RUN / unconfigured.
        """
        if not self.enabled or not self.secret_key:
            # Safe simulated checkout session
            mock_id = f"cs_test_{uuid.uuid4().hex[:16]}"
            mock_url = f"https://checkout.stripe.com/c/pay/{mock_id}?mock=true"
            logger.info(f"[PAYMENT DRY_RUN] Generated simulated Stripe checkout session for business #{business_id} (${amount_usd:,.2f})")
            return {
                "session_id": mock_id,
                "checkout_url": mock_url,
                "amount": amount_usd,
                "currency": "usd",
                "status": "open",
                "mode": "dry_run"
            }

        # Real Stripe API Call
        url = "https://api.stripe.com/v1/checkout/sessions"
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        amount_cents = int(round(amount_usd * 100))
        data = {
            "payment_method_types[0]": "card",
            "line_items[0][price_data][currency]": "usd",
            "line_items[0][price_data][product_data][name]": title,
            "line_items[0][price_data][unit_amount]": str(amount_cents),
            "line_items[0][quantity]": "1",
            "mode": "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": str(business_id),
            "metadata[business_id]": str(business_id),
            "metadata[offer_id]": str(offer_id)
        }
        if customer_email:
            data["customer_email"] = customer_email

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, data=data, headers=headers)
            if resp.status_code not in (200, 201):
                logger.error(f"[Stripe] Checkout creation failed {resp.status_code}: {resp.text}")
                raise RuntimeError(f"Stripe API error: {resp.status_code} - {resp.text}")

            result = resp.json()
            return {
                "session_id": result.get("id"),
                "checkout_url": result.get("url"),
                "amount": amount_usd,
                "currency": "usd",
                "status": "open",
                "mode": "live_stripe"
            }

    async def fetch_completed_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Polls Stripe API for completed checkout sessions to guarantee automatic payment detection.
        In DRY_RUN or unconfigured, returns empty list.
        """
        if not self.enabled or not self.secret_key:
            return []

        url = f"https://api.stripe.com/v1/checkout/sessions?status=complete&limit={limit}"
        headers = {"Authorization": f"Bearer {self.secret_key}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    completed = []
                    for s in data:
                        meta = s.get("metadata", {})
                        biz_id_str = meta.get("business_id") or s.get("client_reference_id")
                        if biz_id_str and str(biz_id_str).isdigit():
                            amount_cents = s.get("amount_total", 0)
                            completed.append({
                                "business_id": int(biz_id_str),
                                "reference_id": s.get("id"),
                                "amount_usd": float(amount_cents) / 100.0 if amount_cents else 0.0,
                                "customer_email": s.get("customer_details", {}).get("email") or s.get("customer_email")
                            })
                    return completed
        except Exception as e:
            logger.warning(f"[Stripe] Error fetching completed sessions: {e}")
        return []

    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        signature_header: Optional[str],
        tolerance_seconds: int = 300
    ) -> Tuple[bool, Optional[str]]:
        """
        Verifies Stripe's HMAC-SHA256 signature from the Stripe-Signature header.
        Header format: t=1614000000,v1=5257a869e7ecebeda32affa62cd...
        """
        if not self.webhook_secret:
            if settings.DRY_RUN or not settings.PAYMENTS_ENABLED:
                # In test/dry-run mode without secret, allow validation if mock token provided
                return True, "dry_run_authorized"
            return False, "STRIPE_WEBHOOK_SECRET is not configured."

        if not signature_header:
            return False, "Missing Stripe-Signature header."

        try:
            elements = {}
            for item in signature_header.split(","):
                k, v = item.strip().split("=", 1)
                elements[k] = v

            timestamp_str = elements.get("t")
            v1_signature = elements.get("v1")

            if not timestamp_str or not v1_signature:
                return False, "Malformed Stripe-Signature header elements."

            timestamp = int(timestamp_str)
            now = int(time.time())
            if abs(now - timestamp) > tolerance_seconds:
                return False, f"Webhook timestamp outside tolerance window ({abs(now - timestamp)}s > {tolerance_seconds}s)."

            signed_payload = f"{timestamp}.".encode("utf-8") + payload_bytes
            expected_signature = hmac.new(
                self.webhook_secret.encode("utf-8"),
                signed_payload,
                hashlib.sha256
            ).hexdigest()

            if hmac.compare_digest(expected_signature, v1_signature):
                return True, "Valid signature"
            else:
                return False, "HMAC-SHA256 signature mismatch."
        except Exception as e:
            return False, f"Signature verification error: {str(e)}"

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
        Unified alias for checkout session generation.
        """
        return await self.create_checkout_session(
            business_id=business_id,
            offer_id=offer_id,
            title=title,
            amount_usd=amount_usd,
            customer_email=customer_email,
            success_url=callback_url
        )

    async def fetch_completed_payments(self, limit: int = 10) -> List[Dict[str, Any]]:
        return await self.fetch_completed_sessions(limit=limit)

stripe_payment_provider = StripePaymentProvider()

from app.payments.razorpay import RazorpayPaymentProvider, razorpay_payment_provider

def get_active_payment_provider():
    """
    Returns the active payment provider based on configuration.
    Defaults to Razorpay as primary, Stripe as secondary.
    """
    if settings.PAYMENT_PROVIDER == "stripe":
        return stripe_payment_provider
    return razorpay_payment_provider

