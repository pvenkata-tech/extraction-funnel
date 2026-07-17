"""
SQLAlchemy models for the four tables that cover almost every extraction-at-scale
system: file_registry, extraction_run, extracted_field, hitl_review — plus two
modality-specific tables (column_profile for CSV, section_chunk for PDF).
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _uuid():
    return uuid.uuid4()


class FileRegistry(Base):
    """Every raw file that lands, CSV or PDF. Checksum dedup is non-negotiable."""
    __tablename__ = "file_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_uri = Column(Text, nullable=False)
    file_type = Column(String(16), nullable=False)  # 'csv' | 'pdf'
    source_system = Column(String(64))
    schema_version = Column(Integer)
    checksum = Column(String(64), nullable=False)
    row_count = Column(Integer)
    page_count = Column(Integer)
    lexical_match = Column(Boolean)  # PDF only: survived the cheap keyword gate?
    ingest_status = Column(String(32), default="received")
    received_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)

    __table_args__ = (UniqueConstraint("checksum", name="uq_file_registry_checksum"),)

    runs = relationship("ExtractionRun", back_populates="file", cascade="all, delete-orphan")
    fields = relationship("ExtractedField", back_populates="file", cascade="all, delete-orphan")
    columns = relationship("ColumnProfile", back_populates="file", cascade="all, delete-orphan")
    chunks = relationship("SectionChunk", back_populates="file", cascade="all, delete-orphan")


class ExtractionRun(Base):
    """One row per (file, stage) — lets a partially-processed file resume without redoing work."""
    __tablename__ = "extraction_run"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    file_id = Column(UUID(as_uuid=True), ForeignKey("file_registry.id"), nullable=False)
    stage = Column(String(32), nullable=False)  # ingest|filter|target|precision|store
    status = Column(String(16), default="pending")  # pending|running|done|failed
    error = Column(Text)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    file = relationship("FileRegistry", back_populates="runs")

    __table_args__ = (UniqueConstraint("file_id", "stage", name="uq_run_file_stage"),)


class ColumnProfile(Base):
    """CSV only: per-column null-rate + missingness classification (MCAR/MAR/MNAR)."""
    __tablename__ = "column_profile"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    file_id = Column(UUID(as_uuid=True), ForeignKey("file_registry.id"), nullable=False)
    column_name = Column(String(128), nullable=False)
    inferred_type = Column(String(32))
    null_rate = Column(Numeric(5, 4))
    missingness_class = Column(String(8))  # MCAR | MAR | MNAR | NONE
    distinct_count = Column(Integer)

    file = relationship("FileRegistry", back_populates="columns")


class SectionChunk(Base):
    """PDF only: section-scoped passages produced by the chunker, only for lexical-match docs."""
    __tablename__ = "section_chunk"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    file_id = Column(UUID(as_uuid=True), ForeignKey("file_registry.id"), nullable=False)
    section_name = Column(String(64))  # recitals | indemnification | limitation_of_liability | ...
    text = Column(Text, nullable=False)
    full_section_text = Column(Text)  # wider context used by the verify pass
    page_number = Column(Integer)

    file = relationship("FileRegistry", back_populates="chunks")


class ExtractedField(Base):
    """The single structured-store table both archetypes write to. Confidence + provenance always."""
    __tablename__ = "extracted_field"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    file_id = Column(UUID(as_uuid=True), ForeignKey("file_registry.id"), nullable=False)
    entity_key = Column(String(128))  # vendor id, account id, contract id, etc.
    field_name = Column(String(128), nullable=False)
    value = Column(Text)
    confidence = Column(Numeric(4, 3), nullable=False, default=1.0)
    extraction_method = Column(String(16), nullable=False)  # rule|imputed|backfilled|llm|human_review
    negation_detected = Column(Boolean, default=False)
    extraction_pass = Column(SmallInteger, default=1)  # 1 = first pass, 2 = verify pass
    source_ref = Column(JSONB)  # {"source_chunk_id": ..., "source_file_id": ..., "evidence_span": ...}
    extracted_at = Column(DateTime, default=datetime.utcnow)

    file = relationship("FileRegistry", back_populates="fields")
    hitl_reviews = relationship("HitlReview", back_populates="extracted_field", cascade="all, delete-orphan")


class HitlReview(Base):
    """Human review queue for low-confidence or MNAR-flagged extractions."""
    __tablename__ = "hitl_review"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    extracted_field_id = Column(UUID(as_uuid=True), ForeignKey("extracted_field.id"), nullable=False)
    reason = Column(String(64), nullable=False)  # low_confidence | mnar_suspected | negation_ambiguous
    reviewer_id = Column(String(64))
    resolution = Column(String(16))  # accepted | corrected | rejected
    corrected_value = Column(Text)
    reviewed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    extracted_field = relationship("ExtractedField", back_populates="hitl_reviews")


class AuditLog(Base):
    """
    Every LLM call, prompt, and output — mandatory once sensitive/regulated data
    is anywhere near the pipeline. Also the observability trail: latency, token
    counts, and estimated cost per call, so a prompt or model change shows up as
    a number (see scripts/llm_cost_report.py) instead of a vibe.
    """
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    file_id = Column(UUID(as_uuid=True), ForeignKey("file_registry.id"))
    model = Column(String(64))
    prompt = Column(Text)
    response = Column(Text)
    latency_ms = Column(Integer)
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    estimated_cost_usd = Column(Numeric(10, 6))
    created_at = Column(DateTime, default=datetime.utcnow)
