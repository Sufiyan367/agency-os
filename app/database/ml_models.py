import enum
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Text, ForeignKey, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.connection import Base

class ModelStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CANDIDATE = "CANDIDATE"
    ARCHIVED = "ARCHIVED"

class ExperimentStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CONCLUDED = "CONCLUDED"

class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    version_tag: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    model_type: Mapped[str] = mapped_column(String(50), default="deterministic_baseline")
    parameters: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    training_metrics: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(50), default=ModelStatus.ACTIVE.value, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    predictions: Mapped[List["ModelPrediction"]] = relationship("ModelPrediction", back_populates="version_record", lazy="selectin")

class ModelPrediction(Base):
    __tablename__ = "model_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, default=lambda: f"PRED-{uuid.uuid4().hex[:12].upper()}")
    model_name: Mapped[str] = mapped_column(String(100), index=True)
    model_version: Mapped[str] = mapped_column(String(50), ForeignKey("model_versions.version_tag"), index=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)  # business, reply, deal, proposal
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    prediction_type: Mapped[str] = mapped_column(String(50), index=True)  # lead_score, reply_classification, expected_revenue, send_time
    predicted_value: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    features: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    version_record: Mapped[Optional["ModelVersion"]] = relationship("ModelVersion", back_populates="predictions", lazy="selectin")
    outcomes: Mapped[List["Outcome"]] = relationship("Outcome", back_populates="prediction", lazy="selectin")

class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    variants: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(50), default=ExperimentStatus.ACTIVE.value, index=True)
    metrics: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class Outcome(Base):
    __tablename__ = "model_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)  # business, outreach_message, reply, deal
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    prediction_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("model_predictions.prediction_id"), nullable=True, index=True)
    event_name: Mapped[str] = mapped_column(String(100), index=True)  # EMAIL_OPENED, REPLY_RECEIVED, POSITIVE_REPLY, MEETING_BOOKED, DEAL_WON, DEAL_LOST, OPT_OUT
    value: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    prediction: Mapped[Optional["ModelPrediction"]] = relationship("ModelPrediction", back_populates="outcomes", lazy="selectin")
