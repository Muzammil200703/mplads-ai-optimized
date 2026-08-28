import os
import time
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query, Path, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct, case, text, or_
import io
import csv

from database import engine, Base, SessionLocal
import models
from schemas import ProjectCreate
from ml.predictor import predict_risk

# Create tables
Base.metadata.create_all(bind=engine)

# ═══════════════ STALE PROGRESS DETECTION CONFIG ═══════════════
# Projects above this sanctioned-amount threshold with zero progress
# and zero expenditure are flagged as "possibly stale" data rather
# than automatically treated as anomalous.
STALE_PROGRESS_AMOUNT_THRESHOLD = 10 * 100000  # ₹10 lakh

# Known financial years in the dataset (newest first)
_KNOWN_FYS = ["2026-27", "2025-26", "2024-25", "2023-24"]


def _check_stale_progress(project):
    """
    Check if a project's zero-progress/zero-expenditure record
    may indicate stale (un-updated) data rather than genuine anomalies.

    Returns a dict:
        flag: "POSSIBLY_STALE" | "INSUFFICIENT_DATA" | "NORMAL"
        reason: human-readable explanation
        sanctioned_amount: float
        expenditure: float
        completion: float
    """
    sanctioned = float(getattr(project, "sanctioned_amount", 0) or 0)
    expenditure = float(getattr(project, "expenditure", 0) or 0)
    completion = float(getattr(project, "completion_percentage", 0) or 0)
    status_str = str(getattr(project, "status", "") or "").lower()
    fy = str(getattr(project, "fy", "") or "")

    # If any values are missing/None, treat as insufficient data
    if sanctioned is None or expenditure is None or completion is None:
        return {
            "flag": "INSUFFICIENT_DATA",
            "reason": "Insufficient project data to assess progress status.",
            "sanctioned_amount": sanctioned or 0,
            "expenditure": expenditure or 0,
            "completion": completion or 0,
        }

    # Only flag if: high sanctioned amount AND zero progress AND zero expenditure
    if (sanctioned >= STALE_PROGRESS_AMOUNT_THRESHOLD
            and completion == 0
            and expenditure == 0):

        # Build the reason
        sanctioned_display = f"₹{sanctioned / 100000:.1f} L" if sanctioned < 10000000 else f"₹{sanctioned / 10000000:.2f} Cr"
        reason = (
            f"{sanctioned_display} sanctioned but 0% progress and ₹0 expenditure recorded. "
            f"Progress data may require updating."
        )

        # If we have FY info, add a note about age
        if fy and fy in _KNOWN_FYS:
            fy_index = _KNOWN_FYS.index(fy)
            if fy_index >= 2:  # FY 2024-25 or older
                reason += f" (Financial year: {fy})"

        return {
            "flag": "POSSIBLY_STALE",
            "reason": reason,
            "sanctioned_amount": sanctioned,
            "expenditure": expenditure,
            "completion": completion,
        }

    # Normal — not enough conditions to warrant a flag
    return {
        "flag": "NORMAL",
        "reason": "",
        "sanctioned_amount": sanctioned,
        "expenditure": expenditure,
        "completion": completion,
    }

# In-memory cache for heavy aggregations
_cache: Dict[str, Any] = {}
_cache_ttl: Dict[str, float] = {}

def get_cached(key: str, ttl_seconds: int = 300):
    if key in _cache and (time.time() - _cache_ttl.get(key, 0)) < ttl_seconds:
        return _cache[key]
    return None

def set_cached(key: str, value: Any):
    _cache[key] = value
    _cache_ttl[key] = time.time()

def clear_cache(prefix: Optional[str] = None):
    global _cache, _cache_ttl
    if prefix:
        keys_to_del = [k for k in _cache if k.startswith(prefix)]
        for k in keys_to_del:
            _cache.pop(k, None)
            _cache_ttl.pop(k, None)
    else:
        _cache.clear()
        _cache_ttl.clear()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup indices on existing SQLite tables if not present
    with engine.connect() as conn:
        # Project indexes for search/filter performance
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_proj_state ON projects(state);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_proj_district ON projects(district);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_proj_status ON projects(status);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_proj_type ON projects(project_type);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_proj_constituency ON projects(constituency);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_proj_fy2 ON projects(fy);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_proj_sanctioned ON projects(sanctioned_amount);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_proj_expenditure ON projects(expenditure);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_proj_completion ON projects(completion_percentage);"))
        # Risk score indexes for anomaly/risk queries
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_risk_project ON risk_scores(project_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_risk_level ON risk_scores(risk_level);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_risk_score ON risk_scores(risk_score);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_risk_ml ON risk_scores(ml_anomaly);"))
        # MP summary indexes for name-based search
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mp_name ON mp_summaries(mp_name);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mp_const_state ON mp_summaries(constituency, state);"))
        conn.commit()

    # Add composite indexes for common query patterns
    with engine.connect() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_risk_level_ml ON risk_scores(risk_level, ml_anomaly);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_risk_level_score ON risk_scores(risk_level, risk_score);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_proj_state_fy ON projects(state, fy);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_proj_state_cons ON projects(state, constituency);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_risk_project_level ON risk_scores(project_id, risk_level);"))
        conn.commit()

    # Cache risk table presence at startup (avoids COUNT(*) on every request)
    db = SessionLocal()
    try:
        _cache["_has_risk_table"] = (db.query(func.count(models.RiskScore.id)).scalar() or 0) > 0
        _cache_ttl["_has_risk_table"] = time.time()
    except Exception:
        _cache["_has_risk_table"] = False
        _cache_ttl["_has_risk_table"] = time.time()
    finally:
        db.close()

    # Warm-cache critical endpoints at startup for instant first load
    try:
        db = SessionLocal()
        try:
            # Warm filter_states
            states_rows = db.query(models.Project.state).filter(
                models.Project.state.isnot(None), models.Project.state != ""
            ).distinct().order_by(models.Project.state.asc()).all()
            set_cached("filter_states", [s[0] for s in states_rows if s[0]])

            # Warm filter_fys
            fy_rows = db.query(
                models.Project.fy, func.count(models.Project.id).label("count")
            ).filter(
                models.Project.fy.isnot(None), models.Project.fy != ""
            ).group_by(models.Project.fy).order_by(models.Project.fy.asc()).all()
            set_cached("filter_fys", [{"fy": r.fy, "count": r.count} for r in fy_rows])

            # Warm dashboard_overview (all FY)
            stats = db.query(
                func.count(models.Project.id).label("total_projects"),
                func.coalesce(func.sum(models.Project.sanctioned_amount), 0).label("total_sanctioned"),
                func.coalesce(func.sum(models.Project.expenditure), 0).label("total_expenditure"),
                func.coalesce(func.avg(models.Project.completion_percentage), 0).label("avg_completion"),
                func.count(distinct(models.Project.state)).label("total_states"),
                func.sum(case((models.Project.status.ilike("completed"), 1), else_=0)).label("completed_projects"),
                func.sum(case((models.Project.status.ilike("ongoing"), 1), else_=0)).label("ongoing_projects"),
                func.sum(case((models.Project.status.ilike("recommended"), 1), else_=0)).label("recommended_works")
            ).one()
            total_sanctioned = float(stats.total_sanctioned)
            total_expenditure = float(stats.total_expenditure)
            utilization = (total_expenditure / total_sanctioned * 100) if total_sanctioned > 0 else 0.0
            total_mps = db.query(func.count(models.MPSummary.id)).scalar() or 0
            set_cached("dashboard_overview_all", {
                "total_projects": int(stats.total_projects or 0),
                "completed_projects": int(stats.completed_projects or 0),
                "ongoing_projects": int(stats.ongoing_projects or 0),
                "total_allocated_amount": total_sanctioned,
                "total_sanctioned_amount": total_sanctioned,
                "total_expenditure": total_expenditure,
                "utilization_percentage": round(utilization, 2),
                "average_completion_percentage": round(float(stats.avg_completion or 0), 2),
                "total_mps": total_mps,
                "total_states": int(stats.total_states or 0),
                "recommended_works": int(stats.recommended_works or 0),
            })
        finally:
            db.close()
    except Exception:
        pass  # Warm-cache is best-effort

    yield


app = FastAPI(
    title="MPLADS AI API",
    description="High-performance AI-powered MPLADS monitoring, anomaly detection, and analytics system",
    version="2.0.0",
    lifespan=lifespan
)

# =========================================================
# CORS CONFIGURATION
# =========================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Sortable columns map (avoids SQL injection)
_SORT_COLUMNS = {
    "id": models.Project.id,
    "project_name": models.Project.project_name,
    "state": models.Project.state,
    "district": models.Project.district,
    "constituency": models.Project.constituency,
    "project_type": models.Project.project_type,
    "sanctioned_amount": models.Project.sanctioned_amount,
    "expenditure": models.Project.expenditure,
    "completion_percentage": models.Project.completion_percentage,
    "status": models.Project.status,
    "fy": models.Project.fy,
}


def apply_sort(query, sort_by: Optional[str], sort_dir: Optional[str], model=None):
    """Apply sorting to a SQLAlchemy query safely."""
    if not sort_by:
        return query
    col_key = sort_by.strip().lower()
    if col_key not in _SORT_COLUMNS:
        return query
    col = _SORT_COLUMNS[col_key]
    if sort_dir and sort_dir.strip().lower() == "asc":
        return query.order_by(col.asc().nullslast())
    return query.order_by(col.desc().nullslast())


def _enrich_projects_with_risk(projects, db):
    """Attach risk_scores data to a list of Project objects for API responses.
    This ensures the Projects table, Risk Center, and Project Details all
    use the SAME backend risk score as the single source of truth."""
    if not projects:
        return []
    project_ids = [p.id for p in projects]
    risk_rows = (
        db.query(models.RiskScore)
        .filter(models.RiskScore.project_id.in_(project_ids))
        .all()
    )
    risk_map = {r.project_id: r for r in risk_rows}
    result = []
    for p in projects:
        risk = risk_map.get(p.id)
        item = {
            "id": p.id,
            "project_name": p.project_name,
            "state": p.state,
            "district": p.district,
            "constituency": p.constituency,
            "project_type": p.project_type,
            "sanctioned_amount": p.sanctioned_amount or 0.0,
            "expenditure": p.expenditure or 0.0,
            "completion_percentage": p.completion_percentage or 0.0,
            "status": p.status,
            "fy": p.fy,
            "risk": {
                "risk_score": risk.risk_score if risk else None,
                "risk_level": risk.risk_level if risk else None,
                "ml_anomaly": risk.ml_anomaly if risk else None,
                "reasons": risk.reasons if risk else None,
            } if risk else None,
        }
        result.append(item)
    return result


# =========================================================
# ROOT & HEALTH CHECK
# =========================================================

@app.get("/", tags=["System"])
def root():
    return {
        "service": "MPLADS AI Backend",
        "version": "2.0.0",
        "status": "online",
        "docs_url": "/docs"
    }


@app.get("/health", tags=["System"])
def health_check(db: Session = Depends(get_db)):
    try:
        # Quick ping to DB
        count = db.query(func.count(models.Project.id)).scalar()
        return {
            "status": "healthy",
            "database": "connected",
            "total_projects": count
        }
    except Exception as e:
        return {
            "status": "degraded",
            "database": "error",
            "detail": str(e)
        }


# =========================================================
# FILTERS ENDPOINTS
# =========================================================

@app.get("/filters/states", tags=["Filters"])
def get_filter_states(db: Session = Depends(get_db)):
    cached = get_cached("filter_states", ttl_seconds=600)
    if cached is not None:
        return cached

    states = (
        db.query(models.Project.state)
        .filter(models.Project.state.isnot(None), models.Project.state != "")
        .distinct()
        .order_by(models.Project.state.asc())
        .all()
    )
    result = [s[0] for s in states if s[0]]
    set_cached("filter_states", result)
    return result


@app.get("/filters/districts", tags=["Filters"])
def get_filter_districts(
    state: Optional[str] = Query(None, description="State name to filter districts"),
    db: Session = Depends(get_db)
):
    """Backward-compatible: returns districts if available, else constituencies."""
    if not state:
        return []

    cache_key = f"filter_districts_{state}"
    cached = get_cached(cache_key, ttl_seconds=600)
    if cached is not None:
        return cached

    # The dataset primarily uses the 'constituency' field
    districts = (
        db.query(models.Project.constituency)
        .filter(
            models.Project.state == state,
            models.Project.constituency.isnot(None),
            models.Project.constituency != ""
        )
        .distinct()
        .order_by(models.Project.constituency.asc())
        .all()
    )
    result = [d[0] for d in districts if d[0]]
    set_cached(cache_key, result)
    return result


@app.get("/filters/constituencies", tags=["Filters"])
def get_filter_constituencies(
    state: Optional[str] = Query(None, description="State name to filter constituencies"),
    db: Session = Depends(get_db)
):
    if not state:
        return []

    cache_key = f"filter_constituencies_{state}"
    cached = get_cached(cache_key, ttl_seconds=600)
    if cached is not None:
        return cached

    constituencies = (
        db.query(models.Project.constituency)
        .filter(
            models.Project.state == state,
            models.Project.constituency.isnot(None),
            models.Project.constituency != ""
        )
        .distinct()
        .order_by(models.Project.constituency.asc())
        .all()
    )
    result = [c[0] for c in constituencies if c[0]]
    set_cached(cache_key, result)
    return result
def get_filter_categories(db: Session = Depends(get_db)):
    cached = get_cached("filter_categories", ttl_seconds=600)
    if cached is not None:
        return cached

    categories = (
        db.query(models.Project.project_type)
        .filter(models.Project.project_type.isnot(None), models.Project.project_type != "")
        .distinct()
        .order_by(models.Project.project_type.asc())
        .all()
    )
    result = [c[0] for c in categories if c[0]]
    set_cached("filter_categories", result)
    return result


# =========================================================
# PROJECTS API (OPTIMIZED & PAGINATED)
# =========================================================

@app.post("/projects", tags=["Projects"], status_code=status.HTTP_201_CREATED)
def create_project(
    project: ProjectCreate,
    db: Session = Depends(get_db)
):
    new_project = models.Project(**project.model_dump())
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    clear_cache()
    return new_project


@app.get("/filters/fys", tags=["Filters"])
def get_filter_fys(db: Session = Depends(get_db)):
    """Return available financial years with project counts."""
    cached = get_cached("filter_fys", ttl_seconds=600)
    if cached is not None:
        return cached

    rows = (
        db.query(
            models.Project.fy,
            func.count(models.Project.id).label("count")
        )
        .filter(models.Project.fy.isnot(None), models.Project.fy != "")
        .group_by(models.Project.fy)
        .order_by(models.Project.fy.asc())
        .all()
    )
    result = [{"fy": r.fy, "count": r.count} for r in rows]
    set_cached("filter_fys", result)
    return result


@app.get("/projects", tags=["Projects"])
def get_projects(
    state: Optional[str] = None,
    district: Optional[str] = None,
    constituency: Optional[str] = None,
    fy: Optional[str] = Query(None, description="Filter by financial year: 2023-24, 2024-25, 2025-26, 2026-27"),
    project_type: Optional[str] = None,
    status: Optional[str] = None,
    min_sanctioned_amount: Optional[float] = None,
    max_sanctioned_amount: Optional[float] = None,
    min_expenditure: Optional[float] = None,
    max_expenditure: Optional[float] = None,
    min_completion: Optional[float] = None,
    max_completion: Optional[float] = None,
    risk_level: Optional[str] = Query(None, description="Filter by risk level: High, Medium, Low, None"),
    min_risk_score: Optional[int] = Query(None),
    max_risk_score: Optional[int] = Query(None),
    sort_by: Optional[str] = Query(None, description="Sort column"),
    sort_dir: Optional[str] = Query(None, description="Sort direction: asc or desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    needs_risk_join = risk_level or min_risk_score is not None or max_risk_score is not None
    if needs_risk_join:
        query = (
            db.query(models.Project)
            .join(models.RiskScore, models.Project.id == models.RiskScore.project_id, isouter=True)
        )
    else:
        query = db.query(models.Project)

    if state:
        query = query.filter(models.Project.state == state)
    if district:
        query = query.filter(models.Project.district == district)
    if constituency:
        query = query.filter(models.Project.constituency == constituency)
    if fy:
        query = query.filter(models.Project.fy == fy)
    if project_type:
        query = query.filter(models.Project.project_type == project_type)
    if status:
        query = query.filter(models.Project.status.ilike(status))
    if risk_level:
        query = query.filter(models.RiskScore.risk_level.ilike(risk_level))
    if min_risk_score is not None:
        query = query.filter(models.RiskScore.risk_score >= min_risk_score)
    if max_risk_score is not None:
        query = query.filter(models.RiskScore.risk_score <= max_risk_score)
    if min_sanctioned_amount is not None:
        query = query.filter(models.Project.sanctioned_amount >= min_sanctioned_amount)
    if max_sanctioned_amount is not None:
        query = query.filter(models.Project.sanctioned_amount <= max_sanctioned_amount)
    if min_expenditure is not None:
        query = query.filter(models.Project.expenditure >= min_expenditure)
    if max_expenditure is not None:
        query = query.filter(models.Project.expenditure <= max_expenditure)
    if min_completion is not None:
        query = query.filter(models.Project.completion_percentage >= min_completion)
    if max_completion is not None:
        query = query.filter(models.Project.completion_percentage <= max_completion)

    if sort_by:
        query = apply_sort(query, sort_by, sort_dir)
    else:
        query = query.order_by(models.Project.id.asc())

    projects = query.offset(skip).limit(limit).all()
    return _enrich_projects_with_risk(projects, db)


@app.get("/search/projects", tags=["Projects"])
def search_projects(
    q: Optional[str] = Query(None, description="Search keyword in project name, type, state, district, constituency, or ID"),
    state: Optional[str] = None,
    district: Optional[str] = None,
    constituency: Optional[str] = None,
    fy: Optional[str] = Query(None, description="Filter by financial year"),
    project_type: Optional[str] = None,
    status: Optional[str] = None,
    risk_level: Optional[str] = Query(None, description="Filter by risk level: High, Medium, Low, None"),
    min_sanctioned_amount: Optional[float] = Query(None),
    max_sanctioned_amount: Optional[float] = Query(None),
    min_expenditure: Optional[float] = Query(None),
    max_expenditure: Optional[float] = Query(None),
    min_completion: Optional[float] = Query(None),
    max_completion: Optional[float] = Query(None),
    min_risk_score: Optional[int] = Query(None),
    max_risk_score: Optional[int] = Query(None),
    sort_by: Optional[str] = Query(None, description="Sort column: id, project_name, state, sanctioned_amount, expenditure, completion_percentage, status"),
    sort_dir: Optional[str] = Query(None, description="Sort direction: asc or desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Optimized project search.

    Performance optimizations vs. previous implementation:
    - Short-circuits for exact numeric ID match (indexed PK lookup)
    - Uses EXISTS subqueries for MP name matching (avoids full outerjoin)
    - Skips expensive DISTINCT+COUNT; uses LIMIT+1 for hasMore instead
    - Removes redundant DISTINCT on primary-key results
    """
    q_clean = (q or "").strip()

    # ---------------------------------------------------------------
    # FAST PATH: exact numeric ID match (single indexed PK lookup)
    # ---------------------------------------------------------------
    if q_clean:
        try:
            q_id = int(q_clean)
            project = db.query(models.Project).filter(models.Project.id == q_id).first()
            if project:
                # Apply post-filters to the single result
                if state and project.state != state:
                    return {"total": 0, "skip": 0, "limit": limit, "results": [], "hasMore": False}
                if district and project.district != district:
                    return {"total": 0, "skip": 0, "limit": limit, "results": [], "hasMore": False}
                if constituency and project.constituency != constituency:
                    return {"total": 0, "skip": 0, "limit": limit, "results": [], "hasMore": False}
                if fy and project.fy != fy:
                    return {"total": 0, "skip": 0, "limit": limit, "results": [], "hasMore": False}
                if project_type and project.project_type != project_type:
                    return {"total": 0, "skip": 0, "limit": limit, "results": [], "hasMore": False}
                if min_sanctioned_amount is not None and (project.sanctioned_amount or 0) < min_sanctioned_amount:
                    return {"total": 0, "skip": 0, "limit": limit, "results": [], "hasMore": False}
                if max_sanctioned_amount is not None and (project.sanctioned_amount or 0) > max_sanctioned_amount:
                    return {"total": 0, "skip": 0, "limit": limit, "results": [], "hasMore": False}
                if min_expenditure is not None and (project.expenditure or 0) < min_expenditure:
                    return {"total": 0, "skip": 0, "limit": limit, "results": [], "hasMore": False}
                if max_expenditure is not None and (project.expenditure or 0) > max_expenditure:
                    return {"total": 0, "skip": 0, "limit": limit, "results": [], "hasMore": False}
                if min_completion is not None and (project.completion_percentage or 0) < min_completion:
                    return {"total": 0, "skip": 0, "limit": limit, "results": [], "hasMore": False}
                if max_completion is not None and (project.completion_percentage or 0) > max_completion:
                    return {"total": 0, "skip": 0, "limit": limit, "results": [], "hasMore": False}
                # Risk filters — need to check risk_scores table
                if risk_level or min_risk_score is not None or max_risk_score is not None:
                    risk_row = db.query(models.RiskScore).filter(models.RiskScore.project_id == project.id).first()
                    if not risk_row:
                        return {"total": 0, "skip": 0, "limit": limit, "results": [], "hasMore": False}
                    if risk_level and (risk_row.risk_level or "").lower() != risk_level.lower():
                        return {"total": 0, "skip": 0, "limit": limit, "results": [], "hasMore": False}
                    if min_risk_score is not None and (risk_row.risk_score or 0) < min_risk_score:
                        return {"total": 0, "skip": 0, "limit": limit, "results": [], "hasMore": False}
                    if max_risk_score is not None and (risk_row.risk_score or 0) > max_risk_score:
                        return {"total": 0, "skip": 0, "limit": limit, "results": [], "hasMore": False}
                return {"total": 1, "skip": 0, "limit": limit, "results": _enrich_projects_with_risk([project], db), "hasMore": False}
            # Exact ID not found — fall through to text search below
        except (ValueError, TypeError):
            pass

    # ---------------------------------------------------------------
    # BUILD MAIN QUERY
    # ---------------------------------------------------------------
    needs_risk_join = risk_level or min_risk_score is not None or max_risk_score is not None
    if needs_risk_join:
        query = (
            db.query(models.Project)
            .join(models.RiskScore, models.Project.id == models.RiskScore.project_id, isouter=True)
        )
    else:
        query = db.query(models.Project)

    # ---------------------------------------------------------------
    # TEXT SEARCH — use EXISTS subqueries for MP name (avoids full outerjoin)
    # ---------------------------------------------------------------
    if q_clean:
        ilike_pattern = f"%{q_clean}%"
        or_conditions = [
            models.Project.project_name.ilike(ilike_pattern),
            models.Project.project_type.ilike(ilike_pattern),
            models.Project.state.ilike(ilike_pattern),
            models.Project.district.ilike(ilike_pattern),
            models.Project.constituency.ilike(ilike_pattern),
        ]

        # Only add MP-name subquery if the query looks like it could be a name
        # (all alpha characters, or contains spaces typical of names)
        is_likely_name = q_clean.replace(" ", "").replace(".", "").replace("-", "").isalpha()
        if is_likely_name:
            mp_exists = (
                db.query(models.MPSummary.id)
                .filter(
                    models.MPSummary.mp_name.ilike(ilike_pattern),
                    models.MPSummary.constituency == models.Project.constituency,
                    models.MPSummary.state == models.Project.state,
                )
                .correlate(models.Project)
                .exists()
            )
            or_conditions.append(mp_exists)

        query = query.filter(or_(*or_conditions))

    # ---------------------------------------------------------------
    # STRUCTURAL FILTERS (exact match on indexed columns)
    # ---------------------------------------------------------------
    if state:
        query = query.filter(models.Project.state == state)
    if district:
        query = query.filter(models.Project.district == district)
    if constituency:
        query = query.filter(models.Project.constituency == constituency)
    if fy:
        query = query.filter(models.Project.fy == fy)
    if project_type:
        query = query.filter(models.Project.project_type == project_type)
    if status:
        query = query.filter(models.Project.status.ilike(status))
    if min_sanctioned_amount is not None:
        query = query.filter(models.Project.sanctioned_amount >= min_sanctioned_amount)
    if max_sanctioned_amount is not None:
        query = query.filter(models.Project.sanctioned_amount <= max_sanctioned_amount)
    if min_expenditure is not None:
        query = query.filter(models.Project.expenditure >= min_expenditure)
    if max_expenditure is not None:
        query = query.filter(models.Project.expenditure <= max_expenditure)
    if min_completion is not None:
        query = query.filter(models.Project.completion_percentage >= min_completion)
    if max_completion is not None:
        query = query.filter(models.Project.completion_percentage <= max_completion)
    if risk_level:
        query = query.filter(models.RiskScore.risk_level.ilike(risk_level))
    if min_risk_score is not None:
        query = query.filter(models.RiskScore.risk_score >= min_risk_score)
    if max_risk_score is not None:
        query = query.filter(models.RiskScore.risk_score <= max_risk_score)

    # ---------------------------------------------------------------
    # SORT + PAGINATE — skip expensive COUNT, use LIMIT+1 for hasMore
    # ---------------------------------------------------------------
    if sort_by:
        query = apply_sort(query, sort_by, sort_dir)
    else:
        query = query.order_by(models.Project.id.asc())

    # Fetch one extra row to detect whether more results exist
    projects = query.offset(skip).limit(limit + 1).all()
    has_more = len(projects) > limit
    if has_more:
        projects = projects[:limit]

    enriched = _enrich_projects_with_risk(projects, db)
    return {
        "total": len(projects) + (1 if has_more else 0),
        "skip": skip,
        "limit": limit,
        "results": enriched,
        "hasMore": has_more
    }


@app.get("/projects/{project_id}", tags=["Projects"])
def get_project(
    project_id: int = Path(..., description="The ID of the project"),
    db: Session = Depends(get_db)
):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found"
        )

    # Use pre-computed risk from risk_scores table (single source of truth)
    # This ensures consistency with the Projects table, Risk Center, etc.
    risk_row = db.query(models.RiskScore).filter(models.RiskScore.project_id == project.id).first()
    if risk_row:
        risk_info = {
            "risk_score": risk_row.risk_score,
            "risk_level": risk_row.risk_level,
            "ml_anomaly": risk_row.ml_anomaly,
            "ml_score": risk_row.ml_score,
            "reasons": risk_row.reasons,
        }
    else:
        risk_info = predict_risk(project)
    stale_check = _check_stale_progress(project)

    return {
        "project": {
            "id": project.id,
            "project_name": project.project_name,
            "state": project.state,
            "district": project.district,
            "constituency": project.constituency,
            "project_type": project.project_type,
            "status": project.status,
            "sanctioned_amount": project.sanctioned_amount or 0.0,
            "expenditure": project.expenditure or 0.0,
            "completion_percentage": project.completion_percentage or 0.0,
            "data_quality_flag": stale_check["flag"],
            "data_quality_reason": stale_check["reason"],
        },
        "risk": risk_info
    }


# =========================================================
# DASHBOARD AGGREGATIONS (HIGH PERFORMANCE)
# =========================================================

@app.get("/dashboard/overview", tags=["Dashboard"])
def dashboard_overview(
    fy: Optional[str] = Query(None, description="Filter by financial year"),
    db: Session = Depends(get_db)
):
    cache_key = f"dashboard_overview_{fy or 'all'}"
    cached = get_cached(cache_key, ttl_seconds=60)
    if cached is not None:
        return cached

    # Use warmed cache for the common all-FY case
    if not fy:
        warmed = get_cached("dashboard_overview_all", ttl_seconds=600)
        if warmed is not None:
            set_cached(cache_key, warmed)
            return warmed

    base_q = db.query(models.Project)
    if fy:
        base_q = base_q.filter(models.Project.fy == fy)

    stats = base_q.with_entities(
        func.count(models.Project.id).label("total_projects"),
        func.coalesce(func.sum(models.Project.sanctioned_amount), 0).label("total_sanctioned"),
        func.coalesce(func.sum(models.Project.expenditure), 0).label("total_expenditure"),
        func.coalesce(func.avg(models.Project.completion_percentage), 0).label("avg_completion"),
        func.count(distinct(models.Project.state)).label("total_states"),
        func.sum(case((models.Project.status.ilike("completed"), 1), else_=0)).label("completed_projects"),
        func.sum(case((models.Project.status.ilike("ongoing"), 1), else_=0)).label("ongoing_projects"),
        func.sum(case((models.Project.status.ilike("recommended"), 1), else_=0)).label("recommended_works")
    ).one()

    total_mps = db.query(func.count(models.MPSummary.id)).scalar() or 0

    total_sanctioned = float(stats.total_sanctioned)
    total_expenditure = float(stats.total_expenditure)
    utilization = (total_expenditure / total_sanctioned * 100) if total_sanctioned > 0 else 0.0

    result = {
        "total_projects": int(stats.total_projects or 0),
        "completed_projects": int(stats.completed_projects or 0),
        "ongoing_projects": int(stats.ongoing_projects or 0),
        "total_allocated_amount": total_sanctioned,
        "total_sanctioned_amount": total_sanctioned,
        "total_expenditure": total_expenditure,
        "utilization_percentage": round(utilization, 2),
        "average_completion_percentage": round(float(stats.avg_completion or 0), 2),
        "total_mps": total_mps,
        "total_states": int(stats.total_states or 0),
        "recommended_works": int(stats.recommended_works or 0),
    }

    set_cached(cache_key, result)
    return result


@app.get("/dashboard/states", tags=["Dashboard"])
def dashboard_states(
    fy: Optional[str] = Query(None, description="Filter by financial year"),
    db: Session = Depends(get_db)
):
    cache_key = f"dashboard_states_{fy or 'all'}"
    cached = get_cached(cache_key, ttl_seconds=120)
    if cached is not None:
        return cached

    base_q = db.query(models.Project)
    if fy:
        base_q = base_q.filter(models.Project.fy == fy)

    rows = (
        base_q.with_entities(
            models.Project.state,
            func.count(models.Project.id).label("total_projects"),
            func.sum(case((models.Project.status.ilike("completed"), 1), else_=0)).label("completed_projects"),
            func.sum(case((models.Project.status.ilike("ongoing"), 1), else_=0)).label("ongoing_projects"),
            func.coalesce(func.sum(models.Project.sanctioned_amount), 0).label("total_sanctioned_amount"),
            func.coalesce(func.sum(models.Project.expenditure), 0).label("total_expenditure"),
            func.coalesce(func.avg(models.Project.completion_percentage), 0).label("avg_completion")
        )
        .filter(models.Project.state.isnot(None), models.Project.state != "")
        .group_by(models.Project.state)
        .order_by(func.count(models.Project.id).desc())
        .all()
    )

    result = []
    for row in rows:
        sanctioned = float(row.total_sanctioned_amount)
        spent = float(row.total_expenditure)
        utilization = (spent / sanctioned * 100) if sanctioned > 0 else 0.0

        result.append({
            "state": row.state,
            "total_projects": int(row.total_projects),
            "completed_projects": int(row.completed_projects),
            "ongoing_projects": int(row.ongoing_projects),
            "total_sanctioned_amount": sanctioned,
            "total_expenditure": spent,
            "utilization_percentage": round(utilization, 2),
            "average_completion_percentage": round(float(row.avg_completion), 2)
        })

    set_cached(cache_key, result)
    return result


@app.get("/dashboard/mps", tags=["Dashboard"])
def dashboard_mps(
    state: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    query = db.query(models.MPSummary)
    if state:
        query = query.filter(models.MPSummary.state == state)

    rows = query.limit(limit).all()
    return [
        {
            "id": row.id,
            "mp_name": row.mp_name,
            "state": row.state,
            "constituency": row.constituency,
            "house": row.house,
            "allocated_amount": row.allocated_amount or 0.0,
            "total_expenditure": row.total_expenditure or 0.0,
            "utilization_percentage": row.utilization_percentage or 0.0,
            "completed_works": row.completed_works or 0,
            "recommended_works": row.recommended_works or 0,
            "completion_rate_percentage": row.completion_rate_percentage or 0.0,
            "unspent_amount": row.unspent_amount or 0.0,
            "transaction_count": row.transaction_count or 0,
            "successful_payments": row.successful_payments or 0,
            "pending_payments": row.pending_payments or 0,
            "average_rating": row.average_rating or 0.0
        }
        for row in rows
    ]


@app.get("/dashboard/anomalies-summary", tags=["Dashboard"])
def anomalies_summary(
    fy: Optional[str] = Query(None, description="Filter by financial year"),
    db: Session = Depends(get_db)
):
    cache_key = f"anomalies_summary_{fy or 'all'}"
    cached = get_cached(cache_key, ttl_seconds=300)
    if cached is not None:
        return cached

    # Use cached risk table presence (avoids COUNT(*) every call)
    has_risk_table = _cache.get("_has_risk_table", False)
    if has_risk_table:
        # Single consolidated GROUP BY query instead of 3 separate COUNT + IN subquery
        base_q = (
            db.query(models.RiskScore.risk_level, func.count(models.RiskScore.id).label("cnt"))
            .join(models.Project, models.RiskScore.project_id == models.Project.id)
        )
        if fy:
            base_q = base_q.filter(models.Project.fy == fy)
        rows = base_q.group_by(models.RiskScore.risk_level).all()

        level_map = {"high": 0, "medium": 0, "low": 0}
        for row in rows:
            key = (row.risk_level or "").lower()
            if key in level_map:
                level_map[key] = row.cnt

        total_checked = db.query(func.count(models.Project.id)).filter(
            models.Project.fy == fy if fy else True
        ).scalar() or 0

        result = {
            "total_projects_checked": total_checked,
            "high_risk": level_map["high"],
            "medium_risk": level_map["medium"],
            "low_risk": level_map["low"],
            "total_anomalies": level_map["high"] + level_map["medium"] + level_map["low"]
        }
        set_cached(cache_key, result)
        return result

    # Heuristic calculation — consolidated into fewer queries
    base_q = db.query(models.Project)
    if fy:
        base_q = base_q.filter(models.Project.fy == fy)

    # Single pass with CASE WHEN to count all categories at once
    stats = base_q.with_entities(
        func.count(models.Project.id).label("total"),
        func.sum(case((
            (models.Project.expenditure > models.Project.sanctioned_amount) |
            ((models.Project.sanctioned_amount >= 1000000) & (models.Project.completion_percentage < 25)),
            1), else_=0)).label("high"),
        func.sum(case((
            (models.Project.expenditure > 0) & (models.Project.completion_percentage == 0),
            1), else_=0)).label("medium"),
    ).one()

    total_projects = int(stats.total or 0)
    high_risk = int(stats.high or 0)
    medium_risk = int(stats.medium or 0)
    low_risk = max(0, int(total_projects * 0.02))

    result = {
        "total_projects_checked": total_projects,
        "high_risk": high_risk,
        "medium_risk": medium_risk,
        "low_risk": low_risk,
        "total_anomalies": high_risk + medium_risk + low_risk
    }
    set_cached(cache_key, result)
    return result


@app.post("/dashboard/anomalies-summary/refresh", tags=["Dashboard"])
def refresh_anomalies_summary():
    clear_cache()
    return {"message": "All dashboard and anomaly caches cleared successfully"}


@app.get("/dashboard/constituencies", tags=["Dashboard"])
def dashboard_constituencies(
    state: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = (
        db.query(
            models.Project.constituency,
            models.Project.state,
            func.count(models.Project.id).label("total_projects"),
            func.coalesce(func.sum(models.Project.sanctioned_amount), 0).label("total_sanctioned_amount"),
            func.coalesce(func.sum(models.Project.expenditure), 0).label("total_expenditure"),
            func.coalesce(func.avg(models.Project.completion_percentage), 0).label("avg_completion")
        )
        .filter(models.Project.constituency.isnot(None), models.Project.constituency != "")
    )
    if state:
        query = query.filter(models.Project.state == state)

    rows = query.group_by(models.Project.constituency, models.Project.state).order_by(func.count(models.Project.id).desc()).limit(limit).all()

    return [
        {
            "constituency": r.constituency,
            "state": r.state,
            "total_projects": int(r.total_projects),
            "total_sanctioned_amount": float(r.total_sanctioned_amount),
            "total_expenditure": float(r.total_expenditure),
            "utilization_percentage": round((float(r.total_expenditure) / float(r.total_sanctioned_amount) * 100) if float(r.total_sanctioned_amount) > 0 else 0, 2),
            "average_completion_percentage": round(float(r.avg_completion), 2)
        }
        for r in rows
    ]


@app.get("/dashboard/financials", tags=["Dashboard"])
def dashboard_financials(db: Session = Depends(get_db)):
    cached = get_cached("dashboard_financials", ttl_seconds=120)
    if cached is not None:
        return cached

    stats = db.query(
        func.coalesce(func.sum(models.Project.sanctioned_amount), 0).label("total_sanctioned"),
        func.coalesce(func.sum(models.Project.expenditure), 0).label("total_expenditure"),
        func.count(models.Project.id).label("total_projects"),
        func.coalesce(func.avg(models.Project.expenditure), 0).label("avg_expenditure")
    ).one()

    total_sanctioned = float(stats.total_sanctioned)
    total_expenditure = float(stats.total_expenditure)
    unspent = max(0.0, total_sanctioned - total_expenditure)
    utilization = (total_expenditure / total_sanctioned * 100) if total_sanctioned > 0 else 0.0

    highest = (
        db.query(models.Project)
        .filter(models.Project.expenditure.isnot(None))
        .order_by(models.Project.expenditure.desc())
        .first()
    )

    lowest = (
        db.query(models.Project)
        .filter(models.Project.expenditure.isnot(None), models.Project.expenditure > 0)
        .order_by(models.Project.expenditure.asc())
        .first()
    )

    result = {
        "total_sanctioned_amount": total_sanctioned,
        "total_expenditure": total_expenditure,
        "unspent_amount": unspent,
        "utilization_percentage": round(utilization, 2),
        "average_project_expenditure": round(float(stats.avg_expenditure), 2),
        "highest_expenditure_project": {
            "id": highest.id,
            "project_name": highest.project_name,
            "expenditure": highest.expenditure
        } if highest else None,
        "lowest_expenditure_project": {
            "id": lowest.id,
            "project_name": lowest.project_name,
            "expenditure": lowest.expenditure
        } if lowest else None
    }

    set_cached("dashboard_financials", result)
    return result


@app.get("/dashboard/project-types", tags=["Dashboard"])
def dashboard_project_types(db: Session = Depends(get_db)):
    cached = get_cached("dashboard_project_types", ttl_seconds=180)
    if cached is not None:
        return cached

    rows = (
        db.query(
            models.Project.project_type,
            func.count(models.Project.id).label("total_projects"),
            func.coalesce(func.sum(models.Project.sanctioned_amount), 0).label("total_sanctioned_amount"),
            func.coalesce(func.sum(models.Project.expenditure), 0).label("total_expenditure"),
            func.coalesce(func.avg(models.Project.completion_percentage), 0).label("avg_completion")
        )
        .filter(models.Project.project_type.isnot(None), models.Project.project_type != "")
        .group_by(models.Project.project_type)
        .order_by(func.count(models.Project.id).desc())
        .all()
    )

    result = []
    for r in rows:
        sanctioned = float(r.total_sanctioned_amount)
        spent = float(r.total_expenditure)
        utilization = (spent / sanctioned * 100) if sanctioned > 0 else 0.0
        result.append({
            "project_type": r.project_type,
            "total_projects": int(r.total_projects),
            "total_sanctioned_amount": sanctioned,
            "total_expenditure": spent,
            "utilization_percentage": round(utilization, 2),
            "average_completion_percentage": round(float(r.avg_completion), 2)
        })

    set_cached("dashboard_project_types", result)
    return result


# =========================================================
# MP SUMMARY, RECOMMENDED, COMPLETED & EXPENDITURES
# =========================================================

@app.get("/mp-summary", tags=["MP Operations"])
def get_mp_summary(
    state: Optional[str] = None,
    mp_name: Optional[str] = None,
    constituency: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db)
):
    query = db.query(models.MPSummary)
    if state:
        query = query.filter(models.MPSummary.state == state)
    if mp_name:
        query = query.filter(models.MPSummary.mp_name.ilike(f"%{mp_name}%"))
    if constituency:
        query = query.filter(models.MPSummary.constituency.ilike(f"%{constituency}%"))

    return query.offset(skip).limit(limit).all()


@app.get("/recommended-works", tags=["MP Operations"])
def get_recommended_works(
    state: Optional[str] = None,
    constituency: Optional[str] = None,
    category: Optional[str] = None,
    mp_name: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    query = db.query(models.RecommendedWork)
    if state:
        query = query.filter(models.RecommendedWork.state == state)
    if constituency:
        query = query.filter(models.RecommendedWork.constituency == constituency)
    if category:
        query = query.filter(models.RecommendedWork.category == category)
    if mp_name:
        query = query.filter(models.RecommendedWork.mp_name.ilike(f"%{mp_name}%"))

    return query.offset(skip).limit(limit).all()


@app.get("/expenditures", tags=["MP Operations"])
def get_expenditures(
    state: Optional[str] = None,
    constituency: Optional[str] = None,
    mp_name: Optional[str] = None,
    payment_status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    query = db.query(models.Expenditure)
    if state:
        query = query.filter(models.Expenditure.state == state)
    if constituency:
        query = query.filter(models.Expenditure.constituency == constituency)
    if mp_name:
        query = query.filter(models.Expenditure.mp_name.ilike(f"%{mp_name}%"))
    if payment_status:
        query = query.filter(models.Expenditure.payment_status.ilike(payment_status))

    return query.offset(skip).limit(limit).all()


@app.get("/completed-works", tags=["MP Operations"])
def get_completed_works(
    state: Optional[str] = None,
    constituency: Optional[str] = None,
    category: Optional[str] = None,
    mp_name: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    query = db.query(models.CompletedWork)
    if state:
        query = query.filter(models.CompletedWork.state == state)
    if constituency:
        query = query.filter(models.CompletedWork.constituency == constituency)
    if category:
        query = query.filter(models.CompletedWork.category == category)
    if mp_name:
        query = query.filter(models.CompletedWork.mp_name.ilike(f"%{mp_name}%"))

    return query.offset(skip).limit(limit).all()


# =========================================================
# ANOMALY DETECTION & AI ENDPOINTS
# =========================================================

@app.get("/anomalies", tags=["Anomaly Detection"])
def detect_anomalies(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    risk_level: Optional[str] = None,
    state: Optional[str] = None,
    constituency: Optional[str] = None,
    fy: Optional[str] = Query(None, description="Filter by financial year"),
    q: Optional[str] = Query(None, description="Search by project name or ID"),
    sort_by: Optional[str] = Query(None, description="Sort: risk_score, sanctioned_amount, expenditure, completion_percentage, project_name, state, id"),
    sort_dir: Optional[str] = Query(None, description="Sort direction: asc or desc"),
    db: Session = Depends(get_db)
):
    # Use cached risk table presence flag (set at startup, avoids COUNT(*) on every request)
    has_risk_table = _cache.get("_has_risk_table", False)

    if has_risk_table:
        query = (
            db.query(models.RiskScore, models.Project)
            .join(models.Project, models.RiskScore.project_id == models.Project.id)
        )
        if state:
            query = query.filter(models.Project.state == state)
        if constituency:
            query = query.filter(models.Project.constituency == constituency)
        if fy:
            query = query.filter(models.Project.fy == fy)
        if risk_level:
            query = query.filter(models.RiskScore.risk_level.ilike(risk_level))
        if q:
            q_clean = q.strip()
            try:
                q_id = int(q_clean)
                query = query.filter(
                    (models.Project.id == q_id) |
                    (models.Project.project_name.ilike(f"%{q_clean}%"))
                )
            except (ValueError, TypeError):
                query = query.filter(models.Project.project_name.ilike(f"%{q_clean}%"))

        total_anomalies = query.count()
        # Apply sorting for joined risk+project query
        if sort_by:
            sort_col = sort_by.strip().lower()
            sort_asc = sort_dir and sort_dir.strip().lower() == "asc"
            # Map sort columns to the appropriate model column
            anomaly_sort_map = {
                "risk_score": (models.RiskScore.risk_score, None),
                "sanctioned_amount": (models.Project.sanctioned_amount, None),
                "expenditure": (models.Project.expenditure, None),
                "completion_percentage": (models.Project.completion_percentage, None),
                "project_name": (models.Project.project_name, None),
                "state": (models.Project.state, None),
                "id": (models.Project.id, None),
            }
            if sort_col in anomaly_sort_map:
                col = anomaly_sort_map[sort_col][0]
                rows = query.order_by(col.desc().nullslast() if not sort_asc else col.asc().nullslast()).offset(skip).limit(limit).all()
            else:
                rows = query.order_by(models.RiskScore.risk_score.desc()).offset(skip).limit(limit).all()
        else:
            rows = query.order_by(models.RiskScore.risk_score.desc()).offset(skip).limit(limit).all()


        anomalies_list = []
        for risk, proj in rows:
            reasons = [r.strip() for r in (risk.reasons or "").split(",") if r.strip()]
            anomalies_list.append({
                "project_id": proj.id,
                "project_name": proj.project_name,
                "state": proj.state,
                "district": proj.district,
                "constituency": proj.constituency,
                "project_type": proj.project_type,
                "sanctioned_amount": proj.sanctioned_amount or 0.0,
                "expenditure": proj.expenditure or 0.0,
                "completion_percentage": proj.completion_percentage or 0.0,
                "status": proj.status,
                "risk_score": risk.risk_score,
                "risk_level": risk.risk_level,
                "ml_anomaly": risk.ml_anomaly,
                "ml_score": risk.ml_score,
                "reasons": reasons
            })

        total_checked = db.query(func.count(models.Project.id)).scalar() or 0
        return {
            "total_projects_checked": total_checked,
            "total_anomalies": total_anomalies,
            "skip": skip,
            "limit": limit,
            "anomalies": anomalies_list
        }

    # On-the-fly calculation for paginated candidates
    query = db.query(models.Project)
    if state:
        query = query.filter(models.Project.state == state)

    # Focus candidate scan on projects with potential anomalies
    candidate_query = query.filter(
        (models.Project.expenditure > models.Project.sanctioned_amount) |
        ((models.Project.sanctioned_amount >= 1000000) & (models.Project.completion_percentage < 25)) |
        ((models.Project.expenditure > 0) & (models.Project.completion_percentage == 0)) |
        (models.Project.status.ilike("completed") & (models.Project.completion_percentage < 90))
    )

    total_candidates = candidate_query.count()
    projects = candidate_query.offset(skip).limit(limit).all()

    anomalies = []
    for proj in projects:
        risk_info = predict_risk(proj)
        if risk_info["is_anomaly"]:
            if risk_level and risk_info["risk_level"].lower() != risk_level.lower():
                continue
            anomalies.append({
                "project_id": proj.id,
                "project_name": proj.project_name,
                "state": proj.state,
                "district": proj.district,
                "constituency": proj.constituency,
                "project_type": proj.project_type,
                "sanctioned_amount": proj.sanctioned_amount or 0.0,
                "expenditure": proj.expenditure or 0.0,
                "completion_percentage": proj.completion_percentage or 0.0,
                "status": proj.status,
                "risk_score": risk_info["risk_score"],
                "risk_level": risk_info["risk_level"],
                "ml_anomaly": risk_info["ml_anomaly"],
                "ml_score": risk_info["ml_score"],
                "reasons": risk_info["reasons"]
            })

    total_checked = db.query(func.count(models.Project.id)).scalar() or 0
    return {
        "total_projects_checked": total_checked,
        "total_anomalies": total_candidates,
        "skip": skip,
        "limit": limit,
        "anomalies": anomalies
    }


@app.get("/ai/risk/{project_id}", tags=["AI Operations"])
def get_project_risk(
    project_id: int = Path(..., description="Project ID"),
    db: Session = Depends(get_db)
):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found"
        )

    risk_info = predict_risk(project)
    return {
        "project": {
            "id": project.id,
            "project_name": project.project_name,
            "state": project.state,
            "district": project.district,
            "sanctioned_amount": project.sanctioned_amount,
            "expenditure": project.expenditure,
            "completion_percentage": project.completion_percentage,
            "status": project.status
        },
        "risk": risk_info
    }


@app.get("/ai/risky-projects", tags=["AI Operations"])
def get_risky_projects(
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    has_risk_table = db.query(func.count(models.RiskScore.id)).scalar() or 0

    if has_risk_table > 0:
        risks = (
            db.query(models.RiskScore, models.Project)
            .join(models.Project, models.RiskScore.project_id == models.Project.id)
            .filter(models.RiskScore.risk_score >= 50)
            .order_by(models.RiskScore.risk_score.desc())
            .limit(limit)
            .all()
        )
        projects = []
        for risk, project in risks:
            projects.append({
                "id": project.id,
                "project_name": project.project_name,
                "state": project.state,
                "district": project.district,
                "sanctioned_amount": project.sanctioned_amount,
                "expenditure": project.expenditure,
                "completion_percentage": project.completion_percentage,
                "risk_score": risk.risk_score,
                "risk_level": risk.risk_level,
                "ml_anomaly": risk.ml_anomaly,
                "reasons": [r.strip() for r in (risk.reasons or "").split(",") if r.strip()]
            })

        total = db.query(models.RiskScore).filter(models.RiskScore.risk_score >= 50).count()
        return {
            "total_risky_projects": total,
            "showing": len(projects),
            "projects": projects
        }

    # Fallback to candidate evaluation
    candidates = (
        db.query(models.Project)
        .filter(
            (models.Project.expenditure > models.Project.sanctioned_amount) |
            ((models.Project.sanctioned_amount >= 1000000) & (models.Project.completion_percentage < 25))
        )
        .limit(limit * 2)
        .all()
    )

    scored = []
    for p in candidates:
        r = predict_risk(p)
        scored.append({
            "id": p.id,
            "project_name": p.project_name,
            "state": p.state,
            "district": p.district,
            "sanctioned_amount": p.sanctioned_amount,
            "expenditure": p.expenditure,
            "completion_percentage": p.completion_percentage,
            "risk_score": r["risk_score"],
            "risk_level": r["risk_level"],
            "ml_anomaly": r["ml_anomaly"],
            "reasons": r["reasons"]
        })

    scored.sort(key=lambda x: x["risk_score"], reverse=True)
    top = scored[:limit]

    return {
        "total_risky_projects": len(scored),
        "showing": len(top),
        "projects": top
    }


@app.get("/ai/insights", tags=["AI Operations"])
def get_ai_insights(db: Session = Depends(get_db)):
    cached = get_cached("ai_insights", ttl_seconds=120)
    if cached is not None:
        return cached

    stats = db.query(
        func.count(models.Project.id).label("total"),
        func.sum(case((models.Project.status.ilike("completed"), 1), else_=0)).label("completed"),
        func.sum(case((models.Project.status.ilike("ongoing"), 1), else_=0)).label("ongoing"),
        func.coalesce(func.sum(models.Project.sanctioned_amount), 0).label("sanctioned"),
        func.coalesce(func.sum(models.Project.expenditure), 0).label("expenditure")
    ).one()

    total_projects = int(stats.total or 0)
    total_sanctioned = float(stats.sanctioned or 0)
    total_expenditure = float(stats.expenditure or 0)
    unused_amount = max(0.0, total_sanctioned - total_expenditure)

    # Risk counts
    high_risk_projects = db.query(func.count(models.RiskScore.id)).filter(
        models.RiskScore.risk_level.ilike("high")
    ).scalar() or 0

    if high_risk_projects == 0 and total_projects > 0:
        high_risk_projects = db.query(func.count(models.Project.id)).filter(
            models.Project.expenditure > models.Project.sanctioned_amount
        ).scalar() or 0

    top_states = (
        db.query(models.Project.state, func.count(models.Project.id).label("projects"))
        .filter(models.Project.state.isnot(None), models.Project.state != "")
        .group_by(models.Project.state)
        .order_by(func.count(models.Project.id).desc())
        .limit(5)
        .all()
    )

    result = {
        "overview": {
            "total_projects": total_projects,
            "completed_projects": int(stats.completed or 0),
            "ongoing_projects": int(stats.ongoing or 0)
        },
        "financial_analysis": {
            "total_sanctioned_amount": total_sanctioned,
            "total_expenditure": total_expenditure,
            "unused_amount": unused_amount
        },
        "ai_risk_analysis": {
            "high_risk_projects": high_risk_projects
        },
        "top_states_by_projects": [
            {"state": s[0], "projects": int(s[1])} for s in top_states
        ]
    }

    set_cached("ai_insights", result)
    return result


@app.get("/ai/narrative-insights", tags=["AI Operations"])
def narrative_insights(
    fy: Optional[str] = Query(None, description="Filter by financial year"),
    db: Session = Depends(get_db),
):
    cache_key = f"narrative_insights_{fy or 'all'}"
    cached = get_cached(cache_key, ttl_seconds=120)
    if cached is not None:
        return cached

    base_q = db.query(models.Project)
    if fy:
        base_q = base_q.filter(models.Project.fy == fy)

    insights = []
    stats = base_q.with_entities(
        func.count(models.Project.id).label("total"),
        func.sum(case((models.Project.status.ilike("completed"), 1), else_=0)).label("completed"),
        func.coalesce(func.sum(models.Project.sanctioned_amount), 0).label("sanctioned"),
        func.coalesce(func.sum(models.Project.expenditure), 0).label("expenditure")
    ).one()

    total_projects = int(stats.total or 0)
    sanctioned = float(stats.sanctioned or 0)
    expenditure = float(stats.expenditure or 0)
    completed = int(stats.completed or 0)

    # 1. High risk insight
    risk_q = db.query(func.count(models.RiskScore.id)).filter(
        models.RiskScore.risk_level.ilike("high")
    )
    if fy:
        risk_project_ids = base_q.with_entities(models.Project.id).subquery()
        risk_q = risk_q.filter(models.RiskScore.project_id.in_(risk_project_ids))
    high_risk = risk_q.scalar() or 0

    if high_risk == 0 and total_projects > 0:
        high_risk = base_q.filter(
            models.Project.expenditure > models.Project.sanctioned_amount
        ).count() or 0

    if total_projects > 0:
        pct = (high_risk / total_projects) * 100
        insights.append({
            "type": "risk",
            "title": "High Risk Discrepancies Detected",
            "message": f"{high_risk:,} projects ({pct:.2f}% of monitored portfolio) exhibit significant cost overruns or execution stagnation requiring audit attention."
        })

    # 2. Financial insight
    if sanctioned > 0:
        utilization = (expenditure / sanctioned) * 100
        insights.append({
            "type": "financial",
            "title": "Portfolio Fund Utilization",
            "message": f"Cumulative fund utilization is {utilization:.2f}% (₹{expenditure/1e7:,.2f} Cr spent out of ₹{sanctioned/1e7:,.2f} Cr sanctioned)."
        })

    # 3. Completion insight
    if total_projects > 0:
        comp_rate = (completed / total_projects) * 100
        insights.append({
            "type": "completion",
            "title": "Physical Milestone Progress",
            "message": f"{completed:,} projects completed with an overall completion rate of {comp_rate:.2f}%."
        })

    # 4. Top state insight
    top_state_q = (
        base_q.filter(models.Project.state.isnot(None), models.Project.state != "")
        .with_entities(models.Project.state, func.count(models.Project.id).label("count"))
        .group_by(models.Project.state)
        .order_by(func.count(models.Project.id).desc())
        .first()
    )
    if top_state_q:
        insights.append({
            "type": "geographic",
            "title": "Highest Work Allocation Concentration",
            "message": f"{top_state_q[0]} leads with the highest number of sanctioned works ({top_state_q[1]:,} projects)."
        })

    result = {
        "total_insights": len(insights),
        "insights": insights
    }

    set_cached(cache_key, result)
    return result


@app.get("/ai/state-insights/{state}", tags=["AI Operations"])
def state_insights(
    state: str = Path(..., description="State name"),
    db: Session = Depends(get_db)
):
    stats = (
        db.query(
            func.count(models.Project.id).label("total"),
            func.sum(case((models.Project.status.ilike("completed"), 1), else_=0)).label("completed"),
            func.coalesce(func.sum(models.Project.sanctioned_amount), 0).label("sanctioned"),
            func.coalesce(func.sum(models.Project.expenditure), 0).label("expenditure"),
            func.coalesce(func.avg(models.Project.completion_percentage), 0).label("avg_completion")
        )
        .filter(models.Project.state == state)
        .one()
    )

    if not stats.total or stats.total == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No project data found for state: '{state}'"
        )

    total_projects = int(stats.total)
    completed = int(stats.completed or 0)
    sanctioned = float(stats.sanctioned or 0)
    expenditure = float(stats.expenditure or 0)
    utilization = (expenditure / sanctioned * 100) if sanctioned > 0 else 0.0

    # High risk query via subquery instead of python loop
    high_risk = (
        db.query(func.count(models.RiskScore.id))
        .join(models.Project, models.RiskScore.project_id == models.Project.id)
        .filter(models.Project.state == state, models.RiskScore.risk_level.ilike("high"))
        .scalar() or 0
    )

    top_project_type = (
        db.query(models.Project.project_type, func.count(models.Project.id))
        .filter(models.Project.state == state, models.Project.project_type.isnot(None))
        .group_by(models.Project.project_type)
        .order_by(func.count(models.Project.id).desc())
        .first()
    )

    insights = []
    if utilization < 50:
        insights.append(f"Fund utilization is {utilization:.1f}% (below 50%), requiring heightened financial oversight.")
    elif utilization < 75:
        insights.append(f"Fund utilization is moderate at {utilization:.1f}%.")
    else:
        insights.append(f"Strong fund utilization at {utilization:.1f}%.")

    if total_projects > 0 and (completed / total_projects) < 0.20:
        insights.append(f"Physical completion rate is low ({(completed/total_projects)*100:.1f}%).")

    if high_risk > 0:
        insights.append(f"{high_risk} projects flagged as high risk by AI audit checks.")
    else:
        insights.append("No critical high-risk anomalies detected in this state.")

    return {
        "state": state,
        "summary": {
            "total_projects": total_projects,
            "completed_projects": completed,
            "high_risk_projects": high_risk,
            "average_completion_percentage": round(float(stats.avg_completion), 2)
        },
        "financial": {
            "sanctioned_amount": sanctioned,
            "expenditure": expenditure,
            "utilization_percentage": round(utilization, 2)
        },
        "dominant_project_type": top_project_type[0] if top_project_type else "General",
        "ai_analysis": insights
    }


# =========================================================
# STATE INTELLIGENCE
# =========================================================

@app.get("/dashboard/state-intelligence", tags=["Dashboard"])
def state_intelligence(
    fy: Optional[str] = Query(None, description="Filter by financial year"),
    db: Session = Depends(get_db)
):
    """Return detailed analytics for all states."""
    cache_key = f"state_intelligence_{fy or 'all'}"
    cached = get_cached(cache_key, ttl_seconds=120)
    if cached is not None:
        return cached

    base_q = db.query(models.Project).filter(models.Project.state.isnot(None), models.Project.state != "")
    if fy:
        base_q = base_q.filter(models.Project.fy == fy)

    # Main state stats query
    rows = (
        base_q.with_entities(
            models.Project.state,
            func.count(models.Project.id).label("total_projects"),
            func.sum(case((models.Project.status.ilike("completed"), 1), else_=0)).label("completed_projects"),
            func.sum(case((models.Project.status.ilike("ongoing"), 1), else_=0)).label("ongoing_projects"),
            func.coalesce(func.sum(models.Project.sanctioned_amount), 0).label("total_sanctioned"),
            func.coalesce(func.sum(models.Project.expenditure), 0).label("total_expenditure"),
            func.coalesce(func.avg(models.Project.completion_percentage), 0).label("avg_completion")
        )
        .group_by(models.Project.state)
        .order_by(func.count(models.Project.id).desc())
        .all()
    )

    # High-risk counts per state
    hr_q = (
        db.query(
            models.Project.state,
            func.count(models.RiskScore.id).label("high_risk_count"),
            func.sum(case((models.RiskScore.ml_anomaly == True, 1), else_=0)).label("ml_anomaly_count"),
            func.sum(case((models.RiskScore.risk_level.ilike("high"), 1), else_=0)).label("high_count"),
            func.sum(case((models.RiskScore.risk_level.ilike("medium"), 1), else_=0)).label("medium_count")
        )
        .join(models.RiskScore, models.Project.id == models.RiskScore.project_id)
    )
    if fy:
        hr_q = hr_q.filter(models.Project.fy == fy)
    high_risk_rows = hr_q.group_by(models.Project.state).all()
    risk_map = {r.state: r for r in high_risk_rows}

    result = []
    for row in rows:
        sanctioned = float(row.total_sanctioned)
        spent = float(row.total_expenditure)
        utilization = (spent / sanctioned * 100) if sanctioned > 0 else 0.0
        risk = risk_map.get(row.state)
        result.append({
            "state": row.state,
            "total_projects": int(row.total_projects),
            "completed_projects": int(row.completed_projects),
            "ongoing_projects": int(row.ongoing_projects),
            "total_sanctioned_amount": sanctioned,
            "total_expenditure": spent,
            "utilization_percentage": round(utilization, 2),
            "average_completion_percentage": round(float(row.avg_completion), 2),
            "high_risk_projects": int(risk.high_count) if risk else 0,
            "medium_risk_projects": int(risk.medium_count) if risk else 0,
            "ml_anomaly_projects": int(risk.ml_anomaly_count) if risk else 0,
        })

    set_cached(cache_key, result)
    return result


# =========================================================
# AUDIT PRIORITY QUEUE
# =========================================================

@app.get("/audit-priority/summary", tags=["Anomaly Detection"])
def audit_priority_summary(
    fy: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Return aggregate counts for audit priority KPI cards."""
    base = db.query(models.RiskScore).join(
        models.Project, models.RiskScore.project_id == models.Project.id
    ).filter(models.RiskScore.risk_score > 0)
    if fy:
        base = base.filter(models.Project.fy == fy)

    total = base.count()
    high = base.filter(models.RiskScore.risk_level == "High").count()
    medium = base.filter(models.RiskScore.risk_level == "Medium").count()
    critical = base.filter(models.RiskScore.risk_score >= 80).count()
    ml_count = base.filter(models.RiskScore.ml_anomaly == True).count()

    return {
        "total_flagged": total,
        "high_risk": high,
        "medium_risk": medium,
        "critical": critical,
        "ml_anomalies": ml_count,
    }


@app.get("/audit-priority", tags=["Anomaly Detection"])
def audit_priority(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    state: Optional[str] = None,
    constituency: Optional[str] = None,
    fy: Optional[str] = Query(None, description="Filter by financial year"),
    risk_level: Optional[str] = None,
    q: Optional[str] = None,
    sort_by: Optional[str] = Query(None),
    sort_dir: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Return the highest-priority projects for audit, ranked by risk score."""
    query = (
        db.query(models.RiskScore, models.Project)
        .join(models.Project, models.RiskScore.project_id == models.Project.id)
        .filter(models.RiskScore.risk_score > 0)
    )
    if state:
        query = query.filter(models.Project.state == state)
    if constituency:
        query = query.filter(models.Project.constituency == constituency)
    if fy:
        query = query.filter(models.Project.fy == fy)
    if risk_level:
        query = query.filter(models.RiskScore.risk_level.ilike(risk_level))
    if q:
        q_clean = q.strip()
        try:
            q_id = int(q_clean)
            query = query.filter(
                (models.Project.id == q_id) |
                (models.Project.project_name.ilike(f"%{q_clean}%"))
            )
        except (ValueError, TypeError):
            query = query.filter(models.Project.project_name.ilike(f"%{q_clean}%"))

    total = query.count()

    if sort_by:
        sort_col = sort_by.strip().lower()
        sort_asc = sort_dir and sort_dir.strip().lower() == "asc"
        priority_sort_map = {
            "risk_score": models.RiskScore.risk_score,
            "sanctioned_amount": models.Project.sanctioned_amount,
            "expenditure": models.Project.expenditure,
            "completion_percentage": models.Project.completion_percentage,
            "project_name": models.Project.project_name,
            "state": models.Project.state,
            "id": models.Project.id,
        }
        if sort_col in priority_sort_map:
            col = priority_sort_map[sort_col]
            query = query.order_by(col.desc().nullslast() if not sort_asc else col.asc().nullslast())
        else:
            query = query.order_by(models.RiskScore.risk_score.desc())
    else:
        query = query.order_by(models.RiskScore.risk_score.desc())

    rows = query.offset(skip).limit(limit).all()

    priority_list = []
    for rank, (risk, proj) in enumerate(rows, start=skip + 1):
        reasons = [r.strip() for r in (risk.reasons or "").split(",") if r.strip()]
        # Determine primary anomaly type
        primary = "Unknown"
        if reasons:
            r_lower = reasons[0].lower()
            if "exceeds sanctioned" in r_lower:
                primary = "Cost Overrun"
            elif "high expenditure" in r_lower:
                primary = "Expenditure-Progress Mismatch"
            elif "0% physical completion" in r_lower:
                primary = "Zero Progress Disbursement"
            elif "completed but physical" in r_lower:
                primary = "Status Inconsistency"
            elif "high-value project" in r_lower:
                primary = "High-Value Stalled Project"
            elif "high completion" in r_lower:
                primary = "Completion-Expenditure Mismatch"
            elif "very low fund" in r_lower:
                primary = "Low Fund Utilization"
            elif "ml" in r_lower:
                primary = "ML Statistical Outlier"

        priority_list.append({
            "priority_rank": rank,
            "project_id": proj.id,
            "project_name": proj.project_name,
            "state": proj.state,
            "district": proj.district,
            "constituency": proj.constituency,
            "sanctioned_amount": proj.sanctioned_amount or 0.0,
            "expenditure": proj.expenditure or 0.0,
            "completion_percentage": proj.completion_percentage or 0.0,
            "status": proj.status,
            "risk_score": risk.risk_score,
            "risk_level": risk.risk_level,
            "ml_anomaly": risk.ml_anomaly,
            "primary_anomaly": primary,
            "reasons": reasons
        })

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "priorities": priority_list
    }


# =========================================================
# SERVER-SIDE REPORT EXPORT
# =========================================================
# SIMILAR PROJECTS
# =========================================================

@app.get("/projects/{project_id}/similar", tags=["Projects"])
def get_similar_projects(
    project_id: int = Path(...),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db)
):
    """Find similar projects based on state, category, and sanctioned amount range."""
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Build similarity criteria
    sanctioned = project.sanctioned_amount or 0
    low_range = sanctioned * 0.3
    high_range = sanctioned * 3.0 if sanctioned > 0 else 999999999

    query = (
        db.query(models.Project)
        .filter(models.Project.id != project_id)
        .filter(models.Project.state == project.state)
        .filter(models.Project.project_type == project.project_type)
        .filter(models.Project.sanctioned_amount >= low_range)
        .filter(models.Project.sanctioned_amount <= high_range)
    )

    similar = query.limit(limit).all()

    # Get risk scores for similar projects
    similar_ids = [p.id for p in similar]
    risk_map = {}
    if similar_ids:
        risks = db.query(models.RiskScore).filter(models.RiskScore.project_id.in_(similar_ids)).all()
        risk_map = {r.project_id: r for r in risks}

    result = []
    for p in similar:
        r = risk_map.get(p.id)
        result.append({
            "id": p.id,
            "project_name": p.project_name,
            "state": p.state,
            "district": p.district,
            "constituency": p.constituency,
            "project_type": p.project_type,
            "sanctioned_amount": p.sanctioned_amount or 0,
            "expenditure": p.expenditure or 0,
            "completion_percentage": p.completion_percentage or 0,
            "status": p.status,
            "risk_score": r.risk_score if r else 0,
            "risk_level": r.risk_level if r else "None",
            "ml_anomaly": r.ml_anomaly if r else False,
        })

    return {
        "criteria": {
            "state": project.state,
            "project_type": project.project_type,
            "sanctioned_range": f"{low_range:,.0f} - {high_range:,.0f}"
        },
        "similar_projects": result
    }


# =========================================================
# ANOMALY DISTRIBUTION ANALYTICS
# =========================================================

@app.get("/anomalies/analytics", tags=["Anomaly Detection"])
def anomaly_analytics(
    state: Optional[str] = Query(None),
    constituency: Optional[str] = Query(None),
    fy: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Return anomaly distribution analytics, optionally filtered."""
    cache_key = f"anomaly_analytics_{state or ''}_{constituency or ''}_{fy or ''}"
    cached = get_cached(cache_key, ttl_seconds=300)
    if cached is not None:
        return cached

    # ── QUERY 1: Risk distribution + total + ml_count in a single GROUP BY ──
    base_filter = []
    if state:
        base_filter.append(models.Project.state == state)
    if constituency:
        base_filter.append(models.Project.constituency == constituency)
    if fy:
        base_filter.append(models.Project.fy == fy)

    # Single query: GROUP BY risk_level + aggregate ml_anomaly count
    dist_q = (
        db.query(
            models.RiskScore.risk_level,
            func.count(models.RiskScore.id).label("cnt"),
            func.sum(case((models.RiskScore.ml_anomaly == True, 1), else_=0)).label("ml_cnt")
        )
        .join(models.Project, models.RiskScore.project_id == models.Project.id)
    )
    if base_filter:
        dist_q = dist_q.filter(*base_filter)
    dist_rows = dist_q.group_by(models.RiskScore.risk_level).all()

    total = 0
    level_map = {"high": 0, "medium": 0, "low": 0, "none": 0}
    ml_count = 0
    for row in dist_rows:
        total += row.cnt
        ml_count += int(row.ml_cnt or 0)
        key = (row.risk_level or "").lower()
        if key in level_map:
            level_map[key] = row.cnt

    # ── QUERY 2: Anomaly reasons categorization (Python-side) ──
    reasons_q = (
        db.query(models.RiskScore.reasons)
        .join(models.Project, models.RiskScore.project_id == models.Project.id)
        .filter(models.RiskScore.reasons.isnot(None), models.RiskScore.reasons != "")
    )
    if base_filter:
        reasons_q = reasons_q.filter(*base_filter)
    all_reasons = reasons_q.all()

    type_counts = {}
    for (reasons_str,) in all_reasons:
        for reason in reasons_str.split(","):
            reason = reason.strip()
            if not reason:
                continue
            r_lower = reason.lower()
            if "exceeds sanctioned" in r_lower:
                cat = "Cost Overrun"
            elif "high expenditure" in r_lower:
                cat = "Expenditure-Progress Mismatch"
            elif "0% physical" in r_lower:
                cat = "Zero Progress Disbursement"
            elif "completed but" in r_lower:
                cat = "Status Inconsistency"
            elif "high-value project" in r_lower:
                cat = "High-Value Stalled Project"
            elif "high completion" in r_lower:
                cat = "Completion-Expenditure Mismatch"
            elif "very low fund" in r_lower:
                cat = "Low Fund Utilization"
            elif "ml" in r_lower:
                cat = "ML Statistical Outlier"
            else:
                cat = "Other"
            type_counts[cat] = type_counts.get(cat, 0) + 1

    # ── QUERY 3: State distribution ──
    state_q = (
        db.query(
            models.Project.state,
            func.count(models.RiskScore.id).label("anomaly_count")
        )
        .join(models.RiskScore, models.Project.id == models.RiskScore.project_id)
        .filter(models.RiskScore.risk_score > 0)
    )
    if state:
        state_q = state_q.filter(models.Project.state == state)
    if constituency:
        state_q = state_q.filter(models.Project.constituency == constituency)
    if fy:
        state_q = state_q.filter(models.Project.fy == fy)
    state_rows = (
        state_q.group_by(models.Project.state)
        .order_by(func.count(models.RiskScore.id).desc())
        .limit(10)
        .all()
    )

    # ── QUERY 4: FY distribution ──
    fy_q = (
        db.query(
            models.Project.fy,
            func.count(models.RiskScore.id).label("anomaly_count")
        )
        .join(models.RiskScore, models.Project.id == models.RiskScore.project_id)
        .filter(models.Project.fy.isnot(None), models.Project.fy != "")
    )
    if state:
        fy_q = fy_q.filter(models.Project.state == state)
    if constituency:
        fy_q = fy_q.filter(models.Project.constituency == constituency)
    fy_rows = (
        fy_q.group_by(models.Project.fy)
        .order_by(models.Project.fy.asc())
        .all()
    )

    result = {
        "total_scored": total,
        "risk_distribution": {
            "high": level_map["high"],
            "medium": level_map["medium"],
            "low": level_map["low"],
            "none": level_map["none"],
        },
        "ml_anomaly_count": ml_count,
        "anomaly_types": [
            {"type": k, "count": v, "percentage": round(v / total * 100, 2) if total > 0 else 0}
            for k, v in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        ],
        "state_distribution": [
            {"state": r.state, "count": r.anomaly_count}
            for r in state_rows
        ],
        "fy_distribution": [
            {"fy": r.fy, "count": r.anomaly_count}
            for r in fy_rows
        ],
    }

    set_cached(cache_key, result)
    return result


@app.get("/anomalies/scatter-data", tags=["Anomaly Detection"])
def anomaly_scatter_data(
    state: Optional[str] = Query(None),
    constituency: Optional[str] = Query(None),
    fy: Optional[str] = Query(None),
    limit: int = Query(2000, ge=100, le=5000),
    db: Session = Depends(get_db),
):
    """Return sampled project data for scatter plot: expenditure ratio vs physical progress."""
    cache_key = f"scatter_data_{state or ''}_{constituency or ''}_{fy or ''}_{limit}"
    cached = get_cached(cache_key, ttl_seconds=300)
    if cached is not None:
        return cached

    q = (
        db.query(
            models.Project.id,
            models.Project.project_name,
            models.Project.state,
            models.Project.sanctioned_amount,
            models.Project.expenditure,
            models.Project.completion_percentage,
            models.RiskScore.risk_level,
            models.RiskScore.risk_score,
            models.RiskScore.ml_anomaly,
        )
        .join(models.RiskScore, models.Project.id == models.RiskScore.project_id)
        .filter(models.Project.sanctioned_amount > 0)
    )
    if state:
        q = q.filter(models.Project.state == state)
    if constituency:
        q = q.filter(models.Project.constituency == constituency)
    if fy:
        q = q.filter(models.Project.fy == fy)

    rows = q.limit(limit).all()
    result = [
        {
            "id": r.id,
            "name": r.project_name or "",
            "state": r.state or "",
            "expenditure_ratio": round((r.expenditure or 0) / r.sanctioned_amount * 100, 2) if r.sanctioned_amount > 0 else 0,
            "progress": r.completion_percentage or 0,
            "sanctioned": r.sanctioned_amount or 0,
            "expenditure": r.expenditure or 0,
            "risk_level": r.risk_level or "None",
            "risk_score": r.risk_score or 0,
            "ml_anomaly": bool(r.ml_anomaly),
        }
        for r in rows
    ]

    set_cached(cache_key, result)
    return result


# =========================================================
# SERVER-SIDE REPORT EXPORT
# =========================================================

@app.get("/export/report", tags=["Export"])
def export_report(
    report_type: str = Query("Project Audit Report", description="Report type"),
    state: Optional[str] = Query(None),
    constituency: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    fy: Optional[str] = Query(None, description="Filter by financial year"),
    status: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_dir: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Generate a CSV report server-side using the full dataset."""
    _constituency = constituency or district  # backward compat
    # Build query based on report type
    if report_type == "Anomaly Summary Report" and risk_level:
        query = (
            db.query(models.RiskScore, models.Project)
            .join(models.Project, models.RiskScore.project_id == models.Project.id)
        )
        if state:
            query = query.filter(models.Project.state == state)
        if _constituency:
            query = query.filter(models.Project.constituency == _constituency)
        if fy:
            query = query.filter(models.Project.fy == fy)
        if risk_level:
            query = query.filter(models.RiskScore.risk_level.ilike(risk_level))

        rows = query.order_by(models.RiskScore.risk_score.desc()).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Project ID", "Project Name", "State", "Constituency",
            "Category", "Sanctioned Amount", "Expenditure", "Progress %",
            "Status", "Risk Score", "Risk Level", "ML Anomaly", "Anomaly Reasons"
        ])
        for risk, proj in rows:
            reasons = [r.strip() for r in (risk.reasons or "").split(",") if r.strip()]
            writer.writerow([
                proj.id,
                proj.project_name or "",
                proj.state or "",
                proj.constituency or "",
                proj.project_type or "",
                proj.sanctioned_amount or 0,
                proj.expenditure or 0,
                proj.completion_percentage or 0,
                proj.status or "",
                risk.risk_score,
                risk.risk_level,
                "Yes" if risk.ml_anomaly else "No",
                "; ".join(reasons)
            ])
    else:
        # Project Audit Report or other types
        query = db.query(models.Project)
    if state:
        query = query.filter(models.Project.state == state)
    if _constituency:
        query = query.filter(models.Project.constituency == _constituency)
    if fy:
        query = query.filter(models.Project.fy == fy)
    if status:
        query = query.filter(models.Project.status.ilike(status))

    if sort_by:
        query = apply_sort(query, sort_by, sort_dir)
    else:
        query = query.order_by(models.Project.id.asc())
    rows = query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Project ID", "Project Name", "State", "Constituency",
        "Category", "Sanctioned Amount", "Expenditure", "Progress %",
        "Status"
    ])
    for proj in rows:
        writer.writerow([
            proj.id,
            proj.project_name or "",
            proj.state or "",
            proj.constituency or "",
            proj.project_type or "",
            proj.sanctioned_amount or 0,
            proj.expenditure or 0,
            proj.completion_percentage or 0,
            proj.status or ""
        ])

    # Generate filename
    import datetime
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    scope = state or "AllStates"
    filename = f"MPLADS_{report_type.replace(' ', '_')}_{scope}_{date_str}.csv"

    # Reset cursor and create response
    output.seek(0)
    csv_bytes = output.getvalue().encode("utf-8-sig")  # BOM for Excel compat
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/export/report-count", tags=["Export"])
def export_report_count(
    report_type: str = Query("Project Audit Report"),
    state: Optional[str] = Query(None),
    constituency: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    fy: Optional[str] = Query(None, description="Filter by financial year"),
    status: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Return the count of records that would be exported."""
    _constituency = constituency or district  # backward compat
    if report_type == "Anomaly Summary Report" and risk_level:
        query = (
            db.query(func.count(models.RiskScore.id))
            .join(models.Project, models.RiskScore.project_id == models.Project.id)
        )
        if state:
            query = query.filter(models.Project.state == state)
        if _constituency:
            query = query.filter(models.Project.constituency == _constituency)
        if fy:
            query = query.filter(models.Project.fy == fy)
        if risk_level:
            query = query.filter(models.RiskScore.risk_level.ilike(risk_level))
        total = query.scalar() or 0
    else:
        query = db.query(func.count(models.Project.id))
        if state:
            query = query.filter(models.Project.state == state)
        if _constituency:
            query = query.filter(models.Project.constituency == _constituency)
        if fy:
            query = query.filter(models.Project.fy == fy)
        if status:
            query = query.filter(models.Project.status.ilike(status))
        total = query.scalar() or 0

    return {"total_records": total}


# =========================================================
# DATA QUALITY MONITOR
# =========================================================

@app.get("/data-quality", tags=["Data Quality"])
def data_quality_check(db: Session = Depends(get_db)):
    """Analyze the dataset for data quality issues."""
    cached = get_cached("data_quality", ttl_seconds=300)
    if cached is not None:
        return cached

    total = db.query(func.count(models.Project.id)).scalar() or 0
    issues = []

    # 1. Missing project names
    no_name = db.query(func.count(models.Project.id)).filter(
        (models.Project.project_name.is_(None)) | (models.Project.project_name == "")
    ).scalar() or 0
    if no_name > 0:
        issues.append({
            "category": "Missing Data",
            "severity": "Warning",
            "field": "project_name",
            "description": f"{no_name:,} records have missing or empty project names",
            "count": no_name,
            "percentage": round(no_name / total * 100, 2) if total > 0 else 0
        })

    # 2. Missing state
    no_state = db.query(func.count(models.Project.id)).filter(
        (models.Project.state.is_(None)) | (models.Project.state == "")
    ).scalar() or 0
    if no_state > 0:
        issues.append({
            "category": "Missing Data",
            "severity": "Warning",
            "field": "state",
            "description": f"{no_state:,} records have missing or empty state",
            "count": no_state,
            "percentage": round(no_state / total * 100, 2) if total > 0 else 0
        })

    # 3. Missing district
    no_district = db.query(func.count(models.Project.id)).filter(
        (models.Project.district.is_(None)) | (models.Project.district == "")
    ).scalar() or 0
    if no_district > 0:
        issues.append({
            "category": "Missing Data",
            "severity": "Warning",
            "field": "district",
            "description": f"{no_district:,} records have missing or empty district",
            "count": no_district,
            "percentage": round(no_district / total * 100, 2) if total > 0 else 0
        })

    # 4. Missing status
    no_status = db.query(func.count(models.Project.id)).filter(
        (models.Project.status.is_(None)) | (models.Project.status == "")
    ).scalar() or 0
    if no_status > 0:
        issues.append({
            "category": "Missing Data",
            "severity": "Warning",
            "field": "status",
            "description": f"{no_status:,} records have missing or empty status",
            "count": no_status,
            "percentage": round(no_status / total * 100, 2) if total > 0 else 0
        })

    # 5. Null sanctioned amount
    no_sanctioned = db.query(func.count(models.Project.id)).filter(
        (models.Project.sanctioned_amount.is_(None))
    ).scalar() or 0
    if no_sanctioned > 0:
        issues.append({
            "category": "Invalid Financial",
            "severity": "Critical",
            "field": "sanctioned_amount",
            "description": f"{no_sanctioned:,} records have NULL sanctioned amounts",
            "count": no_sanctioned,
            "percentage": round(no_sanctioned / total * 100, 2) if total > 0 else 0
        })

    # 6. Zero sanctioned amount (valid but suspicious)
    zero_sanctioned = db.query(func.count(models.Project.id)).filter(
        models.Project.sanctioned_amount == 0
    ).scalar() or 0
    if zero_sanctioned > 0:
        issues.append({
            "category": "Invalid Financial",
            "severity": "Warning",
            "field": "sanctioned_amount",
            "description": f"{zero_sanctioned:,} records have zero sanctioned amount",
            "count": zero_sanctioned,
            "percentage": round(zero_sanctioned / total * 100, 2) if total > 0 else 0
        })

    # 7. Negative sanctioned amount
    neg_sanctioned = db.query(func.count(models.Project.id)).filter(
        models.Project.sanctioned_amount < 0
    ).scalar() or 0
    if neg_sanctioned > 0:
        issues.append({
            "category": "Invalid Financial",
            "severity": "Critical",
            "field": "sanctioned_amount",
            "description": f"{neg_sanctioned:,} records have negative sanctioned amounts",
            "count": neg_sanctioned,
            "percentage": round(neg_sanctioned / total * 100, 2) if total > 0 else 0
        })

    # 8. Negative expenditure
    neg_expenditure = db.query(func.count(models.Project.id)).filter(
        models.Project.expenditure < 0
    ).scalar() or 0
    if neg_expenditure > 0:
        issues.append({
            "category": "Invalid Financial",
            "severity": "Critical",
            "field": "expenditure",
            "description": f"{neg_expenditure:,} records have negative expenditure values",
            "count": neg_expenditure,
            "percentage": round(neg_expenditure / total * 100, 2) if total > 0 else 0
        })

    # 9. Progress outside 0-100%
    invalid_progress = db.query(func.count(models.Project.id)).filter(
        (
            (models.Project.completion_percentage < 0) |
            (models.Project.completion_percentage > 100)
        ) & (models.Project.completion_percentage.isnot(None))
    ).scalar() or 0
    if invalid_progress > 0:
        issues.append({
            "category": "Invalid Progress",
            "severity": "Critical",
            "field": "completion_percentage",
            "description": f"{invalid_progress:,} records have progress values outside 0-100%",
            "count": invalid_progress,
            "percentage": round(invalid_progress / total * 100, 2) if total > 0 else 0
        })

    # 10. Status/Progress inconsistency (completed + <90%)
    status_progress_mismatch = db.query(func.count(models.Project.id)).filter(
        models.Project.status.ilike("completed"),
        models.Project.completion_percentage < 90
    ).scalar() or 0
    if status_progress_mismatch > 0:
        issues.append({
            "category": "Inconsistency",
            "severity": "Warning",
            "field": "status vs completion_percentage",
            "description": f"{status_progress_mismatch:,} records marked 'Completed' but progress < 90%",
            "count": status_progress_mismatch,
            "percentage": round(status_progress_mismatch / total * 100, 2) if total > 0 else 0
        })

    # 11. Expenditure > Sanctioned (potential overrun)
    overspent = db.query(func.count(models.Project.id)).filter(
        models.Project.expenditure > models.Project.sanctioned_amount,
        models.Project.sanctioned_amount > 0
    ).scalar() or 0
    if overspent > 0:
        issues.append({
            "category": "Inconsistency",
            "severity": "Critical",
            "field": "expenditure vs sanctioned_amount",
            "description": f"{overspent:,} records have expenditure exceeding sanctioned amount",
            "count": overspent,
            "percentage": round(overspent / total * 100, 2) if total > 0 else 0
        })

    # 12. Zero expenditure with progress > 0
    zero_exp_with_progress = db.query(func.count(models.Project.id)).filter(
        models.Project.expenditure == 0,
        models.Project.completion_percentage > 0
    ).scalar() or 0
    if zero_exp_with_progress > 0:
        issues.append({
            "category": "Inconsistency",
            "severity": "Warning",
            "field": "expenditure vs completion_percentage",
            "description": f"{zero_exp_with_progress:,} records show progress > 0% but zero expenditure",
            "count": zero_exp_with_progress,
            "percentage": round(zero_exp_with_progress / total * 100, 2) if total > 0 else 0
        })

    # 13. Duplicate IDs check
    dup_query = db.query(
        models.Project.id, func.count(models.Project.id).label("cnt")
    ).group_by(models.Project.id).having(func.count(models.Project.id) > 1)
    dup_count = dup_query.count()
    if dup_count > 0:
        issues.append({
            "category": "Duplicate Data",
            "severity": "Critical",
            "field": "id",
            "description": f"{dup_count} duplicate project IDs found",
            "count": dup_count,
            "percentage": round(dup_count / total * 100, 2) if total > 0 else 0
        })

    total_issues = sum(i["count"] for i in issues)
    records_with_issues = (
        db.query(func.count(func.distinct(models.Project.id))).filter(
            (
                (models.Project.project_name.is_(None)) |
                (models.Project.project_name == "") |
                (models.Project.state.is_(None)) |
                (models.Project.state == "") |
                (models.Project.sanctioned_amount.is_(None)) |
                (models.Project.sanctioned_amount < 0) |
                (models.Project.expenditure < 0) |
                (
                    (models.Project.completion_percentage < 0) |
                    (models.Project.completion_percentage > 100)
                ) & (models.Project.completion_percentage.isnot(None)) |
                (
                    models.Project.expenditure > models.Project.sanctioned_amount
                ) & (models.Project.sanctioned_amount > 0)
            )
        ).scalar() or 0
    )

    result = {
        "total_records_checked": total,
        "records_with_issues": records_with_issues,
        "total_issues": total_issues,
        "issue_categories": len(issues),
        "percentage_affected": round(records_with_issues / total * 100, 2) if total > 0 else 0,
        "issues": issues
    }

    set_cached("data_quality", result)
    return result


@app.get("/data-quality/records", tags=["Data Quality"])
def data_quality_records(
    field: str = Query(..., description="Issue field identifier"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Return project records matching a specific data quality issue type."""
    q = db.query(models.Project)
    flag_reason = ""

    if field == "project_name":
        q = q.filter((models.Project.project_name.is_(None)) | (models.Project.project_name == ""))
        flag_reason = "Project name is missing or empty"
    elif field == "state":
        q = q.filter((models.Project.state.is_(None)) | (models.Project.state == ""))
        flag_reason = "State is missing or empty"
    elif field == "district":
        q = q.filter((models.Project.district.is_(None)) | (models.Project.district == ""))
        flag_reason = "District is missing or empty"
    elif field == "status":
        q = q.filter((models.Project.status.is_(None)) | (models.Project.status == ""))
        flag_reason = "Status is missing or empty"
    elif field == "sanctioned_amount":
        q = q.filter(
            (models.Project.sanctioned_amount.is_(None)) |
            (models.Project.sanctioned_amount == 0) |
            (models.Project.sanctioned_amount < 0)
        )
        flag_reason = "Sanctioned amount is NULL, zero, or negative"
    elif field == "expenditure":
        q = q.filter(models.Project.expenditure < 0)
        flag_reason = "Expenditure is negative"
    elif field == "completion_percentage":
        q = q.filter(
            models.Project.completion_percentage.isnot(None),
            ((models.Project.completion_percentage < 0) | (models.Project.completion_percentage > 100))
        )
        flag_reason = "Progress is outside 0-100% range"
    elif field == "status vs completion_percentage":
        q = q.filter(
            models.Project.status.ilike("completed"),
            models.Project.completion_percentage < 90
        )
        flag_reason = "Status is 'Completed' but progress < 90%"
    elif field == "expenditure vs sanctioned_amount":
        q = q.filter(
            models.Project.expenditure > models.Project.sanctioned_amount,
            models.Project.sanctioned_amount > 0
        )
        flag_reason = "Expenditure exceeds sanctioned amount"
    elif field == "expenditure vs completion_percentage":
        q = q.filter(
            models.Project.expenditure == 0,
            models.Project.completion_percentage > 0
        )
        flag_reason = "Progress > 0% but expenditure is zero"
    elif field == "id":
        # Find duplicate IDs
        dup_subq = (
            db.query(models.Project.id)
            .group_by(models.Project.id)
            .having(func.count(models.Project.id) > 1)
            .subquery()
        )
        q = q.filter(models.Project.id.in_(db.query(dup_subq)))
        flag_reason = "Duplicate project ID"
    else:
        # Unknown field — return empty
        return {"records": [], "total": 0, "flag_reason": "Unknown issue type", "skip": skip, "limit": limit}

    total = q.count()
    records = q.order_by(models.Project.id).offset(skip).limit(limit).all()

    return {
        "records": [
            {
                "id": p.id,
                "project_name": p.project_name or "",
                "state": p.state or "",
                "constituency": p.constituency or "",
                "sanctioned_amount": p.sanctioned_amount or 0,
                "expenditure": p.expenditure or 0,
                "completion_percentage": p.completion_percentage or 0,
                "status": p.status or "",
                "project_type": p.project_type or "",
            }
            for p in records
        ],
        "total": total,
        "flag_reason": flag_reason,
        "skip": skip,
        "limit": limit,
    }


# =========================================================
# FEATURE 1: AI RISK EXPLANATION
# =========================================================

@app.get("/ai/risk-explanation/{project_id}", tags=["AI Operations"])
def get_risk_explanation(
    project_id: int = Path(..., description="Project ID"),
    db: Session = Depends(get_db),
):
    """Return a structured, human-readable explanation of a project's risk score."""
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    risk_info = predict_risk(project)
    sanctioned = float(project.sanctioned_amount or 0)
    expenditure = float(project.expenditure or 0)
    completion = float(project.completion_percentage or 0)
    utilization = (expenditure / sanctioned * 100) if sanctioned > 0 else 0
    status_str = str(project.status or "").lower()

    # Build structured explanation
    contributing_factors = []
    explanation = risk_info.get("explanation", {})
    risk_factors = explanation.get("risk_factors", [])

    for factor in risk_factors:
        contributing_factors.append({
            "factor": factor.get("explanation", ""),
            "source": factor.get("source", "rule"),
            "impact": factor.get("impact", None),
        })

    # If no ML/rule factors, generate transparent data-based explanation
    if not contributing_factors:
        if sanctioned > 0 and expenditure > sanctioned:
            contributing_factors.append({
                "factor": f"Expenditure (₹{expenditure:,.0f}) exceeds sanctioned amount (₹{sanctioned:,.0f})",
                "source": "data",
            })
        if expenditure > 0 and completion == 0:
            contributing_factors.append({
                "factor": f"₹{expenditure:,.0f} spent with 0% physical progress",
                "source": "data",
            })
        if sanctioned > 0 and utilization >= 80 and completion < 50:
            contributing_factors.append({
                "factor": f"Fund utilization at {utilization:.0f}% but physical progress only {completion:.0f}%",
                "source": "data",
            })
        if status_str == "completed" and completion < 90:
            contributing_factors.append({
                "factor": f"Project marked as completed but physical progress is {completion:.0f}%",
                "source": "data",
            })

    # Performance context
    performance_context = {
        "sanctioned_amount": sanctioned,
        "expenditure": expenditure,
        "completion_percentage": completion,
        "fund_utilization_pct": round(utilization, 2),
        "status": project.status or "",
    }

    # Check for stale progress data (separate from ML risk)
    stale_check = _check_stale_progress(project)

    # ── Data Confidence: based on field completeness ──
    fields_present = 0
    fields_total = 4
    if sanctioned > 0: fields_present += 1
    if expenditure > 0: fields_present += 1
    if completion > 0: fields_present += 1
    if project.status and project.status.strip(): fields_present += 1
    data_confidence = "High" if fields_present >= 3 else ("Medium" if fields_present >= 2 else "Low")
    # Zero expenditure + zero progress on sanctioned project → lower confidence
    if sanctioned > 0 and expenditure == 0 and completion == 0:
        data_confidence = "Low"

    # ── Risk Signals breakdown ──
    risk_signals = []
    if sanctioned > 0:
        spend_ratio = (expenditure / sanctioned * 100) if sanctioned > 0 else 0
        risk_signals.append({
            "signal": "Expenditure / Sanction",
            "value": f"{spend_ratio:.1f}%",
            "raw_value": round(spend_ratio, 1),
            "impact": "HIGH" if spend_ratio > 100 else ("MEDIUM" if spend_ratio > 80 else "LOW"),
        })
    else:
        risk_signals.append({"signal": "Expenditure / Sanction", "value": "N/A", "raw_value": None, "impact": "N/A"})

    risk_signals.append({
        "signal": "Reported Physical Progress",
        "value": f"{completion}%",
        "raw_value": completion,
        "impact": "HIGH" if completion == 0 else ("MEDIUM" if completion < 50 else "LOW"),
    })

    if sanctioned > 0:
        risk_signals.append({
            "signal": "Project Value",
            "value": f"₹{sanctioned:,.0f}",
            "raw_value": sanctioned,
            "impact": "MEDIUM" if sanctioned >= 1000000 else "LOW",
        })

    risk_signals.append({
        "signal": "Recorded Expenditure",
        "value": f"₹{expenditure:,.0f}",
        "raw_value": expenditure,
        "impact": "HIGH" if (sanctioned > 0 and expenditure > sanctioned) else ("MEDIUM" if expenditure > 0 else "LOW"),
    })

    # Overspend calculations
    overspend = None
    overspend_pct = None
    if sanctioned > 0 and expenditure > sanctioned:
        overspend = expenditure - sanctioned
        overspend_pct = (overspend / sanctioned) * 100

    # ── Dynamic AI Recommendation ──
    reasons = risk_info.get("reasons", [])
    risk_level = risk_info["risk_level"]
    recommendation = ""
    if risk_level == "High":
        parts = []
        if sanctioned > 0 and expenditure > sanctioned:
            parts.append(f"Expenditure (₹{expenditure:,.0f}) has exceeded the sanctioned amount (₹{sanctioned:,.0f}). Verify expenditure records and check if additional approvals were obtained.")
        if expenditure > 0 and completion == 0:
            parts.append(f"₹{expenditure:,.0f} has been spent but no physical progress is reported. Verify whether work has commenced and obtain the latest progress update.")
        if sanctioned > 0 and completion < 25 and sanctioned >= 1000000:
            parts.append(f"This is a high-value project (₹{sanctioned:,.0f}) with only {completion}% reported progress. Prioritize for field verification.")
        if status_str == "completed" and completion < 90:
            parts.append(f"Project is marked completed but reported progress is {completion}%. Verify completion status against physical verification records.")
        if risk_info.get("ml_anomaly"):
            parts.append("The ML model has flagged this project as a statistical outlier. Cross-reference with peer projects in the same state/constituency.")
        if not parts:
            parts.append(f"Multiple risk indicators are active for this project (score: {risk_info['risk_score']}/100). Prioritize for financial and progress verification.")
        recommendation = " ".join(parts)
        if data_confidence == "Low":
            recommendation += " Note: Data confidence is low — the assessment is based on incomplete project records."
    elif risk_level == "Medium":
        parts = []
        if completion < 50 and expenditure > 0:
            parts.append(f"Physical progress ({completion}%) is below expected levels for the expenditure incurred (₹{expenditure:,.0f}). Monitor for further delays.")
        if risk_info.get("ml_anomaly"):
            parts.append("An ML-detected anomaly is present. Review project context to determine if the deviation is expected.")
        if not parts:
            parts.append(f"Several risk indicators are partially active (score: {risk_info['risk_score']}/100). Schedule periodic review.")
        recommendation = " ".join(parts)
    elif risk_level == "Low":
        recommendation = f"Minor deviations detected (score: {risk_info['risk_score']}/100). No immediate action required; continue routine monitoring."
    else:
        recommendation = "No significant risk indicators detected. Project metrics appear consistent with expected patterns. Continue standard monitoring."

    result = {
        "project_id": project_id,
        "risk_score": risk_info["risk_score"],
        "risk_level": risk_info["risk_level"],
        "summary": explanation.get("summary", f"Risk level: {risk_info['risk_level']}").strip(),
        "contributing_factors": contributing_factors,
        "performance_context": performance_context,
        "data_sufficiency": "sufficient" if (sanctioned > 0 or expenditure > 0) else "limited",
        "ml_anomaly": risk_info.get("ml_anomaly", False),
        "data_quality": {
            "flag": stale_check["flag"],
            "reason": stale_check["reason"],
        },
        # New enhanced fields
        "data_confidence": data_confidence,
        "indicator_count": len(reasons),
        "risk_signals": risk_signals,
        "overspend": overspend,
        "overspend_pct": round(overspend_pct, 1) if overspend_pct else None,
        "ai_recommendation": recommendation,
    }
    return result


# =========================================================
# FEATURE 3: ANOMALY EXPLANATION
# =========================================================

@app.get("/ai/anomaly-explanation/{project_id}", tags=["AI Operations"])
def get_anomaly_explanation(
    project_id: int = Path(..., description="Project ID"),
    db: Session = Depends(get_db),
):
    """Return detailed anomaly explanation for a specific project."""
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    risk_info = predict_risk(project)
    sanctioned = float(project.sanctioned_amount or 0)
    expenditure = float(project.expenditure or 0)
    completion = float(project.completion_percentage or 0)
    utilization = (expenditure / sanctioned * 100) if sanctioned > 0 else 0

    # Get peer stats for expected values
    expected = {}
    explanation = risk_info.get("explanation", {})
    risk_factors = explanation.get("risk_factors", [])

    # Compute expected reference values from peer stats
    from ml.predictor import peer_stats as _peer_stats
    if _peer_stats and project.state:
        state_stats = _peer_stats.get("states", {}).get(project.state, {})
        if state_stats:
            expected = {
                "state_avg_completion": round(state_stats.get("avg_completion", 0), 1),
                "state_median_expenditure": state_stats.get("median_expenditure", 0),
                "state_avg_utilization": round(state_stats.get("avg_utilization", 0), 1),
            }
        national = _peer_stats.get("national", {})
        if national:
            expected["national_avg_completion"] = round(national.get("avg_completion", 0), 1)
            expected["national_avg_utilization"] = round(national.get("avg_utilization", 0), 1)

    # Build detected anomalies list
    detected_anomalies = []

    # Rule-based anomalies
    if sanctioned > 0 and expenditure > sanctioned:
        detected_anomalies.append({
            "type": "Cost Overrun",
            "what": f"Expenditure (₹{expenditure:,.0f}) exceeds sanctioned amount (₹{sanctioned:,.0f})",
            "observed": {"expenditure": expenditure, "sanctioned_amount": sanctioned},
            "expected": {"max_expenditure": sanctioned},
            "severity": "High",
            "source": "rule",
            "factors": ["Expenditure may include unapproved costs", "Sanction limits may have been exceeded"]
        })

    if expenditure > 0 and completion == 0:
        detected_anomalies.append({
            "type": "Zero Progress Disbursement",
            "what": f"₹{expenditure:,.0f} spent but physical progress remains at 0%",
            "observed": {"expenditure": expenditure, "completion": 0},
            "expected": {"expected_completion_at_spend_level": min(100, expenditure / max(sanctioned, 1) * 100)},
            "severity": "High",
            "source": "rule",
            "factors": ["Work may not have commenced", "Expenditure may be for mobilization only"]
        })

    if sanctioned > 0 and utilization >= 80 and completion < 50:
        detected_anomalies.append({
            "type": "Expenditure-Progress Mismatch",
            "what": f"Fund utilization at {utilization:.0f}% but physical progress only {completion:.0f}%",
            "observed": {"utilization_pct": round(utilization, 1), "completion_pct": completion},
            "expected": {"expected_completion": round(utilization, 1)},
            "severity": "Medium",
            "source": "rule",
            "factors": ["Financial and physical progress are significantly out of sync", "May indicate premature payments or data recording issues"]
        })

    if str(project.status or "").lower() == "completed" and completion < 90:
        detected_anomalies.append({
            "type": "Status Inconsistency",
            "what": f"Project marked as completed but physical progress is {completion:.0f}%",
            "observed": {"status": project.status, "completion": completion},
            "expected": {"expected_completion": 100},
            "severity": "Medium",
            "source": "rule",
            "factors": ["Status may be incorrectly recorded", "Project may be partially complete"]
        })

    # ML-based anomaly
    if risk_info.get("ml_anomaly"):
        ml_factors = []
        for rf in risk_factors:
            if rf.get("source") == "ml" and rf.get("explanation"):
                ml_factors.append(rf["explanation"])
        detected_anomalies.append({
            "type": "ML Statistical Outlier",
            "what": "Project exhibits patterns statistically unusual compared to peer projects",
            "observed": {"ml_score": risk_info.get("ml_score", 0)},
            "expected": {},
            "severity": "High" if risk_info["risk_level"] == "High" else "Medium",
            "source": "ml",
            "factors": ml_factors[:3] if ml_factors else ["Statistical deviation detected by ML model"]
        })

    # If no anomalies detected, note it
    if not detected_anomalies:
        detected_anomalies.append({
            "type": "No Anomaly Detected",
            "what": "This project does not show significant anomalous patterns",
            "observed": {},
            "expected": {},
            "severity": "None",
            "source": "data",
            "factors": ["Project metrics are within expected ranges for similar projects"]
        })

    severity = risk_info["risk_level"]

    return {
        "project_id": project_id,
        "risk_score": risk_info["risk_score"],
        "risk_level": severity,
        "detected_anomalies": detected_anomalies,
        "reference_values": expected,
        "project_metrics": {
            "sanctioned_amount": sanctioned,
            "expenditure": expenditure,
            "completion_percentage": completion,
            "fund_utilization_pct": round(utilization, 2),
            "status": project.status or "",
        },
    }


# =========================================================
# FEATURE 4: STATE / CONSTITUENCY BENCHMARKING
# =========================================================

@app.get("/ai/benchmarking", tags=["AI Operations"])
def get_benchmarking(
    state: Optional[str] = Query(None, description="State to benchmark"),
    constituency: Optional[str] = Query(None, description="Constituency to benchmark"),
    fy: Optional[str] = Query(None, description="Financial year filter"),
    db: Session = Depends(get_db),
):
    """Return benchmarking comparison for a state/constituency against national or state averages."""
    if not state and not constituency:
        raise HTTPException(status_code=400, detail="Provide at least a state or constituency")

    cache_key = f"benchmark_{state or ''}_{constituency or ''}_{fy or 'all'}"
    cached = get_cached(cache_key, ttl_seconds=120)
    if cached is not None:
        return cached

    # --- National average ---
    nat_q = db.query(models.Project)
    if fy:
        nat_q = nat_q.filter(models.Project.fy == fy)
    nat_stats = nat_q.with_entities(
        func.count(models.Project.id).label("total"),
        func.coalesce(func.avg(models.Project.completion_percentage), 0).label("avg_completion"),
        func.coalesce(func.sum(models.Project.sanctioned_amount), 0).label("total_sanctioned"),
        func.coalesce(func.sum(models.Project.expenditure), 0).label("total_expenditure"),
        func.sum(case((models.Project.status.ilike("completed"), 1), else_=0)).label("completed"),
        func.sum(case((models.Project.status.ilike("ongoing"), 1), else_=0)).label("ongoing"),
    ).one()

    nat_sanctioned = float(nat_stats.total_sanctioned)
    nat_expenditure = float(nat_stats.total_expenditure)
    national = {
        "total_projects": int(nat_stats.total or 0),
        "avg_completion": round(float(nat_stats.avg_completion), 2),
        "utilization_pct": round((nat_expenditure / nat_sanctioned * 100) if nat_sanctioned > 0 else 0, 2),
        "total_sanctioned": nat_sanctioned,
        "total_expenditure": nat_expenditure,
        "completed_projects": int(nat_stats.completed or 0),
        "ongoing_projects": int(nat_stats.ongoing or 0),
    }

    # National risk stats
    nat_risk_q = db.query(
        func.count(models.RiskScore.id).label("total_risk"),
        func.sum(case((models.RiskScore.risk_level.ilike("high"), 1), else_=0)).label("high_risk"),
        func.coalesce(func.avg(models.RiskScore.risk_score), 0).label("avg_risk_score"),
    )
    if fy:
        nat_risk_q = nat_risk_q.join(models.Project, models.RiskScore.project_id == models.Project.id).filter(models.Project.fy == fy)
    nat_risk = nat_risk_q.one()
    national["high_risk_projects"] = int(nat_risk.high_risk or 0)
    national["avg_risk_score"] = round(float(nat_risk.avg_risk_score), 1)

    # --- State-level stats ---
    state_stats = None
    state_name = state
    if constituency and not state:
        # Infer state from constituency
        state_row = (
            db.query(models.Project.state)
            .filter(models.Project.constituency == constituency, models.Project.state.isnot(None))
            .first()
        )
        if state_row:
            state_name = state_row[0]

    if state_name:
        sq = db.query(models.Project).filter(models.Project.state == state_name)
        if fy:
            sq = sq.filter(models.Project.fy == fy)
        s_stats = sq.with_entities(
            func.count(models.Project.id).label("total"),
            func.coalesce(func.avg(models.Project.completion_percentage), 0).label("avg_completion"),
            func.coalesce(func.sum(models.Project.sanctioned_amount), 0).label("total_sanctioned"),
            func.coalesce(func.sum(models.Project.expenditure), 0).label("total_expenditure"),
            func.sum(case((models.Project.status.ilike("completed"), 1), else_=0)).label("completed"),
            func.sum(case((models.Project.status.ilike("ongoing"), 1), else_=0)).label("ongoing"),
        ).one()

        s_sanctioned = float(s_stats.total_sanctioned)
        s_expenditure = float(s_stats.total_expenditure)
        state_stats = {
            "total_projects": int(s_stats.total or 0),
            "avg_completion": round(float(s_stats.avg_completion), 2),
            "utilization_pct": round((s_expenditure / s_sanctioned * 100) if s_sanctioned > 0 else 0, 2),
            "total_sanctioned": s_sanctioned,
            "total_expenditure": s_expenditure,
            "completed_projects": int(s_stats.completed or 0),
            "ongoing_projects": int(s_stats.ongoing or 0),
        }

        # State risk stats
        sr_q = (
            db.query(
                func.sum(case((models.RiskScore.risk_level.ilike("high"), 1), else_=0)).label("high_risk"),
                func.coalesce(func.avg(models.RiskScore.risk_score), 0).label("avg_risk_score"),
            )
            .join(models.Project, models.RiskScore.project_id == models.Project.id)
            .filter(models.Project.state == state_name)
        )
        if fy:
            sr_q = sr_q.filter(models.Project.fy == fy)
        sr = sr_q.one()
        state_stats["high_risk_projects"] = int(sr.high_risk or 0)
        state_stats["avg_risk_score"] = round(float(sr.avg_risk_score), 1)

    # --- Constituency-level stats ---
    cons_stats = None
    if constituency and state_name:
        cq = db.query(models.Project).filter(
            models.Project.state == state_name,
            models.Project.constituency == constituency,
        )
        if fy:
            cq = cq.filter(models.Project.fy == fy)
        c_stats = cq.with_entities(
            func.count(models.Project.id).label("total"),
            func.coalesce(func.avg(models.Project.completion_percentage), 0).label("avg_completion"),
            func.coalesce(func.sum(models.Project.sanctioned_amount), 0).label("total_sanctioned"),
            func.coalesce(func.sum(models.Project.expenditure), 0).label("total_expenditure"),
            func.sum(case((models.Project.status.ilike("completed"), 1), else_=0)).label("completed"),
            func.sum(case((models.Project.status.ilike("ongoing"), 1), else_=0)).label("ongoing"),
        ).one()

        c_sanctioned = float(c_stats.total_sanctioned)
        c_expenditure = float(c_stats.total_expenditure)
        cons_stats = {
            "total_projects": int(c_stats.total or 0),
            "avg_completion": round(float(c_stats.avg_completion), 2),
            "utilization_pct": round((c_expenditure / c_sanctioned * 100) if c_sanctioned > 0 else 0, 2),
            "total_sanctioned": c_sanctioned,
            "total_expenditure": c_expenditure,
            "completed_projects": int(c_stats.completed or 0),
            "ongoing_projects": int(c_stats.ongoing or 0),
        }

        cr_q = (
            db.query(
                func.sum(case((models.RiskScore.risk_level.ilike("high"), 1), else_=0)).label("high_risk"),
                func.coalesce(func.avg(models.RiskScore.risk_score), 0).label("avg_risk_score"),
            )
            .join(models.Project, models.RiskScore.project_id == models.Project.id)
            .filter(models.Project.state == state_name, models.Project.constituency == constituency)
        )
        if fy:
            cr_q = cr_q.filter(models.Project.fy == fy)
        cr = cr_q.one()
        cons_stats["high_risk_projects"] = int(cr.high_risk or 0)
        cons_stats["avg_risk_score"] = round(float(cr.avg_risk_score), 1)

    # Build comparisons
    comparisons = []

    if state_stats:
        # State vs National
        state_vs_national = []
        metrics = [
            ("avg_completion", "Average Completion", "%", True),
            ("utilization_pct", "Fund Utilization", "%", True),
            ("high_risk_projects", "High-Risk Projects", "", False),
            ("avg_risk_score", "Avg Risk Score", "", False),
        ]
        for key, label, unit, higher_is_better in metrics:
            state_val = state_stats.get(key, 0)
            nat_val = national.get(key, 0)
            diff = state_val - nat_val
            state_vs_national.append({
                "metric": label,
                "selected": state_val,
                "benchmark": nat_val,
                "difference": round(diff, 2),
                "unit": unit,
                "better": diff > 0 if higher_is_better else diff < 0,
            })
        comparisons.append({
            "type": "state_vs_national",
            "label": f"{state_name} vs National Average",
            "selected_name": state_name,
            "benchmark_name": "National Average",
            "metrics": state_vs_national,
        })

    if cons_stats and state_stats:
        # Constituency vs State
        cons_vs_state = []
        for key, label, unit, higher_is_better in metrics:
            cons_val = cons_stats.get(key, 0)
            st_val = state_stats.get(key, 0)
            diff = cons_val - st_val
            cons_vs_state.append({
                "metric": label,
                "selected": cons_val,
                "benchmark": st_val,
                "difference": round(diff, 2),
                "unit": unit,
                "better": diff > 0 if higher_is_better else diff < 0,
            })
        comparisons.append({
            "type": "constituency_vs_state",
            "label": f"{constituency} vs {state_name} Average",
            "selected_name": constituency,
            "benchmark_name": f"{state_name} Average",
            "metrics": cons_vs_state,
        })

    result = {
        "state": state_name,
        "constituency": constituency,
        "fy": fy,
        "national": national,
        "state_stats": state_stats,
        "constituency_stats": cons_stats,
        "comparisons": comparisons,
    }

    set_cached(cache_key, result)
    return result
