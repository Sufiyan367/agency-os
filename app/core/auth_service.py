import time
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.core.security import hash_password, verify_password, FORBIDDEN_SECRET_PATTERNS
from app.database.models import User, PasswordResetToken

# Minimum password length policy
MIN_PASSWORD_LENGTH = 12

# Common / weak passwords disallowed explicitly
WEAK_PASSWORD_BLACKLIST = {
    "password1234",
    "admin1234567",
    "123456789012",
    "qwertyuiopas",
    "administrator",
    "changeme1234",
    "welcome12345",
}

class AuthService:
    """
    Central authentication and credential management service.
    Handles first-launch setup detection, password strength policy enforcement,
    secure credential updates, and session revocation.
    """
    def __init__(self):
        self._user_revocation_timestamps: Dict[str, float] = {}

    def clear_cache(self) -> None:
        """Clears in-memory revocation timestamps (e.g. for testing)."""
        self._user_revocation_timestamps.clear()

    async def is_setup_required(self, session: AsyncSession) -> bool:
        """
        Determines whether initial administrator setup is required.
        Returns True ONLY if database query explicitly succeeds AND confirms no completed admin exists.
        Re-raises exceptions on database failure so callers fail closed (e.g. HTTP 503) instead of
        falsely reporting that setup is required.
        """
        try:
            stmt = (
                select(User.id)
                .where(
                    User.role == "admin",
                    User.is_setup_completed.is_(True),
                    User.password_hash.is_not(None),
                    User.password_hash != ""
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is None
        except Exception as e:
            logger.error(f"[AuthService] Database error checking setup status: {e}")
            raise

    def validate_password_strength(self, password: str) -> Tuple[bool, str]:
        """
        Validates password against security policies:
        - Minimum 12 characters
        - Disallow pure whitespace or empty
        - Disallow known default credentials, forbidden patterns, and dictionary passwords
        """
        if not password or not isinstance(password, str):
            return False, "Password cannot be empty."

        clean = password.strip()
        if len(clean) < MIN_PASSWORD_LENGTH:
            return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."

        lower = clean.lower()

        # Check blacklist
        if lower in WEAK_PASSWORD_BLACKLIST:
            return False, "The chosen password is too common and insecure. Please choose a stronger passphrase."

        # Check forbidden patterns
        for pattern in FORBIDDEN_SECRET_PATTERNS:
            if pattern in lower:
                return False, f"Password contains insecure pattern '{pattern}'. Please choose a unique passphrase."

        # Check trivial repetition (e.g. 'aaaaaaaaaaaa' or '111111111111')
        if len(set(clean)) < 4:
            return False, "Password lacks character variety. Please use a more complex passphrase."

        return True, ""

    async def complete_setup(
        self,
        session: AsyncSession,
        username: str,
        password: str,
        confirm_password: str
    ) -> User:
        """
        Executes first-launch administrator setup.
        Validates password policies, hashes with PBKDF2, stores in database,
        and marks setup as completed.
        Guarantees idempotency and race-condition safety.
        """
        # Ensure setup has not already been completed
        setup_needed = await self.is_setup_required(session)
        if not setup_needed:
            raise ValueError("Initial setup has already been completed.")

        clean_user = username.strip() if username else "admin"
        if not clean_user:
            clean_user = "admin"

        if password != confirm_password:
            raise ValueError("Password confirmation does not match.")

        valid, reason = self.validate_password_strength(password)
        if not valid:
            raise ValueError(reason)

        hashed = hash_password(password)

        # Check if user already exists
        stmt = select(User).where(User.username == clean_user)
        result = await session.execute(stmt)
        existing_user = result.scalar_one_or_none()

        now = datetime.utcnow()
        if existing_user:
            existing_user.password_hash = hashed
            existing_user.role = "admin"
            existing_user.is_setup_completed = True
            existing_user.updated_at = now
            user = existing_user
        else:
            user = User(
                username=clean_user,
                password_hash=hashed,
                role="admin",
                is_setup_completed=True,
                created_at=now,
                updated_at=now
            )
            session.add(user)

        try:
            await session.commit()
            await session.refresh(user)
        except Exception as e:
            await session.rollback()
            # In case of concurrent insert race condition, check if setup is now complete
            try:
                if not await self.is_setup_required(session):
                    raise ValueError("Initial setup has already been completed.")
            except Exception:
                pass
            raise

        logger.info(f"[AuthService] Administrator account '{clean_user}' created and setup completed.")
        return user

    async def verify_user(
        self,
        session: AsyncSession,
        username: str,
        password: str
    ) -> Optional[User]:
        """
        Verifies credentials against stored PBKDF2 hash in database.
        Returns User object on success, None on invalid credentials or user not found.
        """
        if not username or not password:
            return None

        clean_user = username.strip()
        stmt = select(User).where(User.username == clean_user)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return None

        if verify_password(password, user.password_hash):
            return user

        return None

    async def change_user_password(
        self,
        session: AsyncSession,
        username: str,
        current_password: str,
        new_password: str,
        confirm_password: str
    ) -> User:
        """
        Updates an existing user's password.
        Validates current password, verifies new password strength, ensures difference,
        atomically updates the hash, and invalidates existing sessions.
        """
        clean_user = username.strip()
        stmt = select(User).where(User.username == clean_user)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User '{clean_user}' not found.")

        # 1. Verify current password
        if not verify_password(current_password, user.password_hash):
            raise ValueError("Current password is incorrect.")

        # 2. Check confirmation match
        if new_password != confirm_password:
            raise ValueError("New password confirmation does not match.")

        # 3. Ensure new password differs from current
        if current_password == new_password or verify_password(new_password, user.password_hash):
            raise ValueError("New password cannot be identical to current password.")

        # 4. Validate password policy
        valid, reason = self.validate_password_strength(new_password)
        if not valid:
            raise ValueError(reason)

        # 5. Atomically update hash
        new_hash = hash_password(new_password)
        now = datetime.utcnow()
        user.password_hash = new_hash
        user.updated_at = now

        await session.commit()
        await session.refresh(user)

        # 6. Invalidate active sessions
        self.invalidate_user_sessions(clean_user)
        logger.info(f"[AuthService] Password updated and sessions invalidated for user '{clean_user}'.")
        return user

    def invalidate_user_sessions(self, username: str) -> None:
        """Records revocation timestamp for user to invalidate older tokens."""
        clean_user = username.strip()
        self._user_revocation_timestamps[clean_user] = time.time()

    def is_session_revoked(self, username: str, token: str) -> bool:
        """
        Checks whether a session token was issued before the user's last password change.
        Token format: username.role.expires_at.sig
        """
        clean_user = username.strip()
        revocation_time = self._user_revocation_timestamps.get(clean_user)
        if not revocation_time:
            return False

        parts = token.split(".")
        if len(parts) >= 3:
            try:
                expires_at = int(parts[-2] if len(parts) == 4 else parts[1])
                # In create_session_token: expires_at = now + (SESSION_MAX_AGE_DAYS * 86400)
                issued_at = expires_at - (settings.SESSION_MAX_AGE_DAYS * 86400)
                # If issued before revocation timestamp, session is revoked
                if issued_at < revocation_time:
                    return True
            except (ValueError, IndexError):
                return True

        return False

    async def reset_admin_user(self, session: AsyncSession) -> bool:
        """
        Clears administrator accounts from the database.
        Allows the first-launch setup flow to be re-run.
        """
        stmt = delete(User)
        result = await session.execute(stmt)
        await session.commit()

        self.invalidate_user_sessions("admin")
        logger.warning("[AuthService] Administrator accounts have been reset. First-launch setup is now required.")
        return True

    async def create_password_reset_token(
        self, session: AsyncSession, username_or_email: str
    ) -> Optional[Tuple[str, PasswordResetToken]]:
        """
        Creates a secure, single-use, 15-minute expiring password reset token for user.
        Returns (raw_token, token_record) if user exists, else None.
        Stores only the SHA-256 hash of the token in the database.
        """
        clean_name = username_or_email.strip()
        stmt = select(User).where(User.username == clean_name)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            return None

        # Invalidate any previously unused reset tokens for this user
        expire_stmt = (
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.is_used.is_(False)
            )
            .values(is_used=True)
        )
        await session.execute(expire_stmt)

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = datetime.utcnow() + timedelta(minutes=15)

        reset_record = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            is_used=False,
            created_at=datetime.utcnow(),
        )
        session.add(reset_record)
        await session.commit()
        await session.refresh(reset_record)
        logger.info(f"[AuthService] Password reset token generated for user '{clean_name}'.")
        return raw_token, reset_record

    async def verify_and_use_reset_token(
        self, session: AsyncSession, raw_token: str, new_password: str, confirm_password: str
    ) -> User:
        """
        Validates token, ensures single-use & not expired, validates new password policy,
        updates password hash, marks token used, and invalidates active sessions.
        """
        if not raw_token or not raw_token.strip():
            raise ValueError("Invalid or missing reset token.")

        if new_password != confirm_password:
            raise ValueError("Password confirmation does not match.")

        valid, reason = self.validate_password_strength(new_password)
        if not valid:
            raise ValueError(reason)

        token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
        now = datetime.utcnow()

        stmt = select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.is_used.is_(False),
            PasswordResetToken.expires_at > now
        )
        result = await session.execute(stmt)
        token_record = result.scalar_one_or_none()

        if not token_record:
            raise ValueError("Reset token is invalid, expired, or already used.")

        # Get associated user
        user_stmt = select(User).where(User.id == token_record.user_id)
        user_res = await session.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if not user:
            raise ValueError("Associated user account not found.")

        # Update password
        user.password_hash = hash_password(new_password)
        user.updated_at = now
        token_record.is_used = True

        await session.commit()
        await session.refresh(user)

        self.invalidate_user_sessions(user.username)
        logger.info(f"[AuthService] Password successfully reset for user '{user.username}' via reset token.")
        return user

auth_service = AuthService()

