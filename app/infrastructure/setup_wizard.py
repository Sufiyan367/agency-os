import os
import sys
from typing import Dict, Any, Optional, Callable
from rich.console import Console
from rich.prompt import Prompt, Confirm

from app.core.config import settings
from app.core.settings_manager import SettingsManager
from app.infrastructure.domain_validator import domain_validator
from app.infrastructure.payment_validator import payment_validator
from app.core.logging import logger

console = Console()

class SetupWizard:
    """
    Production Email & Payment Infrastructure Setup Wizard.
    Collects real credentials securely, validates them safely, masks all secrets,
    requires explicit pre-save operator confirmation, and enforces strict post-save
    safety gates (RESEARCH_ONLY=true, EMAIL_DRY_RUN=true, PAYMENTS_ENABLED=false).
    """

    def __init__(
        self,
        prompt_fn: Optional[Callable[[str, Any], str]] = None,
        password_fn: Optional[Callable[[str], str]] = None,
        confirm_fn: Optional[Callable[[str], bool]] = None,
        custom_console: Optional[Console] = None
    ):
        self.prompt_fn = prompt_fn or (lambda msg, default="": Prompt.ask(msg, default=default))
        self.password_fn = password_fn or (lambda msg: Prompt.ask(msg, password=True))
        self.confirm_fn = confirm_fn or (lambda msg: Confirm.ask(msg, default=False))
        self.console = custom_console or console

    def run(self) -> Dict[str, Any]:
        """
        Executes the interactive setup wizard flow.
        Returns a dictionary summary of the result.
        """
        self.console.print("\n[bold cyan]==================================================[/bold cyan]")
        self.console.print("[bold white]JARVIS // AG — PRODUCTION INFRASTRUCTURE SETUP WIZARD[/bold white]")
        self.console.print("[bold cyan]==================================================[/bold cyan]")
        self.console.print("[dim]This wizard configures real provider credentials safely without activating live outreach or live charges.[/dim]\n")

        # --------------------------------------------------
        # 1. DISPLAY CURRENT CONFIGURATION
        # --------------------------------------------------
        self.console.print("[bold yellow]CURRENT CONFIGURATION:[/bold yellow]")
        self.console.print(f"  Provider:    {settings.EMAIL_PROVIDER}")
        self.console.print(f"  Sender:      {settings.EMAIL_FROM}")
        self.console.print(f"  Reply-To:    {settings.EMAIL_REPLY_TO}")
        sender_dom = domain_validator.extract_domain(settings.EMAIL_FROM) or "unknown"
        self.console.print(f"  Domain:      {sender_dom}")
        curr_email_cred = "PRESENT" if (
            (settings.EMAIL_PROVIDER == "resend" and settings.RESEND_API_KEY) or
            (settings.EMAIL_PROVIDER == "sendgrid" and settings.SENDGRID_API_KEY) or
            (settings.EMAIL_PROVIDER == "smtp" and settings.SMTP_HOST and settings.SMTP_USER)
        ) else "ABSENT"
        self.console.print(f"  Credentials: {curr_email_cred}\n")

        # --------------------------------------------------
        # 2. EMAIL SETUP
        # --------------------------------------------------
        self.console.print("[bold green]--- 1. EMAIL PROVIDER SETUP ---[/bold green]")
        self.console.print("Select Email Provider:")
        self.console.print("  [bold]A[/bold]. Resend [green](Recommended)[/green]")
        self.console.print("  [bold]B[/bold]. SMTP")
        self.console.print("  [bold]C[/bold]. SendGrid")

        prov_choice = self.prompt_fn("Select provider [A/B/C]", "A").strip().upper()
        provider_map = {"A": "resend", "B": "smtp", "C": "sendgrid", "RESEND": "resend", "SMTP": "smtp", "SENDGRID": "sendgrid"}
        selected_provider = provider_map.get(prov_choice)
        if not selected_provider:
            self.console.print(f"[bold red]Invalid provider selection: '{prov_choice}'. Setup aborted.[/bold red]")
            raise ValueError(f"Invalid provider selection: '{prov_choice}'")

        email_config: Dict[str, Any] = {"provider": selected_provider}

        if selected_provider == "resend":
            api_key = self.password_fn("Enter Resend API Key (starts with 're_')").strip()
            if not api_key:
                raise ValueError("Resend API key cannot be empty.")
            if not api_key.startswith("re_"):
                self.console.print("[yellow]Warning: Resend API keys usually begin with 're_'.[/yellow]")

            sender_email = self.prompt_fn("Enter real sender email address (e.g. outreach@yourdomain.com)").strip()
            if not domain_validator.validate_email_syntax(sender_email):
                raise ValueError(f"Invalid sender email syntax: '{sender_email}'")

            from_name = self.prompt_fn("Enter sender display name", "Elena Vance | Digital Strategy Director").strip()
            if not from_name:
                from_name = "Elena Vance | Digital Strategy Director"

            reply_to = self.prompt_fn("Enter reply-to email address", sender_email).strip()
            if not domain_validator.validate_email_syntax(reply_to):
                raise ValueError(f"Invalid reply-to email syntax: '{reply_to}'")

            # Identity consistency check
            consistency = domain_validator.validate_identity_consistency(sender_email, reply_to)
            if not consistency["valid"]:
                raise ValueError(consistency["error"])

            email_config.update({
                "api_key": api_key,
                "sender_email": sender_email,
                "from_name": from_name,
                "reply_to": reply_to,
                "domain": consistency["sender_domain"]
            })

        elif selected_provider == "smtp":
            smtp_host = self.prompt_fn("Enter SMTP Host (e.g. smtp.gmail.com)").strip()
            if not smtp_host:
                raise ValueError("SMTP host cannot be empty.")

            smtp_port_raw = self.prompt_fn("Enter SMTP Port", "587").strip()
            try:
                smtp_port = int(smtp_port_raw)
            except ValueError:
                raise ValueError(f"Invalid SMTP port: '{smtp_port_raw}'")

            smtp_user = self.prompt_fn("Enter SMTP Username").strip()
            if not smtp_user:
                raise ValueError("SMTP username cannot be empty.")

            smtp_pass = self.password_fn("Enter SMTP Password").strip()
            if not smtp_pass:
                raise ValueError("SMTP password cannot be empty.")

            sender_email = self.prompt_fn("Enter sender email address", smtp_user).strip()
            if not domain_validator.validate_email_syntax(sender_email):
                raise ValueError(f"Invalid sender email syntax: '{sender_email}'")

            from_name = self.prompt_fn("Enter sender display name", "Elena Vance | Digital Strategy Director").strip()
            reply_to = self.prompt_fn("Enter reply-to email address", sender_email).strip()
            if not domain_validator.validate_email_syntax(reply_to):
                raise ValueError(f"Invalid reply-to email syntax: '{reply_to}'")

            consistency = domain_validator.validate_identity_consistency(sender_email, reply_to)
            if not consistency["valid"]:
                raise ValueError(consistency["error"])

            email_config.update({
                "smtp_host": smtp_host,
                "smtp_port": smtp_port,
                "smtp_user": smtp_user,
                "smtp_password": smtp_pass,
                "sender_email": sender_email,
                "from_name": from_name,
                "reply_to": reply_to,
                "domain": consistency["sender_domain"]
            })

        elif selected_provider == "sendgrid":
            api_key = self.password_fn("Enter SendGrid API Key (starts with 'SG.')").strip()
            if not api_key:
                raise ValueError("SendGrid API key cannot be empty.")

            sender_email = self.prompt_fn("Enter real sender email address").strip()
            if not domain_validator.validate_email_syntax(sender_email):
                raise ValueError(f"Invalid sender email syntax: '{sender_email}'")

            from_name = self.prompt_fn("Enter sender display name", "Elena Vance | Digital Strategy Director").strip()
            reply_to = self.prompt_fn("Enter reply-to email address", sender_email).strip()
            if not domain_validator.validate_email_syntax(reply_to):
                raise ValueError(f"Invalid reply-to email syntax: '{reply_to}'")

            consistency = domain_validator.validate_identity_consistency(sender_email, reply_to)
            if not consistency["valid"]:
                raise ValueError(consistency["error"])

            email_config.update({
                "api_key": api_key,
                "sender_email": sender_email,
                "from_name": from_name,
                "reply_to": reply_to,
                "domain": consistency["sender_domain"]
            })

        # --------------------------------------------------
        # 3. EMAIL DOMAIN VALIDATION (DNS)
        # --------------------------------------------------
        target_domain = email_config["domain"]
        self.console.print(f"\n[cyan]Inspecting public DNS for sender domain '{target_domain}'...[/cyan]")
        dns_res = domain_validator.inspect_domain_dns(target_domain, selected_provider)

        dns_status_label = "[green]AVAILABLE[/green]" if dns_res["dns_available"] else "[red]UNAVAILABLE[/red]"
        spf_label = "[green]PRESENT[/green]" if dns_res["spf_present"] else "[yellow]ABSENT[/yellow]"
        dmarc_label = f"[green]PRESENT (p={dns_res['dmarc_policy']})[/green]" if dns_res["dmarc_present"] else "[yellow]ABSENT[/yellow]"

        self.console.print(f"  DNS Status: {dns_status_label}")
        self.console.print(f"  MX Records: {'PRESENT' if dns_res['mx_present'] else 'ABSENT'}")
        self.console.print(f"  SPF:        {spf_label} (Includes {selected_provider}: {dns_res['spf_includes_provider']})")
        self.console.print(f"  DMARC:      {dmarc_label}")
        self.console.print(f"  DKIM:       {dns_res['dkim_status']}")

        domain_verification_status = "UNKNOWN"
        if dns_res["dns_available"] and dns_res["spf_present"]:
            domain_verification_status = "VERIFIED" if dns_res["spf_includes_provider"] else "PARTIALLY CONFIGURED"
        elif not dns_res["dns_available"]:
            domain_verification_status = "NOT VERIFIED"

        if not dns_res["valid_syntax"] or not dns_res["dns_available"]:
            self.console.print(f"[bold red]Sender domain '{target_domain}' cannot be validated via DNS. Blocking live activation.[/bold red]")
            email_ready = False
        else:
            email_ready = True

        # --------------------------------------------------
        # 4. PAYMENT SETUP
        # --------------------------------------------------
        self.console.print("\n[bold green]--- 2. PAYMENT GATEWAY SETUP ---[/bold green]")
        config_payments = self.confirm_fn("Do you want to configure payments now? [yes/no]")

        payment_config: Optional[Dict[str, Any]] = None
        if config_payments:
            mode_choice = self.prompt_fn("Select Razorpay environment (A. TEST, B. LIVE)", "A").strip().upper()
            pay_mode = "live" if mode_choice in ("B", "LIVE") else "test"

            if pay_mode == "live":
                self.console.print(
                    "\n[bold red]⚠️  WARNING: You are configuring real payment infrastructure. "
                    "No payment will be created during this setup. ⚠️[/bold red]\n"
                )

            key_id = self.password_fn("Enter Razorpay Key ID (e.g. rzp_test_... or rzp_live_...)").strip()
            key_secret = self.password_fn("Enter Razorpay Key Secret").strip()
            webhook_secret = self.password_fn("Enter Razorpay Webhook Secret").strip()
            currency = self.prompt_fn("Enter payment currency (e.g. USD, GBP, EUR, INR)", "USD").strip().upper()

            # Validate payments
            pay_val = payment_validator.validate_razorpay_configuration(
                key_id=key_id,
                key_secret=key_secret,
                webhook_secret=webhook_secret,
                mode=pay_mode,
                currency=currency
            )

            if not pay_val["valid"]:
                err_msg = "; ".join(pay_val["errors"])
                raise ValueError(f"Payment configuration invalid: {err_msg}")

            payment_config = {
                "provider": "razorpay",
                "mode": pay_mode,
                "key_id": key_id,
                "key_secret": key_secret,
                "webhook_secret": webhook_secret,
                "currency": currency,
                "valid": True
            }

        # --------------------------------------------------
        # 5. PRE-SAVE CONFIRMATION SUMMARY (REDACTED)
        # --------------------------------------------------
        self.console.print("\n[bold cyan]==================================================[/bold cyan]")
        self.console.print("[bold white]PRE-SAVE CONFIGURATION SUMMARY[/bold white]")
        self.console.print("[bold cyan]==================================================[/bold cyan]")

        self.console.print("[bold]EMAIL[/bold]")
        self.console.print(f"Provider:    {selected_provider}")
        self.console.print(f"Sender:      {email_config['sender_email']}")
        self.console.print(f"Reply-To:    {email_config['reply_to']}")
        self.console.print(f"Domain:      {email_config['domain']}")
        self.console.print("Credential:  PRESENT")

        self.console.print("\n[bold]PAYMENTS[/bold]")
        if payment_config:
            self.console.print(f"Provider:        {payment_config['provider']}")
            self.console.print(f"Mode:            {payment_config['mode'].upper()}")
            self.console.print(f"Currency:        {payment_config['currency']}")
            self.console.print("Key ID:          PRESENT")
            self.console.print("Key Secret:      PRESENT")
            self.console.print("Webhook Secret:  PRESENT")
        else:
            self.console.print("Status:          NOT CONFIGURED (Will configure later)")

        self.console.print("\n[bold]SAFETY[/bold]")
        self.console.print("Real email sending: DISABLED")
        self.console.print("Real payments:      DISABLED")
        self.console.print("RESEARCH_ONLY:      TRUE")
        self.console.print("[bold cyan]==================================================[/bold cyan]\n")

        # --------------------------------------------------
        # 6. EXPLICIT PRE-SAVE CONFIRMATION
        # --------------------------------------------------
        save_confirmed = self.confirm_fn("Save this production configuration? [yes/no]")
        if not save_confirmed:
            self.console.print("[bold yellow]Setup aborted by operator. No changes were saved to .env or settings.[/bold yellow]")
            return {
                "saved": False,
                "message": "Aborted by operator",
                "email_configured": False,
                "payment_configured": False
            }

        # --------------------------------------------------
        # 7. WRITE SECRETS TO .ENV & UPDATE RUNTIME
        # --------------------------------------------------
        self.console.print("[cyan]Saving production configuration safely to .env...[/cyan]")

        # Email settings
        SettingsManager.write_env_key("EMAIL_PROVIDER", selected_provider)
        SettingsManager.write_env_key("EMAIL_FROM", email_config["sender_email"])
        SettingsManager.write_env_key("OUTREACH_FROM_EMAIL", email_config["sender_email"])
        SettingsManager.write_env_key("EMAIL_REPLY_TO", email_config["reply_to"])
        SettingsManager.write_env_key("OUTREACH_FROM_NAME", email_config["from_name"])
        SettingsManager.write_env_key("EMAIL_FROM_NAME", email_config["from_name"])

        settings.EMAIL_PROVIDER = selected_provider
        settings.EMAIL_FROM = email_config["sender_email"]
        settings.OUTREACH_FROM_EMAIL = email_config["sender_email"]
        settings.EMAIL_REPLY_TO = email_config["reply_to"]
        settings.OUTREACH_FROM_NAME = email_config["from_name"]
        settings.EMAIL_FROM_NAME = email_config["from_name"]

        if selected_provider == "resend":
            SettingsManager.write_env_key("RESEND_API_KEY", email_config["api_key"])
            settings.RESEND_API_KEY = email_config["api_key"]
        elif selected_provider == "smtp":
            SettingsManager.write_env_key("SMTP_HOST", email_config["smtp_host"])
            SettingsManager.write_env_key("SMTP_PORT", str(email_config["smtp_port"]))
            SettingsManager.write_env_key("SMTP_USER", email_config["smtp_user"])
            SettingsManager.write_env_key("SMTP_USERNAME", email_config["smtp_user"])
            SettingsManager.write_env_key("SMTP_PASSWORD", email_config["smtp_password"])
            settings.SMTP_HOST = email_config["smtp_host"]
            settings.SMTP_PORT = email_config["smtp_port"]
            settings.SMTP_USER = email_config["smtp_user"]
            settings.SMTP_USERNAME = email_config["smtp_user"]
            settings.SMTP_PASSWORD = email_config["smtp_password"]
        elif selected_provider == "sendgrid":
            SettingsManager.write_env_key("SENDGRID_API_KEY", email_config["api_key"])
            settings.SENDGRID_API_KEY = email_config["api_key"]

        # Payment settings
        if payment_config:
            SettingsManager.write_env_key("PAYMENT_PROVIDER", "razorpay")
            SettingsManager.write_env_key("RAZORPAY_MODE", payment_config["mode"])
            SettingsManager.write_env_key("RAZORPAY_KEY_ID", payment_config["key_id"])
            SettingsManager.write_env_key("RAZORPAY_KEY_SECRET", payment_config["key_secret"])
            SettingsManager.write_env_key("RAZORPAY_WEBHOOK_SECRET", payment_config["webhook_secret"])
            SettingsManager.write_env_key("RAZORPAY_CURRENCY", payment_config["currency"])

            settings.PAYMENT_PROVIDER = "razorpay"
            setattr(settings, "RAZORPAY_MODE", payment_config["mode"])
            settings.RAZORPAY_KEY_ID = payment_config["key_id"]
            settings.RAZORPAY_KEY_SECRET = payment_config["key_secret"]
            settings.RAZORPAY_WEBHOOK_SECRET = payment_config["webhook_secret"]
            settings.RAZORPAY_CURRENCY = payment_config["currency"]

        # --------------------------------------------------
        # 8. POST-SAVE SAFETY INVARIANTS ENFORCEMENT
        # --------------------------------------------------
        SettingsManager.write_env_key("RESEARCH_ONLY", "true")
        SettingsManager.write_env_key("EMAIL_DRY_RUN", "true")
        SettingsManager.write_env_key("PAYMENTS_ENABLED", "false")
        SettingsManager.write_env_key("PAYMENT_DRY_RUN", "true")

        settings.RESEARCH_ONLY = True
        settings.EMAIL_DRY_RUN = True
        settings.PAYMENTS_ENABLED = False
        settings.PAYMENT_DRY_RUN = True

        self.console.print("[bold green]✓ Configuration securely saved to .env.[/bold green]\n")

        # --------------------------------------------------
        # 9. FINAL CONFIGURATION REPORT
        # --------------------------------------------------
        self.console.print("[bold cyan]==================================================[/bold cyan]")
        self.console.print("[bold white]CONFIGURATION REPORT[/bold white]")
        self.console.print("[bold cyan]==================================================[/bold cyan]")

        email_prov_ready = "READY" if email_ready else "NOT READY"
        sender_ready = "READY" if domain_validator.validate_email_syntax(email_config["sender_email"]) else "NOT READY"
        domain_status = "VERIFIED" if dns_res["spf_includes_provider"] else ("NOT VERIFIED" if not dns_res["dns_available"] else "UNKNOWN")

        self.console.print("[bold]EMAIL CONFIGURATION[/bold]")
        self.console.print(f"Provider:              {email_prov_ready}")
        self.console.print(f"Sender:                {sender_ready}")
        self.console.print(f"Domain:                {domain_status}")
        self.console.print("Credential:            PRESENT")

        self.console.print("\n[bold]PAYMENT CONFIGURATION[/bold]")
        if payment_config:
            self.console.print("Provider:              READY")
            self.console.print(f"Mode:                  {payment_config['mode'].upper()}")
            self.console.print("Credentials:           PRESENT")
            self.console.print("Webhook configuration: READY")
        else:
            self.console.print("Provider:              NOT READY")
            self.console.print("Mode:                  NOT CONFIGURED")
            self.console.print("Credentials:           ABSENT")
            self.console.print("Webhook configuration: NOT READY")

        self.console.print("\n[bold]LIVE SAFETY[/bold]")
        self.console.print(f"RESEARCH_ONLY:         {str(settings.RESEARCH_ONLY).upper()}")
        self.console.print(f"EMAIL_DRY_RUN:         {str(settings.EMAIL_DRY_RUN).upper()}")
        self.console.print(f"PAYMENTS_ENABLED:      {str(settings.PAYMENTS_ENABLED).upper()}")
        self.console.print(f"PAYMENT_DRY_RUN:       {str(settings.PAYMENT_DRY_RUN).upper()}")
        self.console.print("[bold cyan]==================================================[/bold cyan]\n")

        return {
            "saved": True,
            "email_provider": selected_provider,
            "sender_email": email_config["sender_email"],
            "domain": email_config["domain"],
            "domain_status": domain_status,
            "payment_configured": bool(payment_config),
            "payment_mode": payment_config["mode"] if payment_config else None,
            "research_only": settings.RESEARCH_ONLY,
            "email_dry_run": settings.EMAIL_DRY_RUN,
            "payments_enabled": settings.PAYMENTS_ENABLED,
            "payment_dry_run": settings.PAYMENT_DRY_RUN
        }

setup_wizard = SetupWizard()
