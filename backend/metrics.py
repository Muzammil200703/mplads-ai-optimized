"""
Authoritative financial-aggregation service
===========================================

Single source of truth for every "Total Expenditure" / utilization /
completed-works number in the application.

Why this exists — the data model has THREE independent datasets:

  projects            — recommended-works catalog (sanctioned amounts,
                        status, FY, completion% as recorded by the
                        recommending authority). Its per-project
                        `expenditure` column is a LEGACY field: only 4
                        seed/test rows carry a value, so aggregating it
                        systematically under-reports spend as ~₹0.
  expenditures        — the payment ledger: 106,263 dated transactions,
                        ₹391.87 Cr avg-scale rows, totaling ₹3,918.73 Cr.
                        This is the ONLY authoritative expenditure source.
  completed_works     — the completions ledger: 43,173 works with final
                        amounts and completion dates. This is the ONLY
                        authoritative completed-works source.

The two ledgers are payment/completion records with generic work
descriptions; they do NOT join reliably to individual project rows
(verified: only 62/6,315 distinct ledger keys match any project key).
So portfolio aggregates are computed FROM THE LEDGERS DIRECTLY, and
`fy`-scoped queries attribute ledger rows to financial years by
payment/completion date using the standard Indian FY (Apr–Mar).
The FY values stored on project rows come from the same recommendation
dataset and are used unchanged for project-scoped metrics (counts,
sanctioned).

Per-project / per-state / per-constituency views keep sanctioned and
project counts from `projects` (they are the recommended-work catalog)
and are not rewritten here; anything labeled "expenditure" or
"completed" anywhere in the app must come from this module.

All functions take a SQLAlchemy Session and are SQL-aggregated
(constant memory; nothing is materialized in Python).
"""

from typing import Any, Dict, Optional, Tuple

from sqlalchemy import func, case
from sqlalchemy import Integer, Text as SqlText
from sqlalchemy.orm import Session

import models


# Indian financial year from an ISO-like date string 'YYYY-MM-DD...':
# months 04..12 belong to FY <YYYY>-<YYYY+1>; months 01..03 belong to
# the previous year's FY. Emits the short form 'YYYY-YY' to match the
# project catalog's fy values (e.g. '2025-26').
def _fy_expr(col):
    """SQL expression computing the Indian FY (short form 'YYYY-YY')
    from a string date column ('YYYY-MM-DD...')."""
    year = func.substr(col, 1, 4)
    year_int = func.cast(year, Integer)
    return case(
        (
            func.substr(col, 6, 2).in_(("04", "05", "06", "07", "08", "09", "10", "11", "12")),
            year + "-" + func.substr(func.cast(year_int + 1, SqlText), 3, 2),
        ),
        else_=func.cast(year_int - 1, SqlText) + "-" + func.substr(col, 3, 2),
    )


def ledger_totals(db: Session) -> Dict[str, Any]:
    """Portfolio-wide expenditure + completed totals from the ledgers."""
    exp = db.query(
        func.coalesce(func.sum(models.Expenditure.expenditure_amount), 0.0).label("amount"),
        func.count(models.Expenditure.id).label("transactions"),
    ).one()
    comp = db.query(
        func.coalesce(func.sum(models.CompletedWork.final_amount), 0.0).label("amount"),
        func.count(models.CompletedWork.id).label("works"),
    ).one()
    return {
        "total_expenditure": float(exp.amount or 0),
        "expenditure_transactions": int(exp.transactions or 0),
        "completed_works": int(comp.works or 0),
        "completed_works_amount": float(comp.amount or 0),
    }


def ledger_totals_scoped(
    db: Session, state: Optional[str] = None, fy: Optional[str] = None
) -> Dict[str, Any]:
    """Ledger totals, optionally scoped by state (ledger's own state
    column) and/or financial year (payment/completion date, Indian FY)."""
    exp_q = db.query(
        func.coalesce(func.sum(models.Expenditure.expenditure_amount), 0.0).label("amount"),
        func.count(models.Expenditure.id).label("transactions"),
    )
    if state:
        exp_q = exp_q.filter(models.Expenditure.state == state)
    if fy:
        exp_q = exp_q.filter(_fy_expr(models.Expenditure.expenditure_date) == fy)
    exp = exp_q.one()

    comp_q = db.query(
        func.coalesce(func.sum(models.CompletedWork.final_amount), 0.0).label("amount"),
        func.count(models.CompletedWork.id).label("works"),
    )
    if state:
        comp_q = comp_q.filter(models.CompletedWork.state == state)
    if fy:
        comp_q = comp_q.filter(_fy_expr(models.CompletedWork.completed_date) == fy)
    comp = comp_q.one()

    return {
        "total_expenditure": float(exp.amount or 0),
        "expenditure_transactions": int(exp.transactions or 0),
        "completed_works": int(comp.works or 0),
        "completed_works_amount": float(comp.amount or 0),
    }


def portfolio_overview(db: Session, fy: Optional[str] = None) -> Dict[str, Any]:
    """The canonical dashboard-overview payload.

    projects       = project catalog rows (optionally FY-filtered by the
                     catalog's own fy column)
    sanctioned     = SUM(projects.sanctioned_amount) — real recorded values
    expenditure    = SUM from the payment ledger (FY-scoped by payment
                     date when a FY filter is given, unscoped otherwise
                     because ledger rows cannot be joined to projects)
    completed      = count from the completions ledger (same scoping rule)
    utilization    = expenditure / sanctioned * 100 (unrounded)
    """
    q = db.query(
        func.count(models.Project.id).label("total_projects"),
        func.coalesce(func.sum(models.Project.sanctioned_amount), 0.0).label("total_sanctioned"),
        func.coalesce(func.avg(models.Project.completion_percentage), 0.0).label("avg_completion"),
        func.count(func.distinct(models.Project.state)).label("total_states"),
        func.sum(case((func.lower(models.Project.status) == "completed", 1), else_=0)).label("completed_projects"),
        func.sum(case((func.lower(models.Project.status) == "ongoing", 1), else_=0)).label("ongoing_projects"),
        func.sum(case((func.lower(models.Project.status) == "recommended", 1), else_=0)).label("recommended_works"),
    )
    if fy:
        q = q.filter(models.Project.fy == fy)
    stats = q.one()

    total_mps = db.query(func.count(models.MPSummary.id)).scalar() or 0

    scoped = fy is not None
    led = ledger_totals_scoped(db, fy=fy) if scoped else ledger_totals(db)

    total_sanctioned = float(stats.total_sanctioned or 0)
    total_expenditure = float(led["total_expenditure"])
    utilization = (total_expenditure / total_sanctioned * 100) if total_sanctioned > 0 else 0.0

    return {
        "total_projects": int(stats.total_projects or 0),
        "completed_projects": int(led["completed_works"]),
        "ongoing_projects": int(stats.ongoing_projects or 0),
        "total_allocated_amount": total_sanctioned,
        "total_sanctioned_amount": total_sanctioned,
        "total_expenditure": total_expenditure,
        "expenditure_transactions": led["expenditure_transactions"],
        "completed_works_amount": led["completed_works_amount"],
        "utilization_percentage": utilization,
        "average_completion_percentage": round(float(stats.avg_completion or 0), 2),
        "total_mps": total_mps,
        "total_states": int(stats.total_states or 0),
        "recommended_works": int(stats.recommended_works or 0),
        "expenditure_scope": "fy_payment_date" if scoped else "full_ledger",
        "completed_scope": "fy_completion_date" if scoped else "full_ledger",
    }


def portfolio_stats(
    db: Session, fy: Optional[str] = None, state: Optional[str] = None
) -> Dict[str, Any]:
    """Catalog counts/sanctioned + ledger expenditure/completions, optionally
    scoped by catalog fy / catalog state (ledgers scoped by their own state
    and payment/completion-date FY)."""
    q = db.query(
        func.count(models.Project.id).label("total"),
        func.coalesce(func.sum(models.Project.sanctioned_amount), 0.0).label("sanctioned"),
        func.coalesce(func.avg(models.Project.completion_percentage), 0.0).label("avg_completion"),
        func.sum(case((func.lower(models.Project.status) == "ongoing", 1), else_=0)).label("ongoing"),
    )
    if fy:
        q = q.filter(models.Project.fy == fy)
    if state:
        q = q.filter(models.Project.state == state)
    s = q.one()
    led = ledger_totals_scoped(db, state=state, fy=fy)
    return {
        "total_projects": int(s.total or 0),
        "sanctioned": float(s.sanctioned or 0),
        "avg_completion": float(s.avg_completion or 0),
        "ongoing_projects": int(s.ongoing or 0),
        "expenditure": led["total_expenditure"],
        "expenditure_transactions": led["expenditure_transactions"],
        "completed_works": led["completed_works"],
        "completed_works_amount": led["completed_works_amount"],
    }


def project_expenditure_map(db: Session) -> Dict[int, float]:
    """project_id -> SUM(expenditure_amount) for ledger rows linked to the
    project's work key via the SAME conservative linkage as the timeline
    (normalized work key + MP + IDA-prefix, computed fully inside SQLite).

    Bounded by the catalog: only the ~328 work keys shared between the
    payment ledger and the recommended-works catalog can match, so this
    stays small (an ID dict), not a dataset copy.

    The catalog's per-project `expenditure` column is a legacy stamp that
    was zeroed by a documented startup repair after it was proven to be
    group-aggregate duplication of this same ledger — never aggregate it.
    """
    import rec_info as _recinfo
    conn = db.connection().connection  # raw sqlite3 connection
    conn.create_function("normkey", 1, _recinfo._normkey, deterministic=True)
    conn.create_function("idapfx", 1, _recinfo._idapfx_sql, deterministic=True)
    cur = conn.cursor()
    cur.execute("""
        SELECT p.id, COALESCE(SUM(e.expenditure_amount), 0)
        FROM projects p
        JOIN recommended_works rw
          ON normkey(rw.work_description) = normkey(p.project_name)
         AND normkey(rw.constituency)    = normkey(p.constituency)
         AND normkey(rw.state)           = normkey(p.state)
        JOIN expenditures e
          ON normkey(e.work_description) = normkey(rw.work_description)
         AND normkey(e.constituency)     = normkey(rw.constituency)
         AND normkey(e.state)            = normkey(rw.state)
         AND normkey(e.mp_name)          = normkey(rw.mp_name)
         AND idapfx(e.ida)               = idapfx(rw.ida)
        GROUP BY p.id
        HAVING SUM(e.expenditure_amount) > 0
    """)
    return {int(pid): float(amt) for pid, amt in cur.fetchall()}


def state_ledger_map(db: Session, fy: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """state -> ledger totals (expenditure by the ledger's own state column,
    completions by the completions ledger's state column)."""
    out: Dict[str, Dict[str, Any]] = {}

    eq = db.query(
        models.Expenditure.state.label("g"),
        func.coalesce(func.sum(models.Expenditure.expenditure_amount), 0.0).label("expenditure"),
        func.count(models.Expenditure.id).label("transactions"),
    )
    if fy:
        eq = eq.filter(_fy_expr(models.Expenditure.expenditure_date) == fy)
    for r in eq.group_by("g").all():
        entry = out.setdefault(
            r.g or "Unknown",
            {"expenditure": 0.0, "transactions": 0, "completed": 0, "completed_amount": 0.0},
        )
        entry["expenditure"] += float(r.expenditure or 0)
        entry["transactions"] += int(r.transactions or 0)

    cq = db.query(
        models.CompletedWork.state.label("g"),
        func.count(models.CompletedWork.id).label("works"),
        func.coalesce(func.sum(models.CompletedWork.final_amount), 0.0).label("amount"),
    )
    if fy:
        cq = cq.filter(_fy_expr(models.CompletedWork.completed_date) == fy)
    for r in cq.group_by("g").all():
        entry = out.setdefault(
            r.g or "Unknown",
            {"expenditure": 0.0, "transactions": 0, "completed": 0, "completed_amount": 0.0},
        )
        entry["completed"] += int(r.works or 0)
        entry["completed_amount"] += float(r.amount or 0)
    return out


def constituency_ledger_map(
    db: Session, fy: Optional[str] = None
) -> Dict[tuple, Dict[str, Any]]:
    """(state, constituency) -> ledger totals.

    Keyed by the (state, constituency) PAIR: shared labels like
    'Sitting Rajya Sabha' exist in many states, so a constituency-only key
    would double-attribute ledger spend to every state holding the label.
    Verified: 100% of ledger (state, constituency) pairs exist in the
    project catalog with identical strings.
    """
    out: Dict[tuple, Dict[str, Any]] = {}

    eq = db.query(
        models.Expenditure.state.label("s"),
        models.Expenditure.constituency.label("g"),
        func.coalesce(func.sum(models.Expenditure.expenditure_amount), 0.0).label("expenditure"),
        func.count(models.Expenditure.id).label("transactions"),
    )
    if fy:
        eq = eq.filter(_fy_expr(models.Expenditure.expenditure_date) == fy)
    for r in eq.group_by("s", "g").all():
        entry = out.setdefault(
            ((r.s or "").strip(), (r.g or "Unknown").strip()),
            {"expenditure": 0.0, "transactions": 0, "completed": 0, "completed_amount": 0.0},
        )
        entry["expenditure"] += float(r.expenditure or 0)
        entry["transactions"] += int(r.transactions or 0)

    cq = db.query(
        models.CompletedWork.state.label("s"),
        models.CompletedWork.constituency.label("g"),
        func.count(models.CompletedWork.id).label("works"),
        func.coalesce(func.sum(models.CompletedWork.final_amount), 0.0).label("amount"),
    )
    if fy:
        cq = cq.filter(_fy_expr(models.CompletedWork.completed_date) == fy)
    for r in cq.group_by("s", "g").all():
        entry = out.setdefault(
            ((r.s or "").strip(), (r.g or "Unknown").strip()),
            {"expenditure": 0.0, "transactions": 0, "completed": 0, "completed_amount": 0.0},
        )
        entry["completed"] += int(r.works or 0)
        entry["completed_amount"] += float(r.amount or 0)
    return out


def fy_trends(db: Session) -> list:
    """Per-FY trends. Project counts + sanctioned come from the project
    catalog grouped by its own fy column. Expenditure and completed
    counts come from the ledgers grouped by payment/completion-date FY.
    `utilization_percentage` uses the catalog sanctioned vs the ledger
    expenditure of the same FY. Catalog FY values with no ledger rows
    still appear (expenditure 0.0). Returned sorted by fy ascending,
    'Unknown' (NULL fy) last."""
    # Catalog side: counts + sanctioned by fy
    cat_rows = (
        db.query(
            models.Project.fy.label("fy"),
            func.count(models.Project.id).label("projects"),
            func.coalesce(func.sum(models.Project.sanctioned_amount), 0.0).label("sanctioned"),
        )
        .group_by(models.Project.fy)
        .all()
    )
    # Ledger side: expenditure by payment-date FY
    exp_rows = (
        db.query(
            _fy_expr(models.Expenditure.expenditure_date).label("fy"),
            func.coalesce(func.sum(models.Expenditure.expenditure_amount), 0.0).label("expenditure"),
            func.count(models.Expenditure.id).label("transactions"),
        )
        .group_by("fy")
        .all()
    )
    # Completions ledger by completion-date FY
    comp_rows = (
        db.query(
            _fy_expr(models.CompletedWork.completed_date).label("fy"),
            func.count(models.CompletedWork.id).label("works"),
            func.coalesce(func.sum(models.CompletedWork.final_amount), 0.0).label("amount"),
        )
        .group_by("fy")
        .all()
    )

    fy_order: Dict[str, Tuple[int, str]] = {}

    def _rank(v: Optional[str]) -> Tuple[int, str]:
        if not v:
            return (1, "")
        return (0, v)

    by_fy: Dict[str, Dict[str, Any]] = {}
    for r in cat_rows:
        key = r.fy or "Unknown"
        entry = by_fy.setdefault(
            key,
            {"fy": key, "projects": 0, "sanctioned": 0.0, "expenditure": 0.0,
             "transactions": 0, "completed": 0, "avg_risk": None},
        )
        entry["projects"] += int(r.projects or 0)
        entry["sanctioned"] += float(r.sanctioned or 0)
    for r in exp_rows:
        key = (r.fy or "Unknown") if isinstance(r.fy, str) else "Unknown"
        entry = by_fy.setdefault(
            key,
            {"fy": key, "projects": 0, "sanctioned": 0.0, "expenditure": 0.0,
             "transactions": 0, "completed": 0, "avg_risk": None},
        )
        entry["expenditure"] += float(r.expenditure or 0)
        entry["transactions"] += int(r.transactions or 0)
    for r in comp_rows:
        key = (r.fy or "Unknown") if isinstance(r.fy, str) else "Unknown"
        entry = by_fy.setdefault(
            key,
            {"fy": key, "projects": 0, "sanctioned": 0.0, "expenditure": 0.0,
             "transactions": 0, "completed": 0, "avg_risk": None},
        )
        entry["completed"] += int(r.works or 0)
        entry["completed_amount"] = entry.get("completed_amount", 0.0) + float(r.amount or 0)

    # Avg risk per catalog FY (existing risk_scores joined via project fy)
    risk_rows = (
        db.query(
            models.Project.fy.label("fy"),
            func.avg(models.RiskScore.risk_score).label("avg_risk"),
        )
        .join(models.RiskScore, models.RiskScore.project_id == models.Project.id)
        .group_by(models.Project.fy)
        .all()
    )
    for r in risk_rows:
        key = r.fy or "Unknown"
        if key in by_fy:
            by_fy[key]["avg_risk"] = round(float(r.avg_risk), 1) if r.avg_risk is not None else None

    out = []
    for key, e in by_fy.items():
        util = (e["expenditure"] / e["sanctioned"] * 100) if e["sanctioned"] > 0 else None
        out.append({
            "fy": key,
            "projects": e["projects"],
            "sanctioned": e["sanctioned"],
            "expenditure": e["expenditure"],
            "transactions": e["transactions"],
            "completed": e["completed"],
            "completed_amount": e.get("completed_amount", 0.0),
            "utilization_percentage": util,
            "avg_risk": e["avg_risk"],
        })
    out.sort(key=lambda x: (_rank(x["fy"] if x["fy"] != "Unknown" else None), x["fy"]))
    return out
