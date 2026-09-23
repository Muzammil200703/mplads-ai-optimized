"""MP Intelligence — MP-level views over the existing MPLADS data.

Design rules:
- MPSummary rows are the MP identity (one row per MP+House+Constituency in
  the source snapshot; 0 name collisions within or across houses). The row id
  is the stable detail-view key; payloads always carry name+house+state+
  constituency so the identity stays visible.
- Summary/list numbers reuse the authoritative MPSummary fields
  (allocated_amount, total_expenditure, utilization_percentage,
  completed_works, recommended_works, completion_rate_percentage,
  unspent_amount) — no duplicate calculations.
- Work-level detail joins RecommendedWork/CompletedWork/Expenditure by
  normkey(work_description)+normkey(constituency)+normkey(state) within the
  MP+House — the same keying the platform already uses for work↔payment
  linkage. Expenditure rows without a matching recommendation are reported
  as a data-quality note, never silently dropped.
"""
from collections import Counter
from typing import Any, Dict, List, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database import normkey
from models import CompletedWork, MPSummary, RecommendedWork

VALID_HOUSES = ("Lok Sabha", "Rajya Sabha")

_SORT_COLUMNS = {
    "mp_name": MPSummary.mp_name,
    "allocated_amount": MPSummary.allocated_amount,
    "total_expenditure": MPSummary.total_expenditure,
    "utilization_percentage": MPSummary.utilization_percentage,
    "completed_works": MPSummary.completed_works,
    "recommended_works": MPSummary.recommended_works,
    "completion_rate_percentage": MPSummary.completion_rate_percentage,
}


def _norm_house(house: Optional[str]) -> Optional[str]:
    """Accept only exact house names; anything else means All."""
    return house if house in VALID_HOUSES else None


def _apply_filters(query, house: Optional[str], state: Optional[str], q: Optional[str]):
    if house:
        query = query.filter(MPSummary.house == house)
    if state:
        query = query.filter(MPSummary.state == state)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            MPSummary.mp_name.ilike(like)
            | MPSummary.constituency.ilike(like)
            | MPSummary.state.ilike(like)
        )
    return query


def list_mp_intelligence(
    db: Session,
    house: Optional[str] = None,
    state: Optional[str] = None,
    q: Optional[str] = None,
    sort_by: str = "mp_name",
    sort_dir: str = "asc",
    limit: int = 300,
    offset: int = 0,
) -> Dict[str, Any]:
    house_n = _norm_house(house)
    rows = _apply_filters(db.query(MPSummary), house_n, state, q)
    total = rows.count()

    # Portfolio summary over the SAME filtered set (backend aggregation —
    # the frontend never sums rows in the browser).
    agg_q = _apply_filters(db.query(
        func.count(MPSummary.id),
        func.sum(MPSummary.allocated_amount),
        func.sum(MPSummary.total_expenditure),
        func.sum(MPSummary.unspent_amount),
        func.avg(MPSummary.utilization_percentage),
        func.avg(MPSummary.completion_rate_percentage),
        func.sum(MPSummary.completed_works),
        func.sum(MPSummary.recommended_works),
    ), house_n, state, q)
    n_mps, s_alloc, s_exp, s_unspent, a_util, a_completion, s_completed, s_recommended = agg_q.one()

    s_alloc = float(s_alloc or 0)
    s_exp = float(s_exp or 0)
    s_completed = int(s_completed or 0)
    s_recommended = int(s_recommended or 0)

    order_col = _SORT_COLUMNS.get(sort_by, MPSummary.mp_name)
    order = order_col.desc() if sort_dir == "desc" else order_col.asc()
    items = (
        rows.order_by(order, MPSummary.id)
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 1000))
        .all()
    )

    def mp_dict(m: MPSummary) -> Dict[str, Any]:
        recommended = int(m.recommended_works or 0)
        completed = int(m.completed_works or 0)
        return {
            "id": m.id,
            "mp_name": m.mp_name,
            "house": m.house,
            "state": m.state,
            "constituency": m.constituency,
            "allocated_amount": float(m.allocated_amount or 0),
            "total_expenditure": float(m.total_expenditure or 0),
            "unspent_amount": float(m.unspent_amount or 0),
            "utilization_percentage": float(m.utilization_percentage or 0),
            "completed_works": completed,
            "recommended_works": recommended,
            "pending_works": max(recommended - completed, 0),
            "completion_rate_percentage": float(m.completion_rate_percentage or 0),
            "transaction_count": int(m.transaction_count or 0),
            "successful_payments": int(m.successful_payments or 0),
            "pending_payments": int(m.pending_payments or 0),
        }

    return {
        "total": total,
        "summary": {
            "total_mps": int(n_mps or 0),
            "total_allocated": s_alloc,
            "total_expenditure": s_exp,
            # Aggregate unspent prefers the stored per-MP balances; when the
            # column is absent/empty it falls back to allocated − expenditure.
            "total_unspent": float(s_unspent) if s_unspent is not None else max(s_alloc - s_exp, 0.0),
            "average_utilization_percentage": round(float(a_util or 0), 2),
            "average_completion_rate_percentage": round(float(a_completion or 0), 2),
            "total_completed_works": s_completed,
            "total_recommended_works": s_recommended,
            "total_pending_works": max(s_recommended - s_completed, 0),
        },
        "mps": [mp_dict(m) for m in items],
    }


def mp_detail(db: Session, mp_id: int, include_works_limit: int = 400) -> Optional[Dict[str, Any]]:
    m = db.query(MPSummary).filter(MPSummary.id == mp_id).first()
    if m is None:
        return None

    house = m.house
    mpn = normkey(m.mp_name)
    cn = normkey(m.constituency)
    st = normkey(m.state)

    recommended = int(m.recommended_works or 0)
    completed_n = int(m.completed_works or 0)

    # ── Work-level ledger rows for THIS MP+House+Constituency+State ──
    rec_rows = (
        db.query(
            RecommendedWork.id,
            RecommendedWork.work_id,
            RecommendedWork.work_description,
            RecommendedWork.category,
            RecommendedWork.recommended_amount,
            RecommendedWork.recommendation_date,
            RecommendedWork.source,
        )
        .filter(
            RecommendedWork.house == house,
            func.normkey(RecommendedWork.mp_name) == mpn,
            func.normkey(RecommendedWork.constituency) == cn,
            func.normkey(RecommendedWork.state) == st,
        )
        .all()
    )

    comp_rows = (
        db.query(
            CompletedWork.work_id,
            CompletedWork.work_description,
            CompletedWork.category,
            CompletedWork.final_amount,
            CompletedWork.completed_date,
        )
        .filter(
            CompletedWork.house == house,
            func.normkey(CompletedWork.mp_name) == mpn,
            func.normkey(CompletedWork.constituency) == cn,
            func.normkey(CompletedWork.state) == st,
        )
        .all()
    )

    comp_by_wid = {}
    comp_by_wk = {}
    for wid, wdesc, wcat, famt, cdate in comp_rows:
        if wid is not None:
            comp_by_wid.setdefault(int(wid), (famt, cdate))
        comp_by_wk.setdefault(normkey(wdesc), (famt, cdate))

    # Expenditure aggregated per normalized work key (the platform's
    # established work↔payment linkage, scoped to this MP+House).
    exp_rows = db.execute(
        text(
            "SELECT normkey(work_description) AS wk, "
            "SUM(expenditure_amount) AS amt, COUNT(*) AS n "
            "FROM expenditures "
            "WHERE house = :house "
            "AND normkey(mp_name) = :mpn "
            "AND normkey(constituency) = :cn "
            "AND normkey(state) = :st "
            "GROUP BY wk"
        ),
        {"house": house, "mpn": mpn, "cn": cn, "st": st},
    ).all()
    exp_by_wk = {wk: (float(amt or 0), int(n)) for wk, amt, n in exp_rows}

    esakshi = [r for r in rec_rows if r.source == "esakshi"]
    legacy = [r for r in rec_rows if r.source != "esakshi"]
    catalog = esakshi if esakshi else rec_rows

    works: List[Dict[str, Any]] = []
    category_counter: Counter = Counter()
    for rid, wid, wdesc, wcat, ramt, rdate, _src in catalog:
        wk = normkey(wdesc)
        exp_amt, exp_n = exp_by_wk.get(wk, (0.0, 0))
        comp_hit = None
        if wid is not None and int(wid) in comp_by_wid:
            comp_hit = comp_by_wid[int(wid)]
        elif wk in comp_by_wk:
            comp_hit = comp_by_wk[wk]
        is_completed = comp_hit is not None
        if wcat:
            category_counter[wcat] += 1
        works.append({
            "work_id": wid,
            "work_description": wdesc,
            "category": wcat,
            "amount": float(ramt or 0),
            "expenditure": exp_amt,
            "expenditure_transactions": exp_n,
            "expenditure_status": "linked" if exp_n else "no_linked_records",
            "status": "Completed" if is_completed else "Ongoing",
            "progress": 100.0 if is_completed else None,
            "recommendation_date": rdate,
            "completion_date": comp_hit[1] if comp_hit else None,
            "completed_value": float(comp_hit[0]) if comp_hit else None,
        })

    # Data-quality note: payments recorded under this MP that match no
    # recommended work in the catalog. Honest counts, never reassigned.
    matched_wks = {normkey(w["work_description"]) for w in works}
    unlinked_amt = sum(a for k, (a, _n) in exp_by_wk.items() if k not in matched_wks)

    allocated = float(m.allocated_amount or 0)
    expenditure = float(m.total_expenditure or 0)
    utilization = (expenditure / allocated * 100) if allocated > 0 else 0.0
    sanctioned_total = sum(w["amount"] for w in works)
    completed_detail = sum(1 for w in works if w["status"] == "Completed")

    return {
        "mp": {
            "id": m.id,
            "mp_name": m.mp_name,
            "house": house,
            "state": m.state,
            "constituency": m.constituency,
            "allocated_amount": allocated,
            "total_expenditure": expenditure,
            "unspent_amount": float(m.unspent_amount or 0),
            "remaining_amount": max(allocated - expenditure, 0.0),
            "utilization_percentage": round(utilization, 2),
            "transaction_count": int(m.transaction_count or 0),
            "successful_payments": int(m.successful_payments or 0),
            "pending_payments": int(m.pending_payments or 0),
            "average_rating": float(m.average_rating or 0),
        },
        "financial_summary": {
            "total_sanctioned": sanctioned_total if sanctioned_total else allocated,
            "total_expenditure": expenditure,
            "remaining_unspent": float(m.unspent_amount or 0) or max(allocated - expenditure, 0.0),
            "utilization_percentage": round(utilization, 2),
            # Official eSAKSHI utilization from the MP summary ledger — a
            # different basis (expenditure vs. amount recommended) than the
            # computed spent÷sanctioned above. Both exposed, clearly labeled.
            "official_utilization_percentage": float(m.utilization_percentage or 0),
        },
        "work_summary": {
            "recommended_works": recommended,
            "catalog_works": len(works),
            "completed_works": completed_n,
            "ongoing_pending_works": max(recommended - completed_n, 0),
            "sanctioned_amount": sanctioned_total,
            "completion_rate_percentage": float(m.completion_rate_percentage or 0)
            or (round(completed_n / recommended * 100, 2) if recommended else 0.0),
        },
        "completion": {
            "completion_rate": float(m.completion_rate_percentage or 0)
            or (round(completed_n / recommended * 100, 2) if recommended else 0.0),
            "completed_count": completed_n,
            "pending_count": max(recommended - completed_n, 0),
        },
        "categories": [
            {"category": cat, "count": n} for cat, n in category_counter.most_common(12)
        ],
        "works": works[:include_works_limit],
        "works_truncated": len(works) > include_works_limit,
        "data_quality": {
            "unlinked_payment_amount": round(unlinked_amt, 2),
            "legacy_works_excluded": len(legacy),
            "note": (
                "Payments are matched to recommended works by normalized work "
                "description within this MP's constituency; amounts that match "
                "no catalog work are reported here rather than reassigned."
            ),
        },
    }
