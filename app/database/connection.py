"""Database Connection and Session Management.

Provides enterprise-grade abstraction for:
- SQLite (development, local execution, and tests with WAL mode & foreign keys)
- PostgreSQL (production deployments with connection pooling, pre-ping & health checks)
- Transaction integrity and atomic execution context
- Operational diagnostic telemetry without secret leakage
"""
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from app.core.config import settings


class Base(DeclarativeBase):
    pass


def normalize_database_url(url: str, is_async: bool = True) -> str:
    """Normalizes database URLs to ensure correct asynchronous or synchronous drivers."""
    if not url:
        return url
    
    # Handle PostgreSQL URLs
    if url.startswith("postgres://") or url.startswith("postgresql://"):
        base_url = url.split("://", 1)[1]
        if is_async:
            return f"postgresql+asyncpg://{base_url}"
        else:
            return f"postgresql+psycopg://{base_url}"

    # Handle SQLite URLs
    if is_async:
        if url.startswith("sqlite:///") and "aiosqlite" not in url:
            return url.replace("sqlite:///", "sqlite+aiosqlite:///")
    else:
        if "sqlite+aiosqlite:///" in url:
            return url.replace("sqlite+aiosqlite:///", "sqlite:///")

    return url


def create_agency_engine(url: Optional[str] = None, is_async: bool = True):
    """Creates a configured SQLAlchemy engine for SQLite or PostgreSQL."""
    target_url = normalize_database_url(url or settings.DATABASE_URL, is_async=is_async)
    is_sql = "sqlite" in target_url
    if is_async:
        kwargs: Dict[str, Any] = {"echo": False, "future": True}
        if is_sql:
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs["pool_size"] = getattr(settings, "DB_POOL_SIZE", 10)
            kwargs["max_overflow"] = getattr(settings, "DB_MAX_OVERFLOW", 20)
            kwargs["pool_timeout"] = getattr(settings, "DB_POOL_TIMEOUT", 30)
            kwargs["pool_recycle"] = getattr(settings, "DB_POOL_RECYCLE", 1800)
            kwargs["pool_pre_ping"] = True
        return create_async_engine(target_url, **kwargs)
    else:
        sync_kwargs: Dict[str, Any] = {"echo": False, "future": True}
        if is_sql:
            sync_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            sync_kwargs["pool_size"] = getattr(settings, "DB_POOL_SIZE", 10)
            sync_kwargs["max_overflow"] = getattr(settings, "DB_MAX_OVERFLOW", 20)
            sync_kwargs["pool_pre_ping"] = True
        return create_engine(target_url, **sync_kwargs)


# Resolve URLs
RESOLVED_ASYNC_DATABASE_URL = normalize_database_url(settings.DATABASE_URL, is_async=True)
RESOLVED_SYNC_DATABASE_URL = normalize_database_url(
    getattr(settings, "SYNC_DATABASE_URL", None) or settings.DATABASE_URL,
    is_async=False
)

is_sqlite = "sqlite" in RESOLVED_ASYNC_DATABASE_URL

# Async engine configuration
engine_kwargs: Dict[str, Any] = {
    "echo": False,
    "future": True,
}

if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = getattr(settings, "DB_POOL_SIZE", 10)
    engine_kwargs["max_overflow"] = getattr(settings, "DB_MAX_OVERFLOW", 20)
    engine_kwargs["pool_timeout"] = getattr(settings, "DB_POOL_TIMEOUT", 30)
    engine_kwargs["pool_recycle"] = getattr(settings, "DB_POOL_RECYCLE", 1800)
    engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(RESOLVED_ASYNC_DATABASE_URL, **engine_kwargs)

# Sync engine configuration (for migrations and sync workers)
sync_engine_kwargs: Dict[str, Any] = {
    "echo": False,
    "future": True,
}
if is_sqlite:
    sync_engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    sync_engine_kwargs["pool_size"] = getattr(settings, "DB_POOL_SIZE", 10)
    sync_engine_kwargs["max_overflow"] = getattr(settings, "DB_MAX_OVERFLOW", 20)
    sync_engine_kwargs["pool_pre_ping"] = True

sync_engine = create_engine(RESOLVED_SYNC_DATABASE_URL, **sync_engine_kwargs)
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False, autocommit=False, autoflush=False)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enforces WAL journal mode and timeouts on SQLite."""
    if "sqlite" in str(engine.url):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


@event.listens_for(sync_engine, "connect")
def set_sync_sqlite_pragma(dbapi_connection, connection_record):
    """Enforces WAL journal mode on synchronous SQLite connections."""
    if "sqlite" in str(sync_engine.url):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency yielding transactional database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def atomic_transaction(session: AsyncSession):
    """Context manager ensuring all operations in the block commit together or rollback atomically."""
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise


def get_database_dialect() -> str:
    """Returns the database dialect: 'sqlite' or 'postgresql'."""
    url_str = str(engine.url).lower()
    return "sqlite" if "sqlite" in url_str else "postgresql"


async def check_database_connectivity() -> Dict[str, Any]:
    """Measures round-trip database latency and reports connection pool status without exposing secrets."""
    start = time.perf_counter()
    dialect = get_database_dialect()
    
    pool_stats = {
        "configured_pool_size": getattr(settings, "DB_POOL_SIZE", 10) if dialect == "postgresql" else None,
        "pre_ping": True if dialect == "postgresql" else False,
    }

    try:
        pool = getattr(engine, "pool", None)
        if pool and dialect == "postgresql":
            pool_stats.update({
                "size": getattr(pool, "size", lambda: 0)(),
                "checkedin": getattr(pool, "checkedin", lambda: 0)(),
                "checkedout": getattr(pool, "checkedout", lambda: 0)(),
                "overflow": getattr(pool, "overflow", lambda: 0)(),
            })
    except Exception:
        pass

    target_url = str(engine.url)
    db_name = target_url.split("/")[-1].split("?")[0] or "agency_db"

    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("SELECT 1"))
            val = res.scalar()
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            if val == 1:
                return {
                    "status": "ONLINE",
                    "connected": True,
                    "healthy": True,
                    "dialect": dialect,
                    "latency_ms": latency_ms,
                    "database_name": db_name,
                    "pool_status": f"size={pool_stats.get('size', 1)}, overflow={pool_stats.get('overflow', 0)}" if dialect == "postgresql" else "sqlite_wal_mode",
                    "pool": pool_stats,
                }
            return {
                "status": "DEGRADED",
                "connected": False,
                "healthy": False,
                "dialect": dialect,
                "latency_ms": latency_ms,
                "database_name": db_name,
                "error": "Query returned unexpected value",
                "pool": pool_stats,
            }
    except Exception as e:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "status": "OFFLINE",
            "connected": False,
            "healthy": False,
            "dialect": dialect,
            "latency_ms": latency_ms,
            "database_name": db_name,
            "error": str(e),
            "pool": pool_stats,
        }


async def init_db():
    """Initializes the database schema, enables WAL mode, and ensures all tables exist."""
    import app.database.models  # noqa
    import app.models.entities  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Safe migrations for SQLite if tables already existed
        if get_database_dialect() == "sqlite":
            # local_businesses
            for col, col_type in [
                ("address", "TEXT"),
                ("rating", "REAL"),
                ("review_count", "INTEGER"),
                ("source", "VARCHAR(100) DEFAULT 'discovery_engine'"),
                ("source_url", "VARCHAR(500)")
            ]:
                try:
                    await conn.execute(text(f"ALTER TABLE local_businesses ADD COLUMN {col} {col_type}"))
                except Exception:
                    pass

            # payments
            for col, col_type in [
                ("business_id", "INTEGER"),
                ("lead_id", "INTEGER"),
                ("deal_id", "INTEGER"),
                ("proposal_id", "INTEGER"),
                ("payment_type", "VARCHAR(50) DEFAULT 'FULL_PAYMENT'"),
                ("provider", "VARCHAR(50) DEFAULT 'razorpay'"),
                ("razorpay_order_id", "VARCHAR(100)"),
                ("razorpay_payment_id", "VARCHAR(100)"),
                ("razorpay_signature", "VARCHAR(255)"),
                ("is_mock", "BOOLEAN DEFAULT 0"),
                ("paid_at", "TIMESTAMP"),
                ("extra_metadata", "JSON DEFAULT '{}'")
            ]:
                try:
                    await conn.execute(text(f"ALTER TABLE payments ADD COLUMN {col} {col_type}"))
                except Exception:
                    pass

            # local_leads
            for col, col_type in [
                ("contact_email_source", "VARCHAR(100)"),
                ("contact_verified", "BOOLEAN DEFAULT 0"),
                ("contact_verification_reason", "VARCHAR(255)")
            ]:
                try:
                    await conn.execute(text(f"ALTER TABLE local_leads ADD COLUMN {col} {col_type}"))
                except Exception:
                    pass

            # local_outreach_messages
            for col, col_type in [
                ("provider", "VARCHAR(50)"),
                ("provider_message_id", "VARCHAR(100)"),
                ("reply_to", "VARCHAR(255)"),
                ("evidence_used", "JSON DEFAULT '{}'")
            ]:
                try:
                    await conn.execute(text(f"ALTER TABLE local_outreach_messages ADD COLUMN {col} {col_type}"))
                except Exception:
                    pass

            # outreach_messages
            for col, col_type in [
                ("provider", "VARCHAR(50)"),
                ("provider_message_id", "VARCHAR(100)"),
                ("reply_to", "VARCHAR(255)"),
                ("evidence_used", "JSON DEFAULT '{}'")
            ]:
                try:
                    await conn.execute(text(f"ALTER TABLE outreach_messages ADD COLUMN {col} {col_type}"))
                except Exception:
                    pass

            # suppression_list
            try:
                await conn.execute(text("ALTER TABLE suppression_list ADD COLUMN phone VARCHAR(50)"))
            except Exception:
                pass

            # prospect_memories
            for col, col_type in [
                ("objection_history", "JSON DEFAULT '[]'"),
                ("proposal_history", "JSON DEFAULT '[]'"),
                ("meeting_history", "JSON DEFAULT '[]'"),
                ("payment_history", "JSON DEFAULT '[]'"),
                ("human_decisions", "JSON DEFAULT '[]'"),
                ("suppression_state", "JSON DEFAULT '{}'"),
                ("commercial_context", "JSON DEFAULT '{}'")
            ]:
                try:
                    await conn.execute(text(f"ALTER TABLE prospect_memories ADD COLUMN {col} {col_type}"))
                except Exception:
                    pass

            # businesses (Phase 12 Real Prospect Evidence & Scoring)
            for col, col_type in [
                ("evidence_count", "INTEGER DEFAULT 0"),
                ("effective_evidence_score", "REAL DEFAULT 0.0"),
                ("evidence_confidence", "REAL DEFAULT 0.0"),
                ("research_status", "VARCHAR(50) DEFAULT 'RESEARCH_REQUIRED'"),
                ("prospect_score", "REAL DEFAULT 0.0")
            ]:
                try:
                    await conn.execute(text(f"ALTER TABLE businesses ADD COLUMN {col} {col_type}"))
                except Exception:
                    pass

            # prospect_evidence (Phase 13 Real Provenance & Verification)
            for col, col_type in [
                ("http_status", "INTEGER DEFAULT 200"),
                ("content_hash", "VARCHAR(64)"),
                ("verification_status", "VARCHAR(50) DEFAULT 'UNVERIFIED'"),
                ("verification_reason", "TEXT"),
                ("business_identity_match", "BOOLEAN DEFAULT 0"),
                ("source_independence_group", "VARCHAR(255)")
            ]:
                try:
                    await conn.execute(text(f"ALTER TABLE prospect_evidence ADD COLUMN {col} {col_type}"))
                except Exception:
                    pass

            # call_logs (Phase 17 Voice Operations)
            for col, col_type in [
                ("call_state", "VARCHAR(50) DEFAULT 'CALL_INITIATED'"),
                ("previous_state", "VARCHAR(50)"),
                ("escalation_reason", "VARCHAR(255)"),
                ("agreed_price", "REAL"),
                ("objections_detected", "JSON DEFAULT '[]'"),
                ("context_json", "JSON DEFAULT '{}'")
            ]:
                try:
                    await conn.execute(text(f"ALTER TABLE call_logs ADD COLUMN {col} {col_type}"))
                except Exception:
                    pass

            # users (Client portal & customer linking)
            for col, col_type in [
                ("customer_id", "INTEGER REFERENCES customers(id)")
            ]:
                try:
                    await conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {col_type}"))
                except Exception:
                    pass


