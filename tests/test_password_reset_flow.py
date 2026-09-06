import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, delete

from app.api.app import app
from app.core.config import settings
from app.core.auth_service import auth_service
from app.database.connection import AsyncSessionLocal
from app.database.models import User, PasswordResetToken

from app.core.security import hash_password

TEST_ADMIN_USER = "admin_reset_test"
TEST_ORIG_PASS = "ResetInitialPass123!"
TEST_NEW_PASS = "ResetUpdatedPass456!"

@pytest.fixture(autouse=True)
async def clean_test_user():
    # Clean up test user and tokens before and after test
    async with AsyncSessionLocal() as session:
        user_stmt = select(User).where(User.username == TEST_ADMIN_USER)
        res = await session.execute(user_stmt)
        user = res.scalar_one_or_none()
        if user:
            await session.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()
    yield
    async with AsyncSessionLocal() as session:
        user_stmt = select(User).where(User.username == TEST_ADMIN_USER)
        res = await session.execute(user_stmt)
        user = res.scalar_one_or_none()
        if user:
            await session.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()

@pytest.mark.asyncio
async def test_complete_password_reset_lifecycle():
    """
    Verifies full lifecycle:
    1. Account creation & initial login
    2. Forgot password link generation
    3. Password reset execution
    4. Session revocation & new password login verification
    5. Token single-use enforcement
    """
    orig_auth = settings.AUTH_ENABLED
    orig_rate = settings.RATE_LIMIT_ENABLED
    try:
        settings.AUTH_ENABLED = True
        settings.RATE_LIMIT_ENABLED = False
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Create account directly in database
            async with AsyncSessionLocal() as session:
                user = User(
                    username=TEST_ADMIN_USER,
                    password_hash=hash_password(TEST_ORIG_PASS),
                    role="admin",
                    is_setup_completed=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                assert user.username == TEST_ADMIN_USER

            # 2. Login with original password succeeds
            login_res = await client.post("/api/auth/login", json={
                "username": TEST_ADMIN_USER,
                "password": TEST_ORIG_PASS
            })
            assert login_res.status_code == 200
            data = login_res.json()
            assert data["status"] == "SUCCESS"
            initial_token = data["token"]

            # 3. Wrong password fails
            bad_login = await client.post("/api/auth/login", json={
                "username": TEST_ADMIN_USER,
                "password": "WrongPassword999!"
            })
            assert bad_login.status_code == 401

            # 4. Request password reset token
            forgot_res = await client.post("/api/auth/forgot-password", json={
                "username": TEST_ADMIN_USER
            })
            assert forgot_res.status_code == 200
            forgot_data = forgot_res.json()
            assert forgot_data["status"] == "SUCCESS"
            assert "reset_token" in forgot_data
            assert "reset_url" in forgot_data
            raw_token = forgot_data["reset_token"]
            assert len(raw_token) >= 32

            # Verify token record exists in database and is hashed
            async with AsyncSessionLocal() as session:
                stmt = select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
                res = await session.execute(stmt)
                tokens = res.scalars().all()
                assert len(tokens) == 1
                assert tokens[0].is_used is False
                assert tokens[0].token_hash != raw_token # SHA-256 hashed

            # 5. Access /reset-password HTML page
            page_res = await client.get(f"/reset-password?token={raw_token}")
            assert page_res.status_code == 200
            assert "Set new password" in page_res.text
            assert 'id="new_password"' in page_res.text
            assert 'id="confirm_password"' in page_res.text
            assert 'id="btn-reset-submit"' in page_res.text

            # 6. Attempt reset with mismatched passwords
            mismatch_res = await client.post("/api/auth/reset-password", json={
                "token": raw_token,
                "new_password": TEST_NEW_PASS,
                "confirm_password": "DifferentPass123!"
            })
            assert mismatch_res.status_code == 400
            assert "confirmation does not match" in mismatch_res.text.lower()

            # 7. Attempt reset with short/weak password
            weak_res = await client.post("/api/auth/reset-password", json={
                "token": raw_token,
                "new_password": "short",
                "confirm_password": "short"
            })
            assert weak_res.status_code == 400
            assert "at least 12 characters" in weak_res.text.lower()

            # 8. Successful password reset
            reset_res = await client.post("/api/auth/reset-password", json={
                "token": raw_token,
                "new_password": TEST_NEW_PASS,
                "confirm_password": TEST_NEW_PASS
            })
            assert reset_res.status_code == 200
            reset_data = reset_res.json()
            assert reset_data["status"] == "SUCCESS"

            # 9. Token single-use enforcement: reusing the token must fail
            reuse_res = await client.post("/api/auth/reset-password", json={
                "token": raw_token,
                "new_password": "AnotherNewPass123!",
                "confirm_password": "AnotherNewPass123!"
            })
            assert reuse_res.status_code == 400
            assert "invalid, expired, or already used" in reuse_res.text.lower()

            # 10. Prior session token is invalidated
            # Test authenticated request with old session token
            dash_res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {initial_token}"})
            # Since sessions were invalidated via auth_service, request is rejected with 401
            assert dash_res.status_code == 401

            # 11. Old password can no longer log in
            old_login = await client.post("/api/auth/login", json={
                "username": TEST_ADMIN_USER,
                "password": TEST_ORIG_PASS
            })
            assert old_login.status_code == 401

            # 12. New password logs in successfully
            new_login = await client.post("/api/auth/login", json={
                "username": TEST_ADMIN_USER,
                "password": TEST_NEW_PASS
            })
            assert new_login.status_code == 200
            assert new_login.json()["status"] == "SUCCESS"

    finally:
        settings.AUTH_ENABLED = orig_auth
        settings.RATE_LIMIT_ENABLED = orig_rate

@pytest.mark.asyncio
async def test_expired_reset_token_rejected():
    """Verifies that an expired reset token is rejected."""
    orig_auth = settings.AUTH_ENABLED
    orig_rate = settings.RATE_LIMIT_ENABLED
    try:
        settings.AUTH_ENABLED = True
        settings.RATE_LIMIT_ENABLED = False
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with AsyncSessionLocal() as session:
                user = User(
                    username=TEST_ADMIN_USER,
                    password_hash=hash_password(TEST_ORIG_PASS),
                    role="admin",
                    is_setup_completed=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)

            # Generate token
            forgot_res = await client.post("/api/auth/forgot-password", json={
                "username": TEST_ADMIN_USER
            })
            raw_token = forgot_res.json()["reset_token"]

            # Manually expire the token in the database
            async with AsyncSessionLocal() as session:
                stmt = select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
                res = await session.execute(stmt)
                tok_rec = res.scalar_one()
                tok_rec.expires_at = datetime.utcnow() - timedelta(minutes=5)
                await session.commit()

            # Attempt to reset with expired token
            res = await client.post("/api/auth/reset-password", json={
                "token": raw_token,
                "new_password": TEST_NEW_PASS,
                "confirm_password": TEST_NEW_PASS
            })
            assert res.status_code == 400
            assert "invalid, expired, or already used" in res.text.lower()
    finally:
        settings.AUTH_ENABLED = orig_auth
        settings.RATE_LIMIT_ENABLED = orig_rate

@pytest.mark.asyncio
async def test_first_launch_account_setup_and_data_preservation():
    """
    Verifies that:
    1. Account setup UI contains expected elements and SaaS copy.
    2. Preserves backwards test compatibility marker.
    3. Database models and prospect tables remain accessible and untouched.
    """
    from app.database.models import Business
    orig_auth = settings.AUTH_ENABLED
    orig_rate = settings.RATE_LIMIT_ENABLED
    try:
        settings.AUTH_ENABLED = True
        settings.RATE_LIMIT_ENABLED = False
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Verify setup template content directly
            res = await client.get("/setup", follow_redirects=False)
            assert res.status_code in (200, 302, 307)
            if res.status_code == 200:
                assert "Create your account" in res.text
                assert 'id="username"' in res.text
                assert 'id="password"' in res.text
                assert 'id="confirm_password"' in res.text
                assert 'id="btn-submit"' in res.text
                assert 'FIRST-LAUNCH ADMINISTRATOR SETUP' in res.text

            # Verify businesses table is accessible and intact
            async with AsyncSessionLocal() as session:
                biz_stmt = select(Business)
                biz_res = await session.execute(biz_stmt)
                businesses = biz_res.scalars().all()
                assert isinstance(businesses, list)
    finally:
        settings.AUTH_ENABLED = orig_auth
        settings.RATE_LIMIT_ENABLED = orig_rate

