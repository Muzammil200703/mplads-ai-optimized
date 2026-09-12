"""
Expenditure Activity & Activity-Gap Intelligence
================================================

Analyzes the per-project expenditure history from the existing `expenditures`
table (loaded from expenditures.csv) to produce:

  - chronological activity summary (first/latest date, totals, counts)
  - monthly aggregation for charting
  - consecutive-record activity gaps with documented thresholds
  - "days since latest recorded activity"

MATCHING: reuses the exact conservative matching established in
backend/timeline.py — exact normalized (work_description, constituency,
state) key, with the expenditure row's MP name verified against the matched
recommended work. No fuzzy matching; ambiguous rows stay unmatched.

GAP THRESHOLDS (documented):
  <  30 days  -> normal (no flag)
  30 - 89     -> informational (no warning label, but returned in data)
  90 - 179    -> "long_gap"
  >= 180      -> "extended_gap"

All dates come solely from the recorded `expenditure_date` values. No date
is ever fabricated; days-since-latest uses the server's current date at
request time.
"""

import re
import threading
from datetime import date
from typing import Dict, List, Optional

from database import SessionLocal
import models

# ── Documented thresholds ───────────────────────────────────────
GAP_THRESHOLD_LONG = 90          # days
GAP_THRESHOLD_EXTENDED = 180     # days
GAP_INFO_MIN = 30                # days — below this: normal
MAX_MONTHLY_POINTS = 36          # cap chart points (3 years)
MAX_TRANSACTIONS_RETURNED = 50   # cap individual transaction list

# ── In-process index cache (shared with timeline module) ────────
_lock = threading.Lock()
_exp_ready = False
_exp_index: Dict[tuple, list] = {}   # key -> [{id, mp, amount, date, status}]
_rec_mp_index: Dict[tuple, str] = {} # key -> normalized mp of the recommended work


def _norm(s) -> str:
    if s is None:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def _iso_date(raw) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        except ValueError:
            return None
    return None


def _days_between(d1: str, d2: str) -> Optional[int]:
    try:
        return (date.fromisoformat(d2) - date.fromisoformat(d1)).days
    except (ValueError, TypeError):
        return None


def _build_index():
    """Load all expenditure rows plus the recommended-work MP map once."""
    global _exp_ready, _exp_index, _rec_mp_index
    with _lock:
        if _exp_ready:
            return
        db = SessionLocal()
        try:
            exp_index: Dict[tuple, list] = {}
            for desc, con, st, mp, amt, dt, status, eid in db.query(
                models.Expenditure.work_description,
                models.Expenditure.constituency,
                models.Expenditure.state,
                models.Expenditure.mp_name,
                models.Expenditure.expenditure_amount,
                models.Expenditure.expenditure_date,
                models.Expenditure.payment_status,
                models.Expenditure.id,
            ).all():
                d = _iso_date(dt)
                if not d:
                    continue  # rows without a valid date cannot participate in a timeline
                key = (_norm(desc), _norm(con), _norm(st))
                exp_index.setdefault(key, []).append(
                    {"id": eid, "mp": _norm(mp), "amount": amt, "date": d, "status": status}
                )

            rec_mp: Dict[tuple, str] = {}
            for desc, con, st, mp in db.query(
                models.RecommendedWork.work_description,
                models.RecommendedWork.constituency,
                models.RecommendedWork.state,
                models.RecommendedWork.mp_name,
            ).all():
                key = (_norm(desc), _norm(con), _norm(st))
                if key not in rec_mp:
                    rec_mp[key] = _norm(mp)

            _exp_index, _rec_mp_index = exp_index, rec_mp
            _exp_ready = True
        finally:
            db.close()


def _classify_gap(days: int) -> str:
    if days >= GAP_THRESHOLD_EXTENDED:
        return "extended_gap"
    if days >= GAP_THRESHOLD_LONG:
        return "long_gap"
    if days >= GAP_INFO_MIN:
        return "informational"
    return "normal"


def get_expenditure_activity(project) -> dict:
    """
    Build the full expenditure-activity payload for one project (model instance).
    """
    _build_index()

    key = (_norm(project.project_name), _norm(project.constituency), _norm(project.state))
    sanctioned_mp = _rec_mp_index.get(key)

    # Only attach expenditures whose MP matches the recommended work's MP
    rows = _exp_index.get(key, [])
    if sanctioned_mp:
        verified = [r for r in rows if r["mp"] == sanctioned_mp]
    else:
        # No recommended work matched — cannot verify MP; keep records only if
        # the key itself matched uniquely (still requires exact desc+con+state).
        verified = rows

    # Sort chronologically
    verified.sort(key=lambda r: (r["date"], r["id"] or 0))

    total = sum(float(r["amount"] or 0) for r in verified)
    dates = [r["date"] for r in verified]
    today = date.today().isoformat()

    # ── Consecutive gaps ──────────────────────────────────────
    gaps = []
    for i in range(1, len(dates)):
        gap_days = _days_between(dates[i - 1], dates[i])
        if gap_days is not None and gap_days > 0:
            gaps.append({
                "start_date": dates[i - 1],
                "end_date": dates[i],
                "gap_days": gap_days,
                "classification": _classify_gap(gap_days),
            })
    gaps.sort(key=lambda g: g["gap_days"], reverse=True)
    flagged_gaps = [g for g in gaps if g["classification"] in ("long_gap", "extended_gap")]

    # ── Days since latest recorded activity ───────────────────
    days_since_latest = None
    if dates:
        d = _days_between(dates[-1], today)
        if d is not None and d >= 0:
            days_since_latest = d

    # ── Monthly aggregation (chart) ───────────────────────────
    monthly: Dict[str, dict] = {}
    for r in verified:
        ym = r["date"][:7]
        slot = monthly.setdefault(ym, {"amount": 0.0, "count": 0, "statuses": set()})
        slot["amount"] += float(r["amount"] or 0)
        slot["count"] += 1
        if r.get("status"):
            slot["statuses"].add(str(r["status"]))
    monthly_list = [
        {
            "month": ym,
            "amount": round(v["amount"], 2),
            "transaction_count": v["count"],
            "payment_statuses": sorted(v["statuses"]),
        }
        for ym, v in sorted(monthly.items())
    ]
    if len(monthly_list) > MAX_MONTHLY_POINTS:
        monthly_list = monthly_list[-MAX_MONTHLY_POINTS:]

    # ── Activity status ───────────────────────────────────────
    if not verified:
        activity_status = "no_records"
    elif flagged_gaps and flagged_gaps[0]["classification"] == "extended_gap":
        activity_status = "extended_gap"
    elif flagged_gaps:
        activity_status = "long_gap"
    else:
        activity_status = "normal"

    # ── Activity indicators (calculated, clearly labelled) ────
    indicators = []
    for g in flagged_gaps[:3]:
        label = "Extended expenditure activity gap" if g["classification"] == "extended_gap" else "Long expenditure activity gap"
        indicators.append({
            "indicator": label,
            "detail": f"No expenditure activity recorded for {g['gap_days']} days ({g['start_date']} → {g['end_date']}).",
            "severity": "high" if g["classification"] == "extended_gap" else "medium",
        })
    if days_since_latest is not None and days_since_latest >= GAP_THRESHOLD_EXTENDED:
        indicators.append({
            "indicator": "Extended inactivity",
            "detail": f"Latest recorded expenditure was {days_since_latest} days ago ({dates[-1]}).",
            "severity": "high",
        })
    elif days_since_latest is not None and days_since_latest >= GAP_THRESHOLD_LONG:
        indicators.append({
            "indicator": "No recent expenditure activity",
            "detail": f"Latest recorded expenditure was {days_since_latest} days ago ({dates[-1]}).",
            "severity": "medium",
        })

    # ── Transactions (capped — most recent first) ─────────────
    recent = list(reversed(verified[-MAX_TRANSACTIONS_RETURNED:]))
    transactions = [
        {
            "date": r["date"],
            "amount": float(r["amount"] or 0),
            "payment_status": r.get("status"),
        }
        for r in recent
    ]

    return {
        "total_expenditure": round(total, 2),
        "transaction_count": len(verified),
        "transactions": transactions,
        "transactions_returned": len(transactions),
        "transactions_truncated": len(verified) > MAX_TRANSACTIONS_RETURNED,
        "first_activity_date": dates[0] if dates else None,
        "latest_activity_date": dates[-1] if dates else None,
        "days_since_latest_activity": days_since_latest,
        "activity_gaps": gaps[:10],
        "largest_gap": (
            {"start_date": flagged_gaps[0]["start_date"], "end_date": flagged_gaps[0]["end_date"], "gap_days": flagged_gaps[0]["gap_days"]}
            if flagged_gaps else None
        ),
        "largest_gap_days": flagged_gaps[0]["gap_days"] if flagged_gaps else 0,
        "activity_status": activity_status,
        "monthly_activity": monthly_list,
        "indicators": indicators,
        "match_confidence": "mp_verified" if sanctioned_mp and rows else ("key_exact" if rows else None),
        "data_source": "expenditures",
        "thresholds": {
            "long_gap_days": GAP_THRESHOLD_LONG,
            "extended_gap_days": GAP_THRESHOLD_EXTENDED,
            "informational_min_days": GAP_INFO_MIN,
        },
        "disclaimer": (
            "An expenditure activity gap indicates no recorded financial activity during the period. "
            "It does not necessarily mean physical work stopped — data may be incomplete or not recently updated. "
            "These are data-derived indicators and do not establish the cause of any delay."
        ),
    }
