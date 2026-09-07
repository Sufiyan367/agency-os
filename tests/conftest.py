import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_agency.db"
os.environ["SYNC_DATABASE_URL"] = "sqlite:///./test_agency.db"

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.database.connection import Base
from app.database.seed_data import seed_initial_data

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture(autouse=True)
async def ensure_db_schema():
    from app.database.connection import init_db
    await init_db()

@pytest_asyncio.fixture(autouse=True)
async def reset_rate_limiter_between_tests():
    from app.core.security import rate_limiter
    if hasattr(rate_limiter, "reset"):
        await rate_limiter.reset()


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
    from app.core.config import settings
    settings.AUTH_ENABLED = False
    settings.APP_ENV = "development"
    settings.DEBUG = False
    settings.RESEARCH_ONLY = False
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
    """Safeguards real production users in agency.db so test runs never leave it wiped."""
    import os
    import sqlite3
    from app.database.backup import get_sqlite_db_path
    db_file = get_sqlite_db_path() or "test_agency.db"
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


