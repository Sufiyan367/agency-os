"""Alembic migration 002: Autonomous Customer Support, Incident Memory & Maintenance Engine.

Revision ID: 002_mega7_support
Revises: 001_initial_schema
Create Date: 2026-09-13 19:30:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from app.database.connection import Base
import app.database.models
import app.database.ml_models

revision: str = '002_mega7_support'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # Create any missing tables registered in Base.metadata
    Base.metadata.create_all(bind=bind)

    # In SQLite, if tables already existed without the new columns, ensure columns exist
    inspector = sa.inspect(bind)
    
    # 1. support_tickets columns
    st_cols = {c["name"] for c in inspector.get_columns("support_tickets")}
    new_st_cols = [
        ("priority", sa.String(50), "MEDIUM"),
        ("assigned_agent", sa.String(100), None),
        ("correlation_id", sa.String(100), None),
        ("resolution", sa.Text(), None),
        ("customer_visible_summary", sa.Text(), None),
        ("response_at", sa.DateTime(), None),
        ("first_action_at", sa.DateTime(), None),
        ("sla_breached", sa.Boolean(), False),
    ]
    for col_name, col_type, default_val in new_st_cols:
        if col_name not in st_cols:
            op.add_column("support_tickets", sa.Column(col_name, col_type, nullable=True))

    # 2. customer_incidents columns
    ci_cols = {c["name"] for c in inspector.get_columns("customer_incidents")}
    new_ci_cols = [
        ("project_id", sa.Integer(), None),
        ("category", sa.String(100), "APPLICATION"),
        ("affected_component", sa.String(100), None),
        ("status", sa.String(50), "DETECTED"),
        ("diagnostic_summary", sa.JSON(), None),
        ("root_cause", sa.Text(), None),
        ("impact", sa.Text(), None),
        ("remediation_plan", sa.JSON(), None),
        ("fix_version", sa.String(50), None),
        ("deployment_id", sa.Integer(), None),
        ("verification_result", sa.JSON(), None),
        ("postmortem_reference", sa.String(255), None),
        ("reported_at", sa.DateTime(), None),
    ]
    for col_name, col_type, default_val in new_ci_cols:
        if col_name not in ci_cols:
            op.add_column("customer_incidents", sa.Column(col_name, col_type, nullable=True))


def downgrade() -> None:
    pass
