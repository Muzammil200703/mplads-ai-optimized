"""
Database Storage Layer
=====================

Source-agnostic database operations for upserting project data.
All providers use this layer — it knows nothing about where
the data came from, only how to write it to the database.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from database import SessionLocal
from models import Project, RecommendedWork, SyncMetadata

logger = logging.getLogger("mplads.storage")


# ─── Sync Metadata ─────────────────────────────────────────────

def record_sync(db, source: str, status: str, **kwargs) -> int:
    """Record a sync event in the database. Returns the record ID."""
    now = datetime.now(timezone.utc).isoformat()
    record = SyncMetadata(
        source=source,
        status=status,
        synced_at=now,
        records_fetched=kwargs.get("records_fetched", 0),
        records_inserted=kwargs.get("records_inserted", 0),
        records_updated=kwargs.get("records_updated", 0),
        records_unchanged=kwargs.get("records_unchanged", 0),
        records_failed=kwargs.get("records_failed", 0),
        source_updated_at=kwargs.get("source_updated_at"),
        error_message=kwargs.get("error_message"),
        details=json.dumps(kwargs.get("details", {})),
    )
    db.add(record)
    db.commit()
    return record.id


def get_last_sync(db=None) -> Optional[Dict[str, Any]]:
    """Get the most recent successful sync record."""
    own_db = db is None
    if own_db:
        db = SessionLocal()
    try:
        record = (
            db.query(SyncMetadata)
            .filter(SyncMetadata.status == "success")
            .order_by(SyncMetadata.id.desc())
            .first()
        )
        if record:
            return {
                "source": record.source,
                "synced_at": record.synced_at,
                "records_fetched": record.records_fetched,
                "records_inserted": record.records_inserted,
                "records_updated": record.records_updated,
                "source_updated_at": record.source_updated_at,
            }
        return None
    finally:
        if own_db:
            db.close()


def get_sync_history(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent sync history."""
    db = SessionLocal()
    try:
        records = (
            db.query(SyncMetadata)
            .order_by(SyncMetadata.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "source": r.source,
                "status": r.status,
                "synced_at": r.synced_at,
                "records_fetched": r.records_fetched,
                "records_inserted": r.records_inserted,
                "records_updated": r.records_updated,
                "records_unchanged": r.records_unchanged,
                "records_failed": r.records_failed,
                "error_message": r.error_message,
                "source_updated_at": r.source_updated_at,
            }
            for r in records
        ]
    finally:
        db.close()


# ─── Project Upsert ────────────────────────────────────────────

def upsert_project(db, project_data: Dict[str, Any]) -> str:
    """
    Upsert a single project record.

    Args:
        db: SQLAlchemy session
        project_data: Dict with canonical field names:
            id, project_name, state, district, constituency,
            project_type, sanctioned_amount, expenditure,
            completion_percentage, status, fy

    Returns:
        'inserted', 'updated', or 'unchanged'
    """
    project_name = project_data.get("project_name", "")
    if not project_name:
        return "failed"

    state = project_data.get("state", "")
    constituency = project_data.get("constituency", "")
    district = project_data.get("district", "")
    sanctioned = project_data.get("sanctioned_amount", 0.0) or 0.0
    expenditure = project_data.get("expenditure", 0.0) or 0.0
    completion = project_data.get("completion_percentage", 0.0) or 0.0
    status_val = project_data.get("status", "") or ""
    fy = project_data.get("fy", "") or ""
    project_type = project_data.get("project_type", "") or ""

    # Try to find existing by ID
    project_id = project_data.get("id")
    existing = None
    if project_id:
        existing = db.query(Project).filter(Project.id == project_id).first()

    if existing:
        changed = False
        for field, value in [
            ("project_name", project_name),
            ("state", state),
            ("district", district),
            ("constituency", constituency),
            ("project_type", project_type),
            ("sanctioned_amount", sanctioned),
            ("expenditure", expenditure),
            ("completion_percentage", completion),
            ("status", status_val),
            ("fy", fy),
        ]:
            current = getattr(existing, field, None)
            if value and current != value:
                setattr(existing, field, value)
                changed = True
        return "updated" if changed else "unchanged"
    else:
        new_project = Project(
            project_name=project_name,
            state=state,
            district=district,
            constituency=constituency,
            project_type=project_type,
            sanctioned_amount=sanctioned,
            expenditure=expenditure,
            completion_percentage=completion,
            status=status_val,
            fy=fy,
        )
        db.add(new_project)
        return "inserted"


def upsert_projects_batch(
    db, projects: List[Dict[str, Any]], batch_size: int = 500
) -> Dict[str, int]:
    """
    Upsert a batch of projects. Returns counts.

    This is source-agnostic — it accepts normalized dicts
    and writes them to the database.
    """
    counts = {"inserted": 0, "updated": 0, "unchanged": 0, "failed": 0}

    for start in range(0, len(projects), batch_size):
        batch = projects[start : start + batch_size]
        for project_data in batch:
            try:
                result = upsert_project(db, project_data)
                if result in counts:
                    counts[result] += 1
                else:
                    counts["failed"] += 1
            except Exception as e:
                logger.warning(f"Failed to upsert project: {e}")
                counts["failed"] += 1
        db.commit()

    return counts


# ─── Recommended Work Upsert ───────────────────────────────────

def upsert_recommended_work(db, work_data: Dict[str, Any]) -> str:
    """
    Upsert a single recommended work record.

    Returns: 'inserted', 'updated', or 'unchanged'
    """
    work_description = work_data.get("work_description", "")
    if not work_description:
        return "failed"

    existing = (
        db.query(RecommendedWork)
        .filter(
            RecommendedWork.work_description == work_description,
            RecommendedWork.mp_name == work_data.get("mp_name", ""),
            RecommendedWork.constituency == work_data.get("constituency", ""),
        )
        .first()
    )

    if existing:
        return "unchanged"

    new_work = RecommendedWork(
        work_description=work_description,
        category=work_data.get("category", "") or "",
        mp_name=work_data.get("mp_name", "") or "",
        constituency=work_data.get("constituency", "") or "",
        state=work_data.get("state", "") or "",
        house=work_data.get("house", "") or "",
        recommended_amount=work_data.get("recommended_amount", 0.0) or 0.0,
        recommendation_date=work_data.get("recommendation_date", "") or "",
        has_images=work_data.get("has_images", False),
        ida=work_data.get("ida", "") or "",
    )
    db.add(new_work)
    return "inserted"


def upsert_recommended_works_batch(
    db, works: List[Dict[str, Any]], batch_size: int = 1000
) -> Dict[str, int]:
    """Upsert a batch of recommended works. Returns counts."""
    counts = {"inserted": 0, "unchanged": 0, "failed": 0}

    for start in range(0, len(works), batch_size):
        batch = works[start : start + batch_size]
        for work_data in batch:
            try:
                result = upsert_recommended_work(db, work_data)
                if result in counts:
                    counts[result] += 1
                else:
                    counts["failed"] += 1
            except Exception as e:
                logger.warning(f"Failed to upsert recommended work: {e}")
                counts["failed"] += 1
        db.commit()

    return counts
