from sqlalchemy import Column, Integer, String, Float, Boolean, Index, DateTime, Text
from database import Base


class User(Base):
    """Registered portal user (auditor/analyst/admin)."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    # 'public' | 'analyst' | 'auditor' | 'admin'
    role = Column(String, index=True, nullable=False, default="analyst")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(String, nullable=False)


class PasswordReset(Base):
    """Single-use password reset token (short-lived)."""

    __tablename__ = "password_resets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    token = Column(String, index=True, nullable=False)
    expires_at = Column(String, nullable=False)
    used = Column(Boolean, nullable=False, default=False)
    created_at = Column(String, nullable=False)


class UserInvestigation(Base):
    """
    Per-user investigation record.

    Complements the shared per-project investigation workspace: the shared
    workspace holds the evidence checklist (derived from real project data),
    while this table records WHICH user opened an investigation, its workflow
    status and the recommendation snapshot generated from actual risk results.
    """

    __tablename__ = "user_investigations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    project_id = Column(Integer, index=True, nullable=False)
    # 'Open' | 'Under Review' | 'Resolved'
    status = Column(String, index=True, nullable=False, default="Open")
    priority_tier = Column(String, index=True)   # P1..P4 at creation (from audit_intel)
    priority_label = Column(String)
    risk_score_at_start = Column(Integer)
    recommendations = Column(Text)  # JSON list — generated from recorded data
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)

    __table_args__ = (
        Index("idx_userinv_user_project", "user_id", "project_id", unique=True),
    )


class SavedProject(Base):
    """A project bookmarked by a user for their investigation workspace."""

    __tablename__ = "saved_projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    project_id = Column(Integer, index=True, nullable=False)
    saved_at = Column(String, nullable=False)

    __table_args__ = (
        Index("idx_saved_user_project", "user_id", "project_id", unique=True),
    )


class AuditCase(Base):
    """An audit case saved from the generated case for one project."""

    __tablename__ = "audit_cases"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    project_id = Column(Integer, index=True, nullable=False)
    case_id = Column(String, index=True, nullable=False)  # from audit_intel generator
    priority_tier = Column(String, index=True)
    priority_label = Column(String)
    risk_score = Column(Integer)
    risk_level = Column(String)
    # 'Open' | 'Under Review' | 'Resolved' — mirrors the linked investigation
    status = Column(String, index=True, nullable=False, default="Open")
    created_at = Column(String, nullable=False)

    __table_args__ = (
        Index("idx_case_user_project", "user_id", "project_id"),
    )

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    project_name = Column(String, index=True)
    state = Column(String, index=True)
    district = Column(String, index=True)
    constituency = Column(String, index=True)
    project_type = Column(String, index=True)
    sanctioned_amount = Column(Float, index=True)
    expenditure = Column(Float, index=True)
    completion_percentage = Column(Float, index=True)
    status = Column(String, index=True)
    fy = Column(String, index=True)

    __table_args__ = (
        Index("idx_project_state_dist", "state", "district"),
        Index("idx_project_state_status", "state", "status"),
        Index("idx_proj_fy", "fy"),
    )


class MPSummary(Base):
    __tablename__ = "mp_summaries"

    id = Column(Integer, primary_key=True, index=True)
    mp_name = Column(String, index=True)
    constituency = Column(String, index=True)
    state = Column(String, index=True)
    house = Column(String)
    allocated_amount = Column(Float)
    total_expenditure = Column(Float)
    utilization_percentage = Column(Float)
    completed_works = Column(Integer)
    recommended_works = Column(Integer)
    completion_rate_percentage = Column(Float)
    unspent_amount = Column(Float)
    transaction_count = Column(Integer)
    successful_payments = Column(Integer)
    pending_payments = Column(Integer)
    average_rating = Column(Float)


class RecommendedWork(Base):
    __tablename__ = "recommended_works"

    id = Column(Integer, primary_key=True, index=True)
    work_id = Column(Integer, index=True)
    work_description = Column(String)
    category = Column(String, index=True)
    mp_name = Column(String, index=True)
    constituency = Column(String, index=True)
    state = Column(String, index=True)
    house = Column(String)
    recommended_amount = Column(Float)
    recommendation_date = Column(String)
    has_images = Column(Boolean)
    ida = Column(String)


class Expenditure(Base):
    __tablename__ = "expenditures"

    id = Column(Integer, primary_key=True, index=True)
    mp_name = Column(String, index=True)
    constituency = Column(String, index=True)
    state = Column(String, index=True)
    house = Column(String)
    work_description = Column(String)
    vendor = Column(String)
    ida = Column(String)
    expenditure_amount = Column(Float)
    expenditure_date = Column(String)
    payment_status = Column(String, index=True)


class CompletedWork(Base):
    __tablename__ = "completed_works"

    id = Column(Integer, primary_key=True, index=True)
    work_id = Column(Integer, index=True)
    work_description = Column(String)
    category = Column(String, index=True)
    mp_name = Column(String, index=True)
    constituency = Column(String, index=True)
    state = Column(String, index=True)
    house = Column(String)
    final_amount = Column(Float)
    completed_date = Column(String)
    has_images = Column(Boolean)
    average_rating = Column(Float)
    ida = Column(String)


class RiskScore(Base):
    __tablename__ = "risk_scores"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, index=True, unique=True)
    ml_anomaly = Column(Boolean, index=True)
    ml_score = Column(Float)
    risk_score = Column(Integer, index=True)
    risk_level = Column(String, index=True)
    reasons = Column(String)

    __table_args__ = (
        Index("idx_risk_level_score", "risk_level", "risk_score"),
    )


class ProjectTimelineEvent(Base):
    """
    Normalized project lifecycle event.

    Built by matching the existing work-level datasets
    (recommended_works, expenditures, completed_works) to projects using
    exact normalized (name, constituency, state) keys. Events are only
    created where the underlying data actually supports them — no dates
    are ever invented.
    """

    __tablename__ = "project_timeline_events"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, index=True, nullable=False)
    # 'recommendation' | 'expenditure' | 'completion' | 'status'
    event_type = Column(String, index=True, nullable=False)
    event_date = Column(String)  # ISO date (YYYY-MM-DD) or empty if unknown
    title = Column(String)
    description = Column(Text)
    amount = Column(Float)              # nullable — not meaningful for all events
    progress_percentage = Column(Float)  # nullable
    source_dataset = Column(String)      # 'recommended_works' | 'expenditures' | 'completed_works' | 'projects'
    source_record_id = Column(String)    # original row id in the source table
    match_confidence = Column(String, index=True)  # 'exact' | 'mp_verified'

    __table_args__ = (
        Index("idx_pte_project_date", "project_id", "event_date"),
    )


class AuditInvestigation(Base):
    """
    An audit investigation workspace for one flagged project.

    Only workflow state created by the user is stored (status, note).
    No project values are copied here — they always come from the
    projects / risk_scores tables so nothing can drift or be fabricated.
    """

    __tablename__ = "audit_investigations"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, index=True, unique=True, nullable=False)
    # 'New' | 'Evidence Required' | 'Under Review' | 'Resolved'
    status = Column(String, index=True, nullable=False, default="New")
    note = Column(Text)
    risk_score_at_start = Column(Integer)
    risk_level_at_start = Column(String)
    priority_tier_at_start = Column(String, index=True)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class AuditEvidenceCheck(Base):
    """One evidence-checklist item inside an audit investigation."""

    __tablename__ = "audit_evidence_checks"

    id = Column(Integer, primary_key=True, index=True)
    investigation_id = Column(Integer, index=True, nullable=False)
    item_key = Column(String, index=True, nullable=False)
    label = Column(String, nullable=False)
    category = Column(String, index=True)
    severity = Column(String, index=True)  # 'high' | 'medium' | 'low'
    rationale = Column(Text)  # grounded, generated from actual project values
    # 'Pending' | 'Verified' | 'Discrepancy Found' | 'Not Applicable'
    status = Column(String, index=True, nullable=False, default="Pending")
    updated_at = Column(String, nullable=False)

    __table_args__ = (
        Index("idx_evidence_inv_item", "investigation_id", "item_key"),
    )


class GeocodeCache(Base):
    """
    Persistent cache of geocoder responses for Satellite Location Intelligence.

    Keyed by the normalized geocoding query (not project id) so different
    projects sharing a place string reuse one outbound call. Payload is the
    full scoring result JSON. Successful resolves are cached indefinitely;
    failures are never cached, so a later retry can succeed.
    """

    __tablename__ = "geocode_cache"

    id = Column(Integer, primary_key=True, index=True)
    query_hash = Column(String, index=True, unique=True)
    query = Column(String)
    payload = Column(Text)       # JSON scoring result
    created_at = Column(String)


class SyncMetadata(Base):
    __tablename__ = "sync_metadata"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, nullable=False)  # 'csv_upload', 'github', 'api', 'manual'
    status = Column(String, nullable=False)  # 'success', 'partial', 'failed'
    records_fetched = Column(Integer, default=0)
    records_inserted = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    records_unchanged = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)
    source_updated_at = Column(String)  # When the source data was last updated (if known)
    synced_at = Column(String, nullable=False)  # When this sync was performed
    error_message = Column(Text)
    details = Column(Text)  # JSON string with additional sync details
