import os
import time
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query, Path, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct, case, text
import io
import csv

from database import engine, Base, SessionLocal
import models
from schemas import ProjectCreate
from ml.predictor import predict_risk

# Create tables
Base.metadata.create_all(bind=engine)

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
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_proj_state ON projects(state);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_proj_district ON projects(district);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_proj_status ON projects(status);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_proj_type ON projects(project_type);"))
        conn.commit()
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
    return projects


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
    # Join with risk_scores if risk_level or risk_score filters are used
    needs_risk_join = risk_level or min_risk_score is not None or max_risk_score is not None
    if needs_risk_join:
        query = (
            db.query(models.Project)
            .join(models.RiskScore, models.Project.id == models.RiskScore.project_id, isouter=True)
        )
    else:
        query = db.query(models.Project)

    if q:
        q_clean = q.strip()
        # Try matching by exact numeric ID first
        id_match = None
        try:
            id_match = int(q_clean)
        except (ValueError, TypeError):
            pass

        # Subquery to get MP names for projects via mp_summaries (constituency+state join)
        mp_name_subq = (
            db.query(
                models.MPSummary.constituency,
                models.MPSummary.state,
                models.MPSummary.mp_name
            )
            .filter(
                models.MPSummary.mp_name.isnot(None),
                models.MPSummary.mp_name != ""
            )
            .subquery()
        )

        if id_match is not None:
            # Prioritize exact ID match, but also include fuzzy text matches across all fields
            query = query.outerjoin(
                mp_name_subq,
                (models.Project.constituency == mp_name_subq.c.constituency) &
                (models.Project.state == mp_name_subq.c.state)
            ).filter(
                (models.Project.id == id_match) |
                (models.Project.project_name.ilike(f"%{q_clean}%")) |
                (models.Project.project_type.ilike(f"%{q_clean}%")) |
                (models.Project.state.ilike(f"%{q_clean}%")) |
                (models.Project.district.ilike(f"%{q_clean}%")) |
                (models.Project.constituency.ilike(f"%{q_clean}%")) |
                (mp_name_subq.c.mp_name.ilike(f"%{q_clean}%"))
            )
        else:
            # Text search across name, type, state, district, constituency, MP name
            query = query.outerjoin(
                mp_name_subq,
                (models.Project.constituency == mp_name_subq.c.constituency) &
                (models.Project.state == mp_name_subq.c.state)
            ).filter(
                (models.Project.project_name.ilike(f"%{q_clean}%")) |
                (models.Project.project_type.ilike(f"%{q_clean}%")) |
                (models.Project.state.ilike(f"%{q_clean}%")) |
                (models.Project.district.ilike(f"%{q_clean}%")) |
                (models.Project.constituency.ilike(f"%{q_clean}%")) |
                (mp_name_subq.c.mp_name.ilike(f"%{q_clean}%"))
            )

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

    total = query.with_entities(models.Project.id).distinct().count()
    if sort_by:
        query = apply_sort(query, sort_by, sort_dir)
    else:
        query = query.order_by(models.Project.id.asc())

    projects = query.with_entities(models.Project).distinct().offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "results": projects
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

    risk_info = predict_risk(project)

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
def dashboard_states(db: Session = Depends(get_db)):
    cached = get_cached("dashboard_states", ttl_seconds=120)
    if cached is not None:
        return cached

    # Perform a SINGLE grouped query instead of N+1 loop queries
    rows = (
        db.query(
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

    set_cached("dashboard_states", result)
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
def anomalies_summary(db: Session = Depends(get_db)):
    cached = get_cached("anomalies_summary", ttl_seconds=300)
    if cached is not None:
        return cached

    # Check if precalculated RiskScore table has records
    risk_count = db.query(func.count(models.RiskScore.id)).scalar() or 0
    if risk_count > 0:
        high = db.query(func.count(models.RiskScore.id)).filter(models.RiskScore.risk_level == "High").scalar() or 0
        medium = db.query(func.count(models.RiskScore.id)).filter(models.RiskScore.risk_level == "Medium").scalar() or 0
        low = db.query(func.count(models.RiskScore.id)).filter(models.RiskScore.risk_level == "Low").scalar() or 0
        total_checked = db.query(func.count(models.Project.id)).scalar() or 0

        result = {
            "total_projects_checked": total_checked,
            "high_risk": high,
            "medium_risk": medium,
            "low_risk": low,
            "total_anomalies": high + medium + low
        }
        set_cached("anomalies_summary", result)
        return result

    # Quick heuristic calculation
    overspent = db.query(func.count(models.Project.id)).filter(models.Project.expenditure > models.Project.sanctioned_amount).scalar() or 0
    stalled_high = db.query(func.count(models.Project.id)).filter(
        models.Project.sanctioned_amount >= 1000000,
        models.Project.completion_percentage < 25
    ).scalar() or 0
    zero_progress = db.query(func.count(models.Project.id)).filter(
        models.Project.expenditure > 0,
        models.Project.completion_percentage == 0
    ).scalar() or 0
    total_projects = db.query(func.count(models.Project.id)).scalar() or 0

    high_risk = overspent + stalled_high
    medium_risk = zero_progress
    low_risk = max(0, int(total_projects * 0.02))

    result = {
        "total_projects_checked": total_projects,
        "high_risk": high_risk,
        "medium_risk": medium_risk,
        "low_risk": low_risk,
        "total_anomalies": high_risk + medium_risk + low_risk
    }
    set_cached("anomalies_summary", result)
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
    # If RiskScore table is populated, query it with join
    has_risk_table = db.query(func.count(models.RiskScore.id)).scalar() or 0

    if has_risk_table > 0:
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
def narrative_insights(db: Session = Depends(get_db)):
    cached = get_cached("narrative_insights", ttl_seconds=120)
    if cached is not None:
        return cached

    insights = []
    stats = db.query(
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
    high_risk = db.query(func.count(models.RiskScore.id)).filter(
        models.RiskScore.risk_level.ilike("high")
    ).scalar() or 0

    if high_risk == 0 and total_projects > 0:
        high_risk = db.query(func.count(models.Project.id)).filter(
            models.Project.expenditure > models.Project.sanctioned_amount
        ).scalar() or 0

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
    top_state = (
        db.query(models.Project.state, func.count(models.Project.id).label("count"))
        .filter(models.Project.state.isnot(None), models.Project.state != "")
        .group_by(models.Project.state)
        .order_by(func.count(models.Project.id).desc())
        .first()
    )
    if top_state:
        insights.append({
            "type": "geographic",
            "title": "Highest Work Allocation Concentration",
            "message": f"{top_state[0]} leads with the highest number of sanctioned works ({top_state[1]:,} projects)."
        })

    result = {
        "total_insights": len(insights),
        "insights": insights
    }

    set_cached("narrative_insights", result)
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
def anomaly_analytics(db: Session = Depends(get_db)):
    """Return anomaly distribution analytics."""
    cached = get_cached("anomaly_analytics", ttl_seconds=300)
    if cached is not None:
        return cached

    total = db.query(func.count(models.RiskScore.id)).scalar() or 0

    # Risk level distribution
    high = db.query(func.count(models.RiskScore.id)).filter(models.RiskScore.risk_level.ilike("high")).scalar() or 0
    medium = db.query(func.count(models.RiskScore.id)).filter(models.RiskScore.risk_level.ilike("medium")).scalar() or 0
    low = db.query(func.count(models.RiskScore.id)).filter(models.RiskScore.risk_level.ilike("low")).scalar() or 0
    none_count = db.query(func.count(models.RiskScore.id)).filter(models.RiskScore.risk_level.ilike("none")).scalar() or 0
    ml_count = db.query(func.count(models.RiskScore.id)).filter(models.RiskScore.ml_anomaly == True).scalar() or 0

    # Count by anomaly type (from reasons)
    all_risks = db.query(models.RiskScore.reasons).filter(models.RiskScore.reasons != "").all()
    type_counts = {}
    for (reasons_str,) in all_risks:
        for reason in reasons_str.split(","):
            reason = reason.strip()
            if not reason:
                continue
            # Categorize
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

    # State-wise distribution (top 10)
    state_rows = (
        db.query(
            models.Project.state,
            func.count(models.RiskScore.id).label("anomaly_count")
        )
        .join(models.RiskScore, models.Project.id == models.RiskScore.project_id)
        .filter(models.RiskScore.risk_score > 0)
        .group_by(models.Project.state)
        .order_by(func.count(models.RiskScore.id).desc())
        .limit(10)
        .all()
    )

    result = {
        "total_scored": total,
        "risk_distribution": {
            "high": high,
            "medium": medium,
            "low": low,
            "none": none_count,
        },
        "ml_anomaly_count": ml_count,
        "anomaly_types": [
            {"type": k, "count": v, "percentage": round(v / total * 100, 2) if total > 0 else 0}
            for k, v in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        ],
        "state_distribution": [
            {"state": r.state, "count": r.anomaly_count}
            for r in state_rows
        ]
    }

    set_cached("anomaly_analytics", result)
    return result


# =========================================================
# SERVER-SIDE REPORT EXPORT
# =========================================================

@app.get("/export/report", tags=["Export"])
def export_report(
    report_type: str = Query("Project Audit Report", description="Report type"),
    state: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    fy: Optional[str] = Query(None, description="Filter by financial year"),
    status: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_dir: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Generate a CSV report server-side using the full dataset."""
    # Build query based on report type
    if report_type == "Anomaly Summary Report" and risk_level:
        query = (
            db.query(models.RiskScore, models.Project)
            .join(models.Project, models.RiskScore.project_id == models.Project.id)
        )
        if state:
            query = query.filter(models.Project.state == state)
        if district:
            query = query.filter(models.Project.constituency == district)
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
    if district:
        query = query.filter(models.Project.constituency == district)
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
    district: Optional[str] = Query(None),
    fy: Optional[str] = Query(None, description="Filter by financial year"),
    status: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Return the count of records that would be exported."""
    if report_type == "Anomaly Summary Report" and risk_level:
        query = (
            db.query(func.count(models.RiskScore.id))
            .join(models.Project, models.RiskScore.project_id == models.Project.id)
        )
        if state:
            query = query.filter(models.Project.state == state)
        if district:
            query = query.filter(models.Project.constituency == district)
        if fy:
            query = query.filter(models.Project.fy == fy)
        if risk_level:
            query = query.filter(models.RiskScore.risk_level.ilike(risk_level))
        total = query.scalar() or 0
    else:
        query = db.query(func.count(models.Project.id))
        if state:
            query = query.filter(models.Project.state == state)
        if district:
            query = query.filter(models.Project.constituency == district)
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
