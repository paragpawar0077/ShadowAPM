"""
Shared database layer for ShadowAPM.

Every service (proxy, sandbox-api, chaos-engine, anomaly-detector, rca-agent)
imports this module so they all read/write the same telemetry store.

Uses SQLAlchemy so the same code works against:
  - SQLite (zero-config local dev, DATABASE_URL unset)
  - PostgreSQL / TimescaleDB (docker-compose, DATABASE_URL set)

This satisfies NFR-03 (open-source, free-tier deployable) since no paid
database service is required at any point.
"""
import os
import uuid
import datetime as dt
from sqlalchemy import (
    create_engine, Column, String, Float, Integer, Boolean, DateTime, JSON, Text
)
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:////data/shadowapm.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def new_id() -> str:
    return uuid.uuid4().hex


class TelemetryEvent(Base):
    """One row per request handled by the production path or the sandbox replica."""
    __tablename__ = "telemetry_events"

    id = Column(String, primary_key=True, default=new_id)
    request_id = Column(String, index=True, nullable=False)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, index=True)
    source = Column(String, nullable=False)          # "production" | "sandbox"
    method = Column(String, nullable=False)
    path = Column(String, nullable=False, index=True)
    status_code = Column(Integer, nullable=True)
    latency_ms = Column(Float, nullable=True)
    is_chaos = Column(Boolean, default=False)
    fault_type = Column(String, nullable=True)        # e.g. "latency", "error_5xx", "timeout"
    error = Column(Text, nullable=True)
    extra = Column(JSON, nullable=True)


class ChaosExperiment(Base):
    """A configured chaos experiment. Read by the sandbox replica before handling a mirrored request."""
    __tablename__ = "chaos_experiments"

    id = Column(String, primary_key=True, default=new_id)
    name = Column(String, nullable=False)
    target_path = Column(String, nullable=False)      # path prefix this experiment applies to, or "*"
    fault_type = Column(String, nullable=False)        # "latency" | "error_5xx" | "timeout" | "dependency_failure"
    params = Column(JSON, default=dict)                # e.g. {"delay_ms": 800} or {"status": 503}
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class AnomalyScore(Base):
    """Isolation Forest output for a telemetry event."""
    __tablename__ = "anomaly_scores"

    id = Column(String, primary_key=True, default=new_id)
    request_id = Column(String, index=True, nullable=False)
    score = Column(Float, nullable=False)              # raw isolation-forest decision_function score
    is_anomaly = Column(Boolean, nullable=False)
    model_version = Column(String, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class RCAReport(Base):
    """LLM-generated (or rule-based fallback) root-cause explanation for an anomalous request/experiment."""
    __tablename__ = "rca_reports"

    id = Column(String, primary_key=True, default=new_id)
    request_id = Column(String, index=True, nullable=True)
    experiment_id = Column(String, index=True, nullable=True)
    summary = Column(Text, nullable=False)
    root_cause = Column(Text, nullable=False)
    confidence = Column(String, nullable=True)          # "high" | "medium" | "low"
    evidence = Column(JSON, nullable=True)               # the actual telemetry rows used, for verifiability
    generated_by = Column(String, nullable=True)          # "ollama:<model>" | "rule-based-fallback"
    created_at = Column(DateTime, default=dt.datetime.utcnow)


def init_db():
    os.makedirs("/data", exist_ok=True) if DATABASE_URL.startswith("sqlite") else None
    Base.metadata.create_all(engine)


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
