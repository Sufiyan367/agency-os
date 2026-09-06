# Secret Rotation & Credential Management Guide

This document defines the procedure for rotating credentials, session keys, and API secrets without causing unexpected downtime or data corruption.

## 1. Generating Cryptographically Strong Secrets

Always use cryptographically secure random sources. Never use dictionary words or timestamps.

```bash
# Generate 64-character hex secret for SESSION_SECRET or API_SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# Generate URL-safe random string
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 2. Rotating `SESSION_SECRET`
The `SESSION_SECRET` is used to compute and verify HMAC-SHA256 signatures for user session cookies (`agency_session`).

**Impact of Rotation**:
- Active dashboard browser sessions will be invalidated.
- Users will be prompted to log back in with their username and password.
- No database records, lead memories, or persistent state are impacted.

**Procedure**:
1. Generate a new secret: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Update `SESSION_SECRET` in `.env`.
3. Restart the container / service (`docker compose up -d` or `systemctl restart agency`).
4. Verify `/health` returns HTTP 200.

## 3. Rotating `API_SECRET_KEY`
The `API_SECRET_KEY` authenticates programmatic API callers via `Authorization: Bearer <API_SECRET_KEY>`.

**Impact of Rotation**:
- Existing external API clients using the old key will receive HTTP 401 until updated.

**Procedure**:
1. Generate a new key.
2. Coordinate deployment with external callers or configure overlapping verification during rotation windows.
3. Update `API_SECRET_KEY` in `.env` and reload the service.

## 4. Rotating Payment & Telephony Webhook Secrets
- **Razorpay**: Update the webhook secret in Razorpay Dashboard (`Settings > Webhooks`) and update `RAZORPAY_WEBHOOK_SECRET` in `.env`.
- **Stripe**: Add new signing secret from Stripe Dashboard (`Developers > Webhooks > Reveal secret`) to `STRIPE_WEBHOOK_SECRET` in `.env`.
- Note: Both providers support rolling secret periods.

## 5. Security Invariants
- Never commit `.env` to version control.
- Ensure file permissions on production `.env` are `chmod 600`.
- Verify secrets are excluded from backups and container image layers.
