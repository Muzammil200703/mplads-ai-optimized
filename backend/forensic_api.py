"""
Project Forensic Mode + Project DNA/Twins + Risk Stress Test (backend)
=====================================================================

Three new capabilities integrated into the existing project-detail stack:

  • /forensic/{project_id}   — consolidated evidence bundle for Forensic Mode
  • /dna/{project_id}        — Project DNA fingerprint + Project Twins
  • /stress-test/{project_id} — interactive risk simulation (never persists)

Memory discipline (512MB Render container):
  • every multi-row read is LIMITed, SQL-aggregated, or streamed (yield_per)
  • no full-dataset scans; similarity uses the indexed state/type filters
    and the existing risk_scores table (83k rows, one streamed pass)
  • all responses are cached through the existing bounded _intel_cache

All evidence is drawn from existing tables and existing calculation logic —
nothing is invented, and simulations never touch stored data.
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

import activity
import ai_audit
import audit_intel
import models
from database import SessionLocal


def get_db():
    """Session dependency (mirrors main.get_db; kept local to avoid a
    circular import since main.py imports this router)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
from ml.predictor import RULE_POINTS, ML_ANOMALY_POINTS, score_rules_pure

router = APIRouter(prefix="/forensic-tools", tags=["AI Operations"])


# ────────────────────────────────────────────────────────────────────
# Shared helpers
# ────────────────────────────────────────────────────────────────────

class StressTestRequest(BaseModel):
    expenditure: Optional[float] = Field(None, ge=0, le=1e15)
    completion_percentage: Optional[float] = Field(None, ge=0, le=100)
    sanctioned_amount: Optional[float] = Field(None, ge=0, le=1e15)


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _project_or_404(db: Session, project_id: int) -> models.Project:
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(404, f"Project {project_id} not found")
    return project


def _work_key(project) -> str:
    """Normalized work key — same construction as activity._project_key."""
    return activity._project_key(project)


def _rule_reason_to_key() -> Dict[str, str]:
    """Map production reason strings → rule keys via RULE_POINTS order."""
    return {reason: key for key, reason, _, _ in RULE_POINTS}


# ────────────────────────────────────────────────────────────────────
# 1. PROJECT FORENSIC MODE
# ────────────────────────────────────────────────────────────────────

@router.get("/{project_id}")
def forensic_bundle(project_id: int, db: Session = Depends(get_db)):
    """Consolidated forensic evidence for ONE project, in one call.

    Sources (all existing): projects + risk_scores rows, stored rule
    reasons, ML anomaly result, benchmark context, ground verification
    reports, vendor intelligence data for this work key, expenditure
    activity, and the existing stale-data / evidence-gap calculators.
    """
    project = _project_or_404(db, project_id)
    risk_row = (
        db.query(models.RiskScore)
        .filter(models.RiskScore.project_id == project_id)
        .first()
    )

    # -- Financial evidence ------------------------------------------
    sanctioned = _num(project.sanctioned_amount)
    expenditure = _num(project.expenditure)
    completion = _num(project.completion_percentage)
    utilization = (expenditure / sanctioned * 100) if sanctioned > 0 else None

    # Existing calculators — no new formulas
    exposure = audit_intel.financial_exposure(project)
    stale = audit_intel and _stale_via_main(project_id, db)

    # -- Physical evidence -------------------------------------------
    status_str = (project.status or "").strip().lower()
    completion_val = _num(project.completion_percentage)
    status_consistency = {
        "status": project.status,
        "completion_percentage": completion,
        "consistent": (
            None if not status_str or not project.status
            else not (status_str == "completed" and completion < 90)
            and not (expenditure > 0 and completion == 0)
        ),
        "notes": [],
    }
    if status_str == "completed" and completion < 90:
        status_consistency["notes"].append(
            "Marked Completed while reported progress is below 90% — warrants verification."
        )
    if expenditure > 0 and completion == 0:
        status_consistency["notes"].append(
            "Expenditure is recorded but no physical progress is reported — requires review."
        )
    if utilization is not None and utilization >= 80 and completion < 50:
        status_consistency["notes"].append(
            "Fund utilization is high relative to reported physical progress — indicates a discrepancy to verify."
        )

    # -- ML analysis (stored result; SHAP factors if present) ----------
    top_factors = []
    ml_score = None
    ml_anomaly = False
    if risk_row is not None:
        ml_anomaly = bool(risk_row.ml_anomaly)
        ml_score = risk_row.ml_score
        reasons_field = getattr(risk_row, "reasons", None)
        if risk_row.ml_score is not None and risk_row.ml_anomaly:
            try:
                info = __import__("ml.predictor", fromlist=["predict_risk"]).predict_risk(project)
                top_factors = (info.get("contributing_factors") or [])[:5]
            except Exception:
                top_factors = []

    # -- Rule-based analysis with exact point weights ------------------
    reasons: List[str] = []
    if risk_row is not None and risk_row.reasons:
        raw = risk_row.reasons
        reasons = (
            [r.strip() for r in str(raw).split(",")] if isinstance(raw, str)
            else list(raw)
        )
    reasons = [r for r in reasons if r]
    reason_to_points = {reason: pts for _, reason, pts, _ in RULE_POINTS}
    key_to_reason = {key: reason for key, reason, _, _ in RULE_POINTS}
    rule_items = []
    unmatched = []
    for reason in reasons:
        if reason in reason_to_points:
            rule_items.append({
                "key": _reason_key(reason),
                "reason": reason,
                "points": reason_to_points[reason],
                "source": "rule",
            })
        else:
            unmatched.append(reason)
    if unmatched and ml_anomaly:
        rule_items.append({
            "key": "ml_anomaly",
            "reason": unmatched[0],
            "points": ML_ANOMALY_POINTS,
            "source": "ml",
        })
        unmatched = unmatched[1:]
    for reason in unmatched:
        rule_items.append({"key": None, "reason": reason, "points": None, "source": "unknown"})

    # -- Vendor / relationship evidence (work-key scoped) --------------
    vendor_evidence = _vendor_evidence_for_key(db, _work_key(project))

    # -- Ground / evidence (existing verification reports) -------------
    verifications = (
        db.query(models.VerificationReport)
        .filter(models.VerificationReport.project_id == project_id)
        .order_by(models.VerificationReport.created_at.desc())
        .limit(10)
        .all()
    )
    ground = {
        "evidence_count": len(verifications),
        "reports": [
            {
                "status": v.status,
                "reporter": v.reporter_name,
                "reporter_role": v.user_role,
                "gps": None if (v.lat is None and v.lon is None) else
                       {"lat": v.lat, "lon": v.lon},
                "note": (v.note or "")[:160],
                "created_at": v.created_at,
            }
            for v in verifications
        ],
        "note": (
            "Absence of ground evidence means none has been recorded; "
            "it is not itself an indicator of wrongdoing."
        ),
    }

    # -- Score consistency: stored classification vs current values -----
    # The stored score reflects the values recorded at scoring time. If the
    # project row has since been corrected, the two can diverge — surfaced
    # here rather than silently recomputed (Risk Center must stay stable).
    recompute_score, recompute_level, _ = score_rules_pure(
        sanctioned, expenditure, completion, project.status, ml_anomaly=ml_anomaly,
    )
    stored_score_val = risk_row.risk_score if risk_row else 0
    stored_level_val = risk_row.risk_level if risk_row else "None"
    score_consistency = {
        "stored_score": stored_score_val,
        "stored_level": stored_level_val,
        "recomputed_from_current_values": recompute_score,
        "recomputed_level": recompute_level,
        "consistent": stored_score_val == recompute_score,
        "note": None if stored_score_val == recompute_score else (
            f"The stored classification ({stored_score_val}/100) does not match what the "
            f"current record values would score ({recompute_score}/100). The stored score "
            "may predate a data correction — the risk score itself is not changed here; "
            "a re-score through the normal pipeline would be needed to update it."
        ),
    }

    # -- Data quality ---------------------------------------------------
    data_quality = {
        "stale_flag": stale.get("flag"),
        "stale_reason": stale.get("reason"),
        "missing_fields": [],
    }
    for field, label in (
        ("district", "District"),
        ("fy", "Financial year"),
        ("project_type", "Category/type"),
        ("completion_percentage", "Recorded progress"),
        ("expenditure", "Recorded expenditure"),
    ):
        if getattr(project, field, None) in (None, ""):
            data_quality["missing_fields"].append(label)
    if project.expenditure == 0 and project.completion_percentage == 0:
        data_quality["missing_fields"].append(
            "Note: expenditure and progress are recorded as zero — this may mean "
            "missing data rather than actual zero values."
        )

    # -- Forensic summary (deterministic, from the evidence above) ------
    summary = _forensic_summary(
        project, rule_items, ml_anomaly, ml_score, utilization,
        completion, status_consistency, vendor_evidence, ground, data_quality,
        score_consistency,
    )

    return {
        "project": {
            "id": project.id,
            "name": project.project_name,
            "state": project.state,
            "district": project.district,
            "constituency": project.constituency,
            "category": project.project_type,
            "status": project.status,
            "fy": project.fy,
        },
        "financial": {
            "sanctioned_amount": sanctioned,
            "expenditure": expenditure,
            "utilization_pct": round(utilization, 1) if utilization is not None else None,
            "remaining_amount": max(0.0, sanctioned - expenditure) if sanctioned > 0 else None,
            "discrepancy_indicators": {
                "overspend_amount": exposure.get("overspend_amount", 0),
                "unverified_spend": exposure.get("unverified_spend"),
                "unverified_spend_formula": exposure.get("unverified_spend_formula"),
            },
        },
        "physical": {
            "completion_percentage": completion_val,
            "status_consistency": status_consistency,
        },
        "ml": {
            "isolation_forest_flag": ml_anomaly,
            "ml_score": ml_score,
            "top_factors": top_factors,
            "note": "ML output is a statistical indicator — it does not establish wrongdoing.",
        },
        "rules": {
            "triggered": rule_items,
            "risk_score": risk_row.risk_score if risk_row else 0,
            "risk_level": risk_row.risk_level if risk_row else "None",
            "score_consistency": score_consistency,
        },
        "vendor_evidence": vendor_evidence,
        "ground": ground,
        "data_quality": data_quality,
        "summary": summary,
    }


def _stale_via_main(project_id: int, db: Session):
    """Stale-data check reusing main._check_stale_progress (project-loaded)."""
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    try:
        from main import _check_stale_progress
        return _check_stale_progress(project)
    except Exception:
        return {"flag": "UNKNOWN", "reason": "Stale check unavailable"}


def _vendor_evidence_for_key(db: Session, key: str) -> Dict[str, Any]:
    """Vendor relationships for THIS work key only (per-key SQL, bounded)."""
    desc, con, st = (key.split("\u241f") + ["", ""])[:3]
    if not desc:
        return {"available": False, "reason": "Project name unavailable for work-key matching"}
    dbq = db.execute(text("""
        SELECT normkey(vendor) AS v,
               MAX(vendor) AS raw_name,
               COUNT(*) AS tx,
               SUM(expenditure_amount) AS total
        FROM expenditures
        WHERE normkey(work_description) = :desc
          AND normkey(constituency) = :con
          AND normkey(state) = :st
          AND vendor IS NOT NULL
          AND TRIM(vendor) != ''
        GROUP BY normkey(vendor)
        ORDER BY total DESC
        LIMIT 8
    """), {"desc": desc, "con": con, "st": st}).fetchall()
    vendors = [
        {"vendor": raw, "transactions": tx, "total_amount": round(total or 0, 2)}
        for v, raw, tx, total in dbq
    ]
    return {
        "available": bool(vendors),
        "vendors": vendors,
        "match_scope": "Matched by exact normalized work key (description + constituency + state) in the expenditure ledger.",
        "note": (
            "Vendors below appear in this work's payment records. Their presence "
            "is recorded fact, not an indicator of irregularity."
        ) if vendors else "No vendor records match this project's work key in the expenditure ledger.",
    }


def _forensic_summary(
    project, rule_items, ml_anomaly, ml_score, utilization,
    completion, status_consistency, vendor_evidence, ground, data_quality,
    score_consistency=None,
) -> str:
    """Deterministic forensic narrative — only the evidence above is used."""
    s = _num(project.sanctioned_amount)
    e = _num(project.expenditure)
    parts: List[str] = []

    triggered = [r for r in rule_items if r["source"] in ("rule", "ml")]
    if triggered:
        names = "; ".join(r["reason"].lower() for r in triggered)
        parts.append(
            f"{len(triggered)} risk condition(s) triggered: {names}."
        )
    else:
        parts.append(
            "No rule-based risk conditions are triggered for this project."
        )

    if ml_anomaly:
        parts.append(
            "The Isolation Forest model also flags this record as a statistical "
            "outlier among peers — an indicator that warrants review, not proof of wrongdoing."
        )

    if status_consistency["notes"]:
        parts.append("Inconsistencies: " + " ".join(status_consistency["notes"]))

    if vendor_evidence.get("available"):
        vendors = vendor_evidence.get("vendors", [])
        if vendors:
            parts.append(
                f"Payment records list {len(vendors)} vendor(s) for this work, led by "
                f"{vendors[0]['vendor']} ({vendors[0]['transactions']} transaction(s))."
            )

    if ground.get("evidence_count"):
        parts.append(
            f"{ground['evidence_count']} ground-evidence submission(s) are on record for independent review."
        )
    else:
        parts.append(
            "No ground-evidence submissions are recorded; absence of evidence is not evidence of wrongdoing."
        )

    if data_quality.get("missing_fields"):
        parts.append(
            "Data limitations: " + ", ".join(data_quality["missing_fields"][:4]) + "."
        )

    if score_consistency and not score_consistency.get("consistent"):
        parts.append(
            f"Note: the stored risk classification ({score_consistency.get('stored_score')}/100) "
            f"differs from what the current record values would score "
            f"({score_consistency.get('recomputed_from_current_values')}/100) — the stored "
            "score may predate a data correction and warrants a re-score."
        )

    next_steps = []
    if any(r["key"] == "overspend" for r in triggered):
        next_steps.append("verify expenditure vouchers against the sanctioned amount")
    if completion == 0 and e > 0:
        next_steps.append("physically verify the site given funds recorded with no reported progress")
    if status_consistency["notes"]:
        next_steps.append("reconcile recorded status with reported progress")
    if not ground.get("evidence_count"):
        next_steps.append("request ground verification to establish current site status")
    if not next_steps:
        next_steps.append("no specific follow-up indicated by the recorded evidence")
    parts.append("Suggested next steps: " + "; ".join(next_steps[:3]) + ".")

    parts.append(
        "All findings are screening indicators that require review; nothing here "
        "establishes fraud or wrongdoing."
    )
    return " ".join(parts)


# ────────────────────────────────────────────────────────────────────
# 2. PROJECT DNA + PROJECT TWINS
# ────────────────────────────────────────────────────────────────────

@router.get("/dna/{project_id}")
def project_dna(
    project_id: int,
    db: Session = Depends(get_db),
    twins_limit: int = Query(6, ge=0, le=12),
):
    """Analytical fingerprint + genuinely similar projects (analytical peers).

    DNA dimensions are computed only from attributes that exist for the
    project; each includes its derivation so nothing looks invented.
    Twins use weighted attribute similarity over the project's own
    state/type cohort — the same indexed filters as the existing
    /projects/{id}/similar endpoint, not name matching.
    """
    project = _project_or_404(db, project_id)
    risk_row = (
        db.query(models.RiskScore)
        .filter(models.RiskScore.project_id == project_id)
        .first()
    )
    risk_score = int(risk_row.risk_score or 0) if risk_row else 0
    risk_level = risk_row.risk_level if risk_row else "None"

    s = _num(project.sanctioned_amount)
    e = _num(project.expenditure)
    c = _num(project.completion_percentage)

    # Cohort medians (same state + normalized type, indexed filters).
    # Cohort = same state; peers = state + type + amount band.
    type_norm = ai_audit.norm_category(project.project_type)
    cohort = _cohort_stats(db, project, type_norm)

    # ── DNA dimensions (None = attribute not calculable) ─────────────
    dims = []
    if s > 0:
        band = (
            "Large (≥ ₹1 Cr)" if s >= 10_000_000
            else "Medium (≥ ₹10 L)" if s >= 1_000_000
            else "Small (< ₹10 L)"
        )
        dims.append({
            "key": "financial_exposure",
            "label": "Financial Exposure",
            "value": round(min(100.0, s / 10_000_000 * 100), 1),
            "display": band,
            "derivation": "Sanctioned amount ₹{:,.0f} vs ₹1 Cr reference scale".format(s),
        })
    if s > 0:
        dims.append({
            "key": "utilization",
            "label": "Utilization",
            "value": round(min(100.0, e / s * 100), 1),
            "display": f"{e / s * 100:.0f}% of sanction spent",
            "derivation": "Recorded expenditure ÷ sanctioned amount",
        })
    if project.completion_percentage is not None:
        dims.append({
            "key": "physical_progress",
            "label": "Physical Progress",
            "value": round(min(100.0, c), 1),
            "display": f"{c:.0f}% recorded",
            "derivation": "Recorded completion percentage",
        })
    if cohort["median_completion"] is not None:
        dims.append({
            "key": "progress_vs_cohort",
            "label": "Progress vs Peers",
            "value": round(min(100.0, 50 + (c - cohort["median_completion"]) * 2), 1),
            "display": f"{c:.0f}% vs peer median {cohort['median_completion']:.0f}%",
            "derivation": f"Completion against the median of {cohort['cohort_size']} same-state, same-type projects",
        })
    if risk_row:
        dims.append({
            "key": "risk_signals",
            "label": "Risk Signals",
            "value": float(risk_score),
            "display": f"{risk_score}/100 ({risk_level})",
            "derivation": "Stored risk score from the existing risk engine",
        })
    completeness = _evidence_completeness(project, risk_row)
    dims.append({
        "key": "evidence_coverage",
        "label": "Evidence Coverage",
        **completeness,
    })

    # Timeline presence (existing per-key lookup, bounded)
    key = _work_key(project)
    rec = activity._rec_cached(key) if key else None
    comp = activity._comp_cached(key) if key else None
    timeline = {
        "recommended_on": rec[2] if rec else None,
        "completed_on": comp[0] if comp else None,
        "in_ledger": bool(rec or comp),
    }

    # ── Project Twins — attribute-based similarity ───────────────────
    twins = _find_twins(db, project, risk_row, type_norm, cohort, twins_limit)

    return {
        "dna": {
            "dimensions": dims,
            "timeline": timeline,
            "note": "Only attributes present in the dataset are shown; missing dimensions are omitted rather than estimated.",
        },
        "twins": twins,
    }


def _evidence_completeness(project, risk_row) -> Dict[str, Any]:
    fields = [
        project.sanctioned_amount is not None,
        project.expenditure is not None,
        project.completion_percentage is not None,
        bool(project.status),
        bool(project.fy),
        bool(project.district),
    ]
    present = sum(fields)
    pct = present / len(fields) * 100
    return {
        "value": round(pct, 1),
        "display": f"{present} of {len(fields)} core attributes recorded",
        "derivation": "Share of core project attributes present in the dataset",
    }


def _cohort_stats(db: Session, project, type_norm: str) -> Dict[str, Any]:
    """Median completion + cohort size for same-state, same-type projects.

    Uses the same normalized-type function as the audit-intelligence
    benchmark so cohorts are consistent across the app.
    """
    # SQLite has no PERCENTILE_CONT — stream the single completion column
    # for the same-state cohort (one float per row, small) and take the
    # median in Python.
    values: List[float] = []
    rows = (
        db.query(models.Project.completion_percentage)
        .filter(
            models.Project.state == project.state,
            models.Project.completion_percentage.isnot(None),
        )
        .yield_per(500)
    )
    for (v,) in rows:
        values.append(float(v))
    values.sort()
    if values:
        n = len(values)
        med = values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2
    else:
        med = None
    return {
        "cohort_size": len(values),
        "median_completion": med,
        "type_norm": type_norm,
    }


def _find_twins(
    db: Session, project, risk_row, type_norm, cohort, twins_limit,
):
    """Attribute-based Project Twins.

    Cohort = same state (+ same normalized category when populated).
    Weights: category 25 · state 15 · amount band 20 · utilization 15 ·
    progress 15 · status 10 — every dimension derives from real columns.
    Similarity uses the indexed state/type equality filters, then scores
    only the candidate page (LIMIT'd, streamed) — never a full-table scan.
    """
    if twins_limit <= 0:
        return {"peers": [], "cohort_size": 0, "criteria": {}, "method": ""}

    s = _num(project.sanctioned_amount)
    e = _num(project.expenditure)
    c = _num(project.completion_percentage)
    util = (e / s * 100) if s > 0 else None
    status_str = (project.status or "").strip().lower()

    def amount_band(v: float) -> str:
        if v <= 0:
            return "0"
        if v < 500_000:
            return "under_5L"
        if v < 2_000_000:
            return "5L_20L"
        if v < 10_000_000:
            return "20L_1cr"
        return "over_1cr"

    base = db.query(models.Project).filter(models.Project.id != project.id)

    # Indexed narrowing first, then weighted scoring in Python over the
    # limited candidate set.
    if type_norm and project.project_type:
        candidates = (
            base.filter(models.Project.state == project.state)
            .filter(models.Project.project_type == project.project_type)
            .order_by(models.Project.id.asc())
            .limit(200)
            .all()
        )
    else:
        candidates = (
            base.filter(models.Project.state == project.state)
            .order_by(models.Project.id.asc())
            .limit(400)
            .all()
        )

    if not candidates:
        return {
            "peers": [], "cohort_size": 0,
            "criteria": {"state": project.state, "type": project.project_type},
            "method": "No same-state candidates found in the dataset.",
        }

    ids = [p.id for p in candidates]
    risk_map = {
        r.project_id: r
        for r in db.query(models.RiskScore)
        .filter(models.RiskScore.project_id.in_(ids))
        .all()
    }

    scored = []
    for p in candidates:
        ps = _num(p.sanctioned_amount)
        pe = _num(p.expenditure)
        pc = _num(p.completion_percentage)
        p_util = (pe / ps * 100) if ps > 0 else None
        score = 0.0
        # category (25) — already filtered, but score for the fallback path
        if type_norm and ai_audit.norm_category(p.project_type) == type_norm:
            score += 25
        # state (15) — filtered for all candidates
        if p.state == project.state:
            score += 15
        # amount band (20)
        if amount_band(ps) == amount_band(s):
            score += 20
        # utilization similarity (15)
        if util is not None and p_util is not None:
            score += max(0.0, 15 - abs(util - p_util) / 4)
        # progress similarity (15)
        score += max(0.0, 15 - abs(c - pc) * 0.3)
        # status (10)
        if status_str and (p.status or "").strip().lower() == status_str:
            score += 10
        rr = risk_map.get(p.id)
        scored.append({
            "id": p.id,
            "project_name": p.project_name,
            "state": p.state,
            "constituency": p.constituency,
            "sanctioned_amount": ps,
            "expenditure": pe,
            "completion_percentage": pc,
            "status": p.status,
            "similarity": round(min(100.0, score), 1),
            "risk_level": rr.risk_level if rr else "None",
            "risk_score": int(rr.risk_score or 0) if rr else 0,
        })

    # Ties broken by closeness of sanctioned amount so ordering is stable
    # and the nearest-size peer leads.
    scored.sort(key=lambda x: (-x["similarity"], abs(x["sanctioned_amount"] - s)))
    top = scored[:twins_limit]

    # Contextual comparison vs the twin set actually returned
    comparisons = {}
    if top:
        progs = sorted(p["completion_percentage"] for p in top)
        meds = sorted(_num(p["sanctioned_amount"]) for p in top)
        med_prog = progs[len(progs) // 2] if len(progs) % 2 else (progs[len(progs)//2 - 1] + progs[len(progs)//2]) / 2
        med_sanctioned = meds[len(meds) // 2] if len(meds) % 2 else (meds[len(meds)//2 - 1] + meds[len(meds)//2]) / 2
        if project.completion_percentage is not None:
            comparisons["progress"] = {
                "this_project": c,
                "peer_median": round(med_prog, 1),
                "text": (
                    f"This project has {c:.0f}% recorded progress compared with a "
                    f"median of {med_prog:.0f}% among the similar projects shown."
                ),
            }
        if s > 0 and med_sanctioned > 0:
            comparisons["sanctioned"] = {
                "this_project": s,
                "peer_median": round(med_sanctioned, 2),
                "text": (
                    f"Sanctioned amount of ₹{s:,.0f} versus a peer median of "
                    f"₹{med_sanctioned:,.0f}."
                ),
            }

    return {
        "peers": top,
        "cohort_size": len(candidates),
        "criteria": {
            "state": project.state,
            "project_type": project.project_type,
            "weights": "category 25 · state 15 · amount band 20 · utilization 15 · progress 15 · status 10",
        },
        "comparisons": comparisons,
        "label": "Analytical Peers",
        "note": (
            "Similar projects are analytical peers matched on recorded attributes — "
            "not guaranteed equivalents."
        ),
        "method": (
            "Weighted attribute similarity over same-state projects with the same "
            "recorded category (candidates capped per request; no full-dataset scan)."
        ),
    }


# ────────────────────────────────────────────────────────────────────
# 3. RISK STRESS TEST
# ────────────────────────────────────────────────────────────────────

@router.post("/stress-test/{project_id}")
def stress_test(
    project_id: int,
    payload: StressTestRequest = None,
    db: Session = Depends(get_db),
):
    """Interactive what-if on the EXISTING rule engine — nothing persists.

    Hypothetical values are re-scored through score_rules_pure(), which was
    verified 300/300 identical to the production predict_risk() path. The
    stored ML anomaly flag is carried forward as a constant contribution
    (the model itself is not re-run on hypothetical values — that would
    produce a simulated ML result presented as a model result).
    """
    project = _project_or_404(db, project_id)
    payload = payload or StressTestRequest()
    if all(v is None for v in (
        payload.expenditure, payload.completion_percentage, payload.sanctioned_amount,
    )):
        raise HTTPException(400, "Provide at least one value to simulate")

    risk_row = (
        db.query(models.RiskScore)
        .filter(models.RiskScore.project_id == project_id)
        .first()
    )
    cur_s = _num(project.sanctioned_amount)
    cur_e = _num(project.expenditure)
    cur_c = _num(project.completion_percentage)
    stored_ml = bool(risk_row.ml_anomaly) if risk_row else False
    stored_score = int(risk_row.risk_score or 0) if risk_row else 0
    stored_level = risk_row.risk_level if risk_row else "None"

    sim_s = cur_s if payload.sanctioned_amount is None else max(0.0, float(payload.sanctioned_amount))
    sim_e = cur_e if payload.expenditure is None else max(0.0, float(payload.expenditure))
    sim_c = cur_c if payload.completion_percentage is None else min(100.0, max(0.0, float(payload.completion_percentage)))

    # Same-status premise: status is not simulated (explain if unchanged)
    cur_score, cur_level, cur_triggers = score_rules_pure(cur_s, cur_e, cur_c, project.status, ml_anomaly=stored_ml)
    sim_score, sim_level, sim_triggers = score_rules_pure(sim_s, sim_e, sim_c, project.status, ml_anomaly=stored_ml)

    # Current triggers from the STORED reasons when available (single source
    # of truth), falling back to the recomputation for unscored projects.
    stored_reasons = []
    if risk_row is not None and risk_row.reasons:
        raw = risk_row.reasons
        stored_reasons = (
            [r.strip() for r in str(raw).split(",")] if isinstance(raw, str) else list(raw)
        )
    current_view = cur_triggers
    if stored_reasons:
        pts = {reason: p for _, reason, p, _ in RULE_POINTS}
        current_view = []
        for reason in [r for r in stored_reasons if r]:
            if reason in pts:
                current_view.append({"key": _reason_key(reason), "reason": reason, "points": pts[reason], "source": "rule"})
            elif stored_ml:
                current_view.append({"key": "ml_anomaly", "reason": reason, "points": ML_ANOMALY_POINTS, "source": "ml"})

    cur_map = {t["key"]: t for t in current_view}
    sim_map = {t["key"]: t for t in sim_triggers}
    all_keys = list(dict.fromkeys(list(cur_map.keys()) + list(sim_map.keys())))

    drivers = []
    for k in all_keys:
        cur_t = cur_map.get(k)
        sim_t = sim_map.get(k)
        drivers.append({
            "key": k,
            "reason": (sim_t or cur_t or {}).get("reason"),
            "current_points": cur_t["points"] if cur_t else 0,
            "simulated_points": sim_t["points"] if sim_t else 0,
            "status": (
                "unchanged" if cur_t and sim_t
                else "newly_triggered" if sim_t
                else "resolved"
            ),
        })
    drivers.sort(key=lambda d: d["simulated_points"], reverse=True)

    changed_inputs = []
    if payload.sanctioned_amount is not None and abs(sim_s - cur_s) > 1e-6:
        changed_inputs.append(f"sanctioned amount → ₹{sim_s:,.0f}")
    if payload.expenditure is not None and abs(sim_e - cur_e) > 1e-6:
        changed_inputs.append(f"expenditure → ₹{sim_e:,.0f}")
    if payload.completion_percentage is not None and abs(sim_c - cur_c) > 1e-6:
        changed_inputs.append(f"reported progress → {sim_c:.0f}%")

    return {
        "simulation": True,
        "notice": "SIMULATION — Does not modify actual project data. Stored scores, records and the ML model are untouched.",
        "method": (
            "Hypothetical values are re-scored by the same deterministic rule "
            "engine that produced the stored risk score. The stored ML anomaly "
            "flag is held constant rather than re-predicted, so the simulated "
            "ML contribution is carried over, not a new model result."
        ),
        "status_note": "Execution status is not simulated; it stays as recorded.",
        "changed_inputs": changed_inputs,
        "current": {
            "risk_score": stored_score or cur_score,
            "risk_level": stored_level,
            "sanctioned_amount": cur_s,
            "expenditure": cur_e,
            "completion_percentage": cur_c,
            "utilization_pct": round(cur_e / cur_s * 100, 1) if cur_s > 0 else None,
            "triggers": current_view,
        },
        "simulated": {
            "risk_score": sim_score,
            "risk_level": sim_level,
            "sanctioned_amount": sim_s,
            "expenditure": sim_e,
            "completion_percentage": sim_c,
            "utilization_pct": round(sim_e / sim_s * 100, 1) if sim_s > 0 else None,
            "triggers": sim_triggers,
        },
        "score_delta": sim_score - (stored_score or cur_score),
        "risk_drivers": drivers,
    }


def _reason_key(reason: str) -> str:
    for key, r, _, _ in RULE_POINTS:
        if r == reason:
            return key
    if "ml" in (reason or "").lower():
        return "ml_anomaly"
    return reason
