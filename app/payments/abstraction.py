import hmac
import hashlib
import uuid
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

class BasePaymentProvider(ABC):
    """
    Abstract payment gateway provider.
    Enforces unified interfaces for creating orders, verifying webhooks,
    and fetching transaction details across mock and live gateways.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    async def create_payment_order(
        self,
        deal_id: int,
        proposal_id: int,
        amount_usd: float,
        currency: str = "USD",
        payment_type: str = "ADVANCE",
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Creates a payment order with the gateway provider."""
        pass

    @abstractmethod
    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        signature: Optional[str]
    ) -> Tuple[bool, str]:
        """Validates the cryptographic HMAC signature of incoming webhooks."""
        pass

    @abstractmethod
    async def fetch_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Fetches payment details and status from the gateway."""
        pass


class MockPaymentProvider(BasePaymentProvider):
    """
    Deterministic mock payment provider for automated testing and offline simulation.
    Never transmits requests over the network; produces verifiable signatures using a mock secret.
    """

    def __init__(self, webhook_secret: str = "mock_webhook_secret_key_2026"):
        self.mock_secret = webhook_secret

    @property
    def provider_name(self) -> str:
        return "mock_payment_provider"

    async def create_payment_order(
        self,
        deal_id: int,
        proposal_id: int,
        amount_usd: float,
        currency: str = "USD",
        payment_type: str = "ADVANCE",
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        order_id = f"order_mock_{uuid.uuid4().hex[:14]}"
        checkout_url = f"https://rzp.io/mock/{order_id}"
        
        logger.info(
            f"[MockPaymentProvider] Created simulated payment order '{order_id}' "
            f"for Deal #{deal_id} / Proposal #{proposal_id} (${amount_usd:,.2f} {currency}, {payment_type})"
        )

        return {
            "order_id": order_id,
            "checkout_url": checkout_url,
            "amount": amount_usd,
            "currency": currency.upper(),
            "payment_type": payment_type,
            "status": "created",
            "provider": "razorpay_mock",
            "is_mock": True,
            "notes": {
                "deal_id": str(deal_id),
                "proposal_id": str(proposal_id),
                **(metadata or {})
            }
        }

    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        signature: Optional[str]
    ) -> Tuple[bool, str]:
        if not signature:
            return False, "Missing Razorpay webhook signature header (x-razorpay-signature)"

        computed = hmac.new(self.mock_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
        if hmac.compare_digest(computed, signature):
            return True, "Valid signature"
        return False, f"Signature mismatch: computed={computed}, received={signature}"

    def generate_mock_webhook_payload(
        self,
        order_id: str,
        payment_id: str,
        amount_usd: float,
        currency: str = "USD",
        deal_id: Optional[int] = None,
        proposal_id: Optional[int] = None,
        event: str = "payment.captured"
    ) -> Tuple[bytes, str]:
        """Helper to generate signed mock webhook payload for testing."""
        amount_subunits = int(round(amount_usd * 100))
        payload_dict = {
            "entity": "event",
            "account_id": "acc_mock_agency",
            "event": event,
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": order_id,
                        "amount": amount_subunits,
                        "currency": currency.upper(),
                        "status": "captured" if event == "payment.captured" else "failed",
                        "method": "card",
                        "notes": {
                            "deal_id": str(deal_id) if deal_id else "",
                            "proposal_id": str(proposal_id) if proposal_id else ""
                        }
                    }
                }
            }
        }
        raw_bytes = json.dumps(payload_dict).encode("utf-8")
        sig = hmac.new(self.mock_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
        return raw_bytes, sig

    async def fetch_payment_status(self, payment_id: str) -> Dict[str, Any]:
        return {
            "id": payment_id,
            "status": "captured",
            "is_mock": True
        }


class RealRazorpayPaymentProvider(BasePaymentProvider):
    """
    Production Razorpay API adapter.
    Reads credentials strictly from environment variables without hardcoded secrets.
    Calls official Razorpay Orders API and verifies cryptographic signatures.
    """

    def __init__(
        self,
        key_id: Optional[str] = None,
        key_secret: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        currency: str = "USD"
    ):
        self.key_id = key_id or settings.RAZORPAY_KEY_ID
        self.key_secret = key_secret or settings.RAZORPAY_KEY_SECRET
        self.webhook_secret = webhook_secret or settings.RAZORPAY_WEBHOOK_SECRET
        self.currency = currency.upper()

    @property
    def provider_name(self) -> str:
        return "razorpay"

    async def create_payment_order(
        self,
        deal_id: int,
        proposal_id: int,
        amount_usd: float,
        currency: str = "USD",
        payment_type: str = "ADVANCE",
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not self.key_id or not self.key_secret:
            raise ValueError(
                "Missing Razorpay live credentials. Ensure RAZORPAY_KEY_ID and "
                "RAZORPAY_KEY_SECRET environment variables are set."
            )

        url = "https://api.razorpay.com/v1/orders"
        amount_subunits = int(round(amount_usd * 100))
        receipt_id = f"deal_{deal_id}_prop_{proposal_id}_{payment_type.lower()}"

        payload = {
            "amount": amount_subunits,
            "currency": currency.upper(),
            "receipt": receipt_id[:40],
            "notes": {
                "deal_id": str(deal_id),
                "proposal_id": str(proposal_id),
                "payment_type": payment_type,
                **(metadata or {})
            }
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                json=payload,
                auth=(self.key_id, self.key_secret)
            )
            if resp.status_code not in (200, 201):
                logger.error(f"[Razorpay] Order creation failed ({resp.status_code}): {resp.text}")
                raise RuntimeError(f"Razorpay order creation failed: {resp.text}")

            data = resp.json()
            order_id = data["id"]
            checkout_url = f"https://checkout.razorpay.com/v1/checkout.js?order_id={order_id}"

            return {
                "order_id": order_id,
                "checkout_url": checkout_url,
                "amount": amount_usd,
                "currency": currency.upper(),
                "payment_type": payment_type,
                "status": data.get("status", "created"),
                "provider": "razorpay",
                "is_mock": False,
                "raw_response": data
            }

    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        signature: Optional[str]
    ) -> Tuple[bool, str]:
        if not self.webhook_secret:
            return False, "RAZORPAY_WEBHOOK_SECRET environment variable is not configured."
        if not signature:
            return False, "Missing Razorpay webhook signature header (x-razorpay-signature)"

        computed = hmac.new(self.webhook_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
        if hmac.compare_digest(computed, signature):
            return True, "Valid signature"
        return False, "Signature mismatch"

    async def fetch_payment_status(self, payment_id: str) -> Dict[str, Any]:
        if not self.key_id or not self.key_secret:
            raise ValueError("Missing Razorpay credentials.")
        url = f"https://api.razorpay.com/v1/payments/{payment_id}"
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(url, auth=(self.key_id, self.key_secret))
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to fetch payment {payment_id}: {resp.text}")
            return resp.json()


def get_payment_provider() -> BasePaymentProvider:
    """
    Returns the configured payment provider instance.
    Defaults strictly to MockPaymentProvider when PAYMENT_DRY_RUN=True or DRY_RUN=True.
    """
    if settings.PAYMENT_DRY_RUN or settings.DRY_RUN or not settings.PAYMENTS_ENABLED:
        return MockPaymentProvider()
    return RealRazorpayPaymentProvider()
