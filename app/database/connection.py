from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

class Base(DeclarativeBase):
    pass

from sqlalchemy import event, text

# Async engine for async queries (FastAPI, background tasks)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True
)

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if "sqlite" in settings.DATABASE_URL:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
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
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    """Initializes the database schema, enables WAL mode, and creates all tables."""
    import app.database.models  # noqa
    import app.models.entities  # noqa
    async with engine.begin() as conn:
        if "sqlite" in settings.DATABASE_URL:
            await conn.execute(text("PRAGMA journal_mode=WAL;"))
            await conn.execute(text("PRAGMA busy_timeout=5000;"))
        await conn.run_sync(Base.metadata.create_all)
        # Safe migration for new discovery columns if tables already existed
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

        # Safe migration for payments table
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

        # Safe migration for local_leads table
        for col, col_type in [
            ("contact_email_source", "VARCHAR(100)"),
            ("contact_verified", "BOOLEAN DEFAULT 0"),
            ("contact_verification_reason", "VARCHAR(255)")
        ]:
            try:
                await conn.execute(text(f"ALTER TABLE local_leads ADD COLUMN {col} {col_type}"))
            except Exception:
                pass

        # Safe migration for local_outreach_messages table
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

        # Safe migration for outreach_messages table
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

        # Safe migration for suppression_list table
        try:
            await conn.execute(text("ALTER TABLE suppression_list ADD COLUMN phone VARCHAR(50)"))
        except Exception:
            pass
