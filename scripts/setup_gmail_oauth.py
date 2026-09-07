"""
Interactive Gmail OAuth2 Setup for Agency OS.
Acquires long-lived refresh_token for the owner's personal Gmail account using:
- https://www.googleapis.com/auth/gmail.send
- https://www.googleapis.com/auth/gmail.readonly

SAFETY INVARIANTS:
- Never requests or touches passwords or app passwords.
- Never prints refresh_token, client_secret, or authorization codes.
- Never transmits emails.
- Uses dynamic local loopback port (port=0).
- Verifies identity via users.getProfile(userId="me").
"""
import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, Optional

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from app.outreach.providers.gmail_oauth_provider import GMAIL_SCOPES


def update_env_file(env_path: Path, updates: Dict[str, str]):
    """Safely updates or appends key-value pairs in the .env file without printing values."""
    existing_lines = []
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()

    keys_updated = set()
    new_lines = []

    for line in existing_lines:
        trimmed = line.strip()
        if trimmed and not trimmed.startswith("#") and "=" in trimmed:
            key, _ = trimmed.split("=", 1)
            key = key.strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                keys_updated.add(key)
                continue
        new_lines.append(line)

    for key, val in updates.items():
        if key not in keys_updated:
            new_lines.append(f"{key}={val}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def setup_oauth(client_secrets_path: Optional[str] = None, client_id: Optional[str] = None, client_secret: Optional[str] = None):
    print("=" * 60)
    print("  AGENCY OS — GMAIL OAUTH2 SETUP (NON-DESTRUCTIVE)")
    print("=" * 60)
    print("Safety Check:")
    print("  - Zero emails will be transmitted.")
    print("  - Least-privilege scopes: gmail.send + gmail.readonly.")
    print("  - Password is never requested or stored.")
    print("  - Secret tokens will NEVER be printed to the screen.\n")

    # 1. Resolve client credentials
    flow = None
    if client_secrets_path and os.path.exists(client_secrets_path):
        print(f"Loading client credentials from: {client_secrets_path}")
        flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, scopes=GMAIL_SCOPES)
        with open(client_secrets_path, "r", encoding="utf-8") as f:
            client_data = json.load(f)
            client_info = client_data.get("installed") or client_data.get("web") or {}
            resolved_client_id = client_info.get("client_id", "")
            resolved_client_secret = client_info.get("client_secret", "")
    elif client_id and client_secret:
        resolved_client_id = client_id.strip()
        resolved_client_secret = client_secret.strip()
        client_config = {
            "installed": {
                "client_id": resolved_client_id,
                "client_secret": resolved_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, scopes=GMAIL_SCOPES)
    else:
        # Check if default credentials.json exists
        default_json = PROJECT_ROOT / "credentials.json"
        if default_json.exists():
            print(f"Found default client credentials at: {default_json}")
            flow = InstalledAppFlow.from_client_secrets_file(str(default_json), scopes=GMAIL_SCOPES)
            with open(default_json, "r", encoding="utf-8") as f:
                client_data = json.load(f)
                client_info = client_data.get("installed") or client_data.get("web") or {}
                resolved_client_id = client_info.get("client_id", "")
                resolved_client_secret = client_info.get("client_secret", "")
        else:
            print("ERROR: No client credentials provided.")
            print("Please provide client_secrets.json, or pass --client-id and --client-secret.")
            sys.exit(1)

    # 2. Run local loopback callback flow on a dynamically available port
    print("\nLaunching browser for Google authorization...")
    print("Please log in with the owner's Gmail account and approve the requested scopes.")
    creds = flow.run_local_server(
        port=0,
        authorization_prompt_message="Open this URL in your browser if it doesn't open automatically: {url}",
        success_message="Authentication successful! You may close this tab and return to the terminal.",
        access_type="offline",
        prompt="consent"
    )

    if not creds.refresh_token:
        print("\nERROR: No refresh token returned by Google.")
        print("Ensure 'access_type=offline' and 'prompt=consent' were requested.")
        sys.exit(1)

    # 3. Verify authenticated Gmail identity using users().getProfile(userId='me')
    print("\nVerifying authenticated Gmail profile via Gmail API (read-only)...")
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    authenticated_email = profile.get("emailAddress", "").strip().lower()

    if not authenticated_email:
        print("ERROR: Could not verify authenticated email address from Google Profile.")
        sys.exit(1)

    print(f"\n[OK] Authenticated Account: {authenticated_email}")
    print(f"[OK] Total Account Threads: {profile.get('threadsTotal', 0)}")
    print(f"[OK] Token Validity Confirmed: Refresh token acquired successfully.")

    # 4. Save to .env safely without printing tokens
    env_file = PROJECT_ROOT / ".env"
    updates = {
        "GMAIL_CLIENT_ID": resolved_client_id,
        "GMAIL_CLIENT_SECRET": resolved_client_secret,
        "GMAIL_REFRESH_TOKEN": creds.refresh_token,
        "GMAIL_SENDER_EMAIL": authenticated_email,
        "EMAIL_PROVIDER": "gmail"
    }

    update_env_file(env_file, updates)
    print(f"[OK] Configuration safely written to {env_file.name}.")
    print("[OK] Secret values were redacted and NOT printed to the screen.")
    print("[OK] ZERO real emails were sent.")
    print("=" * 60)
    print("Setup complete. You can now use Gmail OAuth in Dry-Run or controlled test mode.")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agency OS Gmail OAuth2 Setup Script")
    parser.add_argument("--client-secrets", help="Path to downloaded client_secrets.json file")
    parser.add_argument("--client-id", help="Google Cloud OAuth Client ID")
    parser.add_argument("--client-secret", help="Google Cloud OAuth Client Secret")
    args = parser.parse_args()

    setup_oauth(
        client_secrets_path=args.client_secrets,
        client_id=args.client_id,
        client_secret=args.client_secret
    )
