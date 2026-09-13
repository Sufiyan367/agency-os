"""Alembic migration 003: Mega 8 Intelligence and Optimization Engine tables.

Revision ID: 003_mega8_intelligence
Revises: 002_mega7_support
Create Date: 2026-09-13 21:15:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from app.database.connection import Base
import app.database.models
import app.database.ml_models

revision: str = '003_mega8_intelligence'
down_revision: Union[str, None] = '002_mega7_support'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # Create any missing tables registered in Base.metadata (intelligence_signals, optimization_recommendations, etc.)
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    pass
