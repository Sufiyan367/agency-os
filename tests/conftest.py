import os

# 1. Force testing environment configuration before any application imports
os.environ["TESTING"] = "true"
os.environ["APP_ENV"] = "test"
os.environ["AUTH_ENABLED"] = "false"
os.environ["EMAIL_DRY_RUN"] = "true"
os.environ["DRY_RUN"] = "true"
os.environ["RESEARCH_ONLY"] = "false"
os.environ["EMAIL_PROVIDER"] = "dry_run"
os.environ["RATE_LIMIT_ENABLED"] = "false"

# 2. Clear sensitive production credentials from test environment to prevent test leaks
for _live_key in (
    "GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN",
    "GMAIL_SENDER_EMAIL", "RESEND_API_KEY", "SENDGRID_API_KEY",
    "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD",
    "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "STRIPE_SECRET_KEY"
):
    os.environ.pop(_live_key, None)

# 3. Explicitly isolate test database
_TEST_DB_PATH = os.path.abspath("./test_agency.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH}"
os.environ["SYNC_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.database.connection import Base
from app.database.seed_data import seed_initial_data
from app.core.config import settings

# Strict safety assertion: Tests must NEVER connect to the production database
_raw_db = settings.DATABASE_URL.lower()
if "data/agency.db" in _raw_db or ("/opt/agency/data" in _raw_db):
    raise RuntimeError(
        f"CRITICAL SAFETY VIOLATION: Test suite attempted to bind to production database: {settings.DATABASE_URL}"
    )

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

def pytest_sessionstart(session):
    """Ensure a clean, uncorrupted test database file at the start of each pytest session."""
    import os
    for suffix in ("", "-wal", "-shm"):
        f = os.path.abspath(f"./test_agency.db{suffix}")
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass


@pytest_asyncio.fixture(autouse=True)
async def ensure_db_schema():
    from app.database.connection import init_db, AsyncSessionLocal
    from app.database.seed_data import seed_initial_data
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)


@pytest_asyncio.fixture(autouse=True)
async def cleanup_transient_test_tables():
    yield
    from app.database.connection import AsyncSessionLocal
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM active_outreach_locks;"))
            await session.execute(text("DELETE FROM suppression_list;"))
            res = await session.execute(text("SELECT count(*) FROM users;"))
            if res.scalar() == 0:
                from app.core.security import hash_password
                await session.execute(
                    text("INSERT OR IGNORE INTO users (username, password_hash, role, is_setup_completed, created_at, updated_at) VALUES (:u, :p, :r, :s, datetime('now'), datetime('now'))"),
                    {"u": "testadmin", "p": hash_password("test_admin_secure_password_2026"), "r": "admin", "s": 1}
                )
            await session.commit()
    except Exception:
        pass



@pytest_asyncio.fixture(autouse=True)
async def reset_rate_limiter_between_tests():
    from app.core.security import rate_limiter
    if hasattr(rate_limiter, "reset"):
        await rate_limiter.reset()

@pytest.fixture(autouse=True)
def reset_test_settings_state():
    """Guarantees clean baseline test settings before and after each test function."""
    orig_auth = settings.AUTH_ENABLED
    orig_email_dry = getattr(settings, "EMAIL_DRY_RUN", True)
    orig_dry_run = getattr(settings, "DRY_RUN", True)
    orig_env = settings.APP_ENV
    orig_provider = getattr(settings, "EMAIL_PROVIDER", "dry_run")

    settings.AUTH_ENABLED = False
    settings.EMAIL_DRY_RUN = True
    settings.DRY_RUN = True
    settings.APP_ENV = "test"
    settings.EMAIL_PROVIDER = "dry_run"

    yield

    settings.AUTH_ENABLED = orig_auth
    settings.EMAIL_DRY_RUN = orig_email_dry
    settings.DRY_RUN = orig_dry_run
    settings.APP_ENV = orig_env
    settings.EMAIL_PROVIDER = orig_provider

@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        await seed_initial_data(session)
        yield session
    
    await engine.dispose()

@pytest.fixture(autouse=True, scope="session")
def setup_test_auth_env():
    """Ensures test session has valid test-only secrets configured and defaults AUTH_ENABLED to False for functional suites."""
    settings.AUTH_ENABLED = False
    settings.APP_ENV = "test"
    settings.DEBUG = False
    settings.RESEARCH_ONLY = False
    settings.EMAIL_DRY_RUN = True
    settings.DRY_RUN = True
    settings.EMAIL_PROVIDER = "dry_run"
    if not settings.SESSION_SECRET:
        settings.SESSION_SECRET = "test_only_session_hmac_secret_key_with_sufficient_length_2026"
    if not settings.API_SECRET_KEY:
        settings.API_SECRET_KEY = "test_only_api_secret_master_key_with_sufficient_length_2026"
    if not settings.DASHBOARD_USERNAME:
        settings.DASHBOARD_USERNAME = "admin"
    if not settings.DASHBOARD_PASSWORD:
        settings.DASHBOARD_PASSWORD = "test_admin_secure_password_2026"
    if not settings.VIEWER_USERNAME:
        settings.VIEWER_USERNAME = "viewer"
    if not settings.VIEWER_PASSWORD:
        settings.VIEWER_PASSWORD = "test_viewer_secure_password_2026"

@pytest.fixture(autouse=True, scope="session")
def safeguard_production_users():
    """Safeguards users in test_agency.db so test runs never leave it wiped."""
    import os
    import sqlite3
    db_file = os.path.abspath("./test_agency.db")
    backup_rows = []
    if os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
            if cur.fetchone():
                cur.execute("SELECT username, password_hash, role, is_setup_completed, created_at, updated_at FROM users;")
                backup_rows = cur.fetchall()
            conn.close()
        except Exception:
            backup_rows = []

    yield

    if backup_rows and os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file)
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM users;")
            cnt = cur.fetchone()[0]
            if cnt == 0:
                cur.executemany(
                    "INSERT INTO users (username, password_hash, role, is_setup_completed, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?);",
                    backup_rows
                )
                conn.commit()
            conn.close()
        except Exception:
            pass


