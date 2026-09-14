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

MEMORY (512MB Render instance)
──────────────────────────────
This module owns the ONE shared in-process work index (timeline.py
delegates to it). It is deliberately compact:

  - The (work_description, constituency, state) matching key is normalized
    and grouped by SQLite in SQL, so normalized key strings exist only
    once per distinct work (SQL GROUP BY), never once per row.
  - Expenditure rows are stored as plain tuples (mp, amount, date,
    status, id) instead of per-row dicts — roughly 5x smaller than the
    previous dict-per-row layout for 106k rows.
  - Rows are streamed from the cursor (yield_per), so only the final
    compact structures ever exist in memory — not a full materialized
    result set plus the index.
  - Recommended/completed works keep only the fields consumers use
    (first recommended MP/amount/date, completed amount/date).

The old design held two near-duplicate dict-based copies of the same data
(one here, one in timeline.py) at roughly 200+ MB each; this shared layout
holds the same information in a fraction of that.
"""

import re
import threading
from datetime import date
from typing import Dict, List, Optional, Tuple

from database import SessionLocal
import models

# ── Documented thresholds ───────────────────────────────────────
GAP_THRESHOLD_LONG = 90          # days
GAP_THRESHOLD_EXTENDED = 180     # days
GAP_INFO_MIN = 30                # days — below this: normal
MAX_MONTHLY_POINTS = 36          # cap chart points (3 years)
MAX_TRANSACTIONS_RETURNED = 50   # cap individual transaction list

# ── Shared in-process index cache (single owner; timeline delegates) ──
_lock = threading.Lock()
_ready = False

# key -> list of (mp, amount, date, status, id) tuples for that work.
# Key strings live only in the dict (one per distinct work), not per row.
_exp_rows: Dict[str, list] = {}
# key -> (mp, amount, date, id) of the FIRST recommended work for that key
_rec_first: Dict[str, tuple] = {}
# key -> (date, amount, id) of the completed work for that key (first wins)
_comp_by_key: Dict[str, tuple] = {}


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
    """Build the shared compact work index once (streamed, SQL-grouped).

    SQLite groups rows by the normalized key in SQL, so this process only
    ever holds one key string per distinct work plus compact tuple rows.
    """
    global _ready, _exp_rows, _rec_first, _comp_by_key
    with _lock:
        if _ready:
            return
        db = SessionLocal()
        try:
            # ── Expenditures: SQL GROUP BY on the normalized key ──
            # Streamed via yield_per so the full result never materializes.
            exp_q = (
                db.query(
                    models.Expenditure.work_description,
                    models.Expenditure.constituency,
                    models.Expenditure.state,
                    models.Expenditure.mp_name,
                    models.Expenditure.expenditure_amount,
                    models.Expenditure.expenditure_date,
                    models.Expenditure.payment_status,
                    models.Expenditure.id,
                )
                .filter(
                    models.Expenditure.work_description.isnot(None),
                    models.Expenditure.work_description != "",
                    models.Expenditure.constituency.isnot(None),
                    models.Expenditure.constituency != "",
                    models.Expenditure.state.isnot(None),
                    models.Expenditure.state != "",
                    models.Expenditure.expenditure_date.isnot(None),
                )
                .yield_per(50)
            )
            exp_rows: Dict[str, list] = {}
            for desc, con, st, mp, amt, dt, status, eid in exp_q:
                d = _iso_date(dt)
                if not d:
                    continue  # rows without a valid date cannot participate
                key = f"{_norm(desc)}\u241f{_norm(con)}\u241f{_norm(st)}"
                exp_rows.setdefault(key, []).append(
                    (_norm(mp), amt, d, status, eid)
                )

            # ── Recommended works: first (earliest id) per key ──
            rec_first: Dict[str, tuple] = {}
            rec_q = (
                db.query(
                    models.RecommendedWork.work_description,
                    models.RecommendedWork.constituency,
                    models.RecommendedWork.state,
                    models.RecommendedWork.mp_name,
                    models.RecommendedWork.recommended_amount,
                    models.RecommendedWork.recommendation_date,
                    models.RecommendedWork.id,
                )
                .filter(
                    models.RecommendedWork.work_description.isnot(None),
                    models.RecommendedWork.work_description != "",
                    models.RecommendedWork.constituency.isnot(None),
                    models.RecommendedWork.constituency != "",
                    models.RecommendedWork.state.isnot(None),
                    models.RecommendedWork.state != "",
                )
                .yield_per(50)
            )
            for desc, con, st, mp, amt, dt, rid in rec_q:
                key = f"{_norm(desc)}\u241f{_norm(con)}\u241f{_norm(st)}"
                if key not in rec_first:
                    # (mp, amount, date, id) — id kept for source attribution
                    rec_first[key] = (_norm(mp), amt, _iso_date(dt), rid)

            # ── Completed works: first per key ──
            comp_by_key: Dict[str, tuple] = {}
            comp_q = (
                db.query(
                    models.CompletedWork.work_description,
                    models.CompletedWork.constituency,
                    models.CompletedWork.state,
                    models.CompletedWork.final_amount,
                    models.CompletedWork.completed_date,
                    models.CompletedWork.id,
                )
                .filter(
                    models.CompletedWork.work_description.isnot(None),
                    models.CompletedWork.work_description != "",
                    models.CompletedWork.constituency.isnot(None),
                    models.CompletedWork.constituency != "",
                    models.CompletedWork.state.isnot(None),
                    models.CompletedWork.state != "",
                )
                .yield_per(50)
            )
            for desc, con, st, amt, dt, cid in comp_q:
                key = f"{_norm(desc)}\u241f{_norm(con)}\u241f{_norm(st)}"
                if key not in comp_by_key:
                    # (date, amount, id) — id kept for source attribution
                    comp_by_key[key] = (_iso_date(dt), amt, cid)

            _exp_rows, _rec_first, _comp_by_key = exp_rows, rec_first, comp_by_key
            _ready = True
        finally:
            db.close()


def _project_key(project) -> str:
    return f"{_norm(project.project_name)}\u241f{_norm(project.constituency)}\u241f{_norm(project.state)}"


def _classify_gap(days: int) -> str:
    if days >= GAP_THRESHOLD_EXTENDED:
        return "extended_gap"
    if days >= GAP_THRESHOLD_LONG:
        return "long_gap"
    if days >= GAP_INFO_MIN:
        return "informational"
    return "normal"


def _verified_rows(project) -> Tuple[Optional[str], list]:
    """Rows for this project's work key, MP-verified when possible.

    Returns (sanctioned_mp_or_None, rows). When a recommended work matches
    the key, only expenditures whose MP equals that work's MP are kept.
    """
    _build_index()
    key = _project_key(project)
    rec = _rec_first.get(key)
    sanctioned_mp = rec[0] if rec else None
    rows = _exp_rows.get(key, [])
    if sanctioned_mp:
        rows = [r for r in rows if r[0] == sanctioned_mp]
    return sanctioned_mp, rows


# ═════════════ Shared accessors (timeline.py delegates here) ═════════════

def shared_indexes():
    """Return (rec_first, comp_by_key, exp_rows) after ensuring built.

    timeline.py uses this instead of keeping its own duplicate copy of the
    same datasets in memory.
    """
    _build_index()
    return _rec_first, _comp_by_key, _exp_rows


def first_recommended_mp(project) -> Optional[str]:
    """Normalized MP name of the first recommended work for this project key."""
    _build_index()
    rec = _rec_first.get(_project_key(project))
    return rec[0] if rec else None


def completed_for_key(project) -> Optional[tuple]:
    """(completed_date, final_amount) of the completed work for this key, if any."""
    _build_index()
    return _comp_by_key.get(_project_key(project))


def expenditure_count_for_key(project) -> int:
    """Number of expenditure rows recorded for this project's work key.

    Used by endpoints that only need a count — avoids loading the rows.
    """
    _build_index()
    return len(_exp_rows.get(_project_key(project), []))


# ═══════════════════ Feature payloads ═══════════════════════════════════

def get_expenditure_span(project) -> Optional[dict]:
    """
    Compact expenditure-activity span for list views (Risk Center).

    Returns the first/latest recorded expenditure dates, the day count between
    them, and a conservative delay indicator derived ONLY from the combination
    of activity duration and reported physical completion. This is recorded
    financial activity duration — NOT an official start date or contractual
    delay (no such dates exist in the source data).

    Returns None when the project has no matched expenditure records with
    valid dates.
    """
    sanctioned_mp, rows = _verified_rows(project)

    if not rows:
        return None

    dates = sorted(r[2] for r in rows)
    first_date, latest_date = dates[0], dates[-1]
    span_days = _days_between(first_date, latest_date)
    if span_days is None or span_days < 0:
        return None

    completion = float(project.completion_percentage or 0)

    # Indicator bands (documented, conservative):
    #   A long recorded-activity window combined with very low reported
    #   physical completion is an observation worth review — never a claim.
    if span_days >= 365 and completion < 10:
        indicator, severity = "Severe Execution Concern", "high"
    elif span_days >= 180 and completion < 25:
        indicator, severity = "Potential Delay", "medium"
    elif span_days >= 180:
        indicator, severity = "Extended Activity", "low"
    else:
        indicator, severity = None, None

    return {
        "first_expenditure_date": first_date,
        "latest_expenditure_date": latest_date,
        "activity_days": span_days,
        "transaction_count": len(rows),
        "completion_percentage": completion,
        "delay_indicator": indicator,
        "delay_severity": severity,
        "match_confidence": "mp_verified" if sanctioned_mp else "key_exact",
    }


def get_expenditure_activity(project) -> dict:
    """
    Build the full expenditure-activity payload for one project (model instance).
    """
    sanctioned_mp, rows = _verified_rows(project)
    key_matched = bool(_exp_rows.get(_project_key(project)))

    # Sort chronologically (tuple: mp, amount, date, status, id)
    verified = sorted(rows, key=lambda r: (r[2], r[4] or 0))

    total = sum(float(r[1] or 0) for r in verified)
    dates = [r[2] for r in verified]
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
        ym = r[2][:7]
        slot = monthly.setdefault(ym, {"amount": 0.0, "count": 0, "statuses": set()})
        slot["amount"] += float(r[1] or 0)
        slot["count"] += 1
        if r[3]:
            slot["statuses"].add(str(r[3]))
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
            "date": r[2],
            "amount": float(r[1] or 0),
            "payment_status": r[3],
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
        "match_confidence": "mp_verified" if sanctioned_mp and rows else ("key_exact" if key_matched and rows else None),
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
