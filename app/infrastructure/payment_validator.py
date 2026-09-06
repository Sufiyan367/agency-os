import re
from typing import Dict, Any, Optional, List

VALID_CURRENCIES = {
    "USD", "GBP", "EUR", "CAD", "AUD", "INR", "SGD", "NZD", "AED", "CHF", "JPY"
}

class PaymentValidator:
    """
    Validates payment credentials, environment modes, currencies, and secrets.
    Strictly prevents secret leaking in logs, errors, or exceptions.
    """

    @staticmethod
    def validate_razorpay_configuration(
        key_id: str,
        key_secret: str,
        webhook_secret: str,
        mode: str,
        currency: str = "USD"
    ) -> Dict[str, Any]:
        errors: List[str] = []
        warnings: List[str] = []

        clean_mode = (mode or "").lower().strip()
        if clean_mode not in ("test", "live"):
            errors.append("Payment mode must be either 'test' or 'live'.")

        clean_kid = (key_id or "").strip()
        if not clean_kid:
            errors.append("Razorpay Key ID cannot be empty.")
        else:
            if clean_mode == "test" and not clean_kid.startswith("rzp_test_"):
                errors.append("Razorpay Key ID must begin with 'rzp_test_' when TEST mode is selected.")
            elif clean_mode == "live" and not clean_kid.startswith("rzp_live_"):
                errors.append("Razorpay Key ID must begin with 'rzp_live_' when LIVE mode is selected.")

        clean_ksec = (key_secret or "").strip()
        if not clean_ksec:
            errors.append("Razorpay Key Secret cannot be empty.")
        elif len(clean_ksec) < 8:
            errors.append("Razorpay Key Secret is too short (must be at least 8 characters).")

        clean_whsec = (webhook_secret or "").strip()
        if not clean_whsec:
            errors.append("Razorpay Webhook Secret cannot be empty.")
        elif len(clean_whsec) < 6:
            errors.append("Razorpay Webhook Secret is too short (must be at least 6 characters).")

        clean_curr = (currency or "").upper().strip()
        if not clean_curr or clean_curr not in VALID_CURRENCIES:
            errors.append(f"Unsupported or invalid currency code: '{currency}'. Supported: {', '.join(sorted(VALID_CURRENCIES))}")

        if clean_mode == "live":
            warnings.append("You are configuring real payment infrastructure. No payment will be created during this setup.")

        return {
            "valid": len(errors) == 0,
            "mode": clean_mode,
            "currency": clean_curr,
            "key_id": clean_kid,
            "errors": errors,
            "warnings": warnings,
            "masked_summary": {
                "provider": "razorpay",
                "mode": clean_mode.upper(),
                "currency": clean_curr,
                "key_id_masked": f"{clean_kid[:8]}••••••••" if len(clean_kid) > 8 else "••••••••",
                "key_secret_status": "PRESENT" if clean_ksec else "ABSENT",
                "webhook_secret_status": "PRESENT" if clean_whsec else "ABSENT"
            }
        }

payment_validator = PaymentValidator()
