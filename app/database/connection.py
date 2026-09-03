from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

class Base(DeclarativeBase):
    pass

# Async engine for async queries (FastAPI, background tasks)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True
)

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
    """Initializes the database schema and creates all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safe migration for new discovery columns if tables already existed
        from sqlalchemy import text
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
