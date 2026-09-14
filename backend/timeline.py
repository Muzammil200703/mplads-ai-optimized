import logging
import re
import threading
from datetime import date, datetime
from typing import Dict, List, Optional, Set

import models
from database import SessionLocal

logger = logging.getLogger("mplads.timeline")

# ── Tuning ──────────────────────────────────────────────────────
MAX_EXPENDITURE_EVENTS = 10   # show at most the 10 most recent payment dates
CACHE_MAX = 5000              # in-process result cache bound

# ── Result cache ────────────────────────────────────────────────
# The work-level datasets themselves are NOT loaded here anymore. They live
# once, in compact form, in activity.py's shared index (see activity.py's
# memory notes). timeline.py delegates to it — keeping a second dict-heavy
# copy of the same 106k rows here doubled peak memory for no benefit.
_result_cache: Dict[int, Optional[dict]] = {}
_persist_checked: Set[int] = set()


def _norm(s) -> str:
    """Normalize a string for exact matching."""
    if s is None:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def _iso_date(raw) -> Optional[str]:
    """Parse a source date string to YYYY-MM-DD. Returns None when absent/invalid."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Source format: '2025-02-14T00:00:00.000Z'
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
        a = date.fromisoformat(d1)
        b = date.fromisoformat(d2)
        return (b - a).days
    except (ValueError, TypeError):
        return None


# ── Event construction ──────────────────────────────────────────

def _build_events(project) -> List[dict]:
    """Build the ordered lifecycle event list for one project from matched data.

    Uses the shared compact index from activity.py (built once per process,
    streamed from SQL). Expenditure rows are tuples:
        (mp, amount, date, status, id)
    Recommended/completed records come back as:
        rec  = (mp, amount, date, id)
        comp = (date, amount, id)
    """
    import activity  # local import avoids any module-load ordering concerns

    rec_first, comp_by_key, exp_rows = activity.shared_indexes()

    key = activity._project_key(project)
    events: List[dict] = []

    rec = rec_first.get(key)
    comp = comp_by_key.get(key)

    # 1. Recommendation (only when a real date exists — never invented)
    if rec and rec[2]:
        events.append({
            "event_type": "recommendation",
            "date": rec[2],
            "title": "Recommended by MP",
            "description": f"Work recommended with estimated cost of ₹{int(rec[1] or 0):,}."
            if rec[1] else "Work recommended under MPLADS.",
            "amount": rec[1],
            "progress_percentage": None,
            "source_dataset": "recommended_works",
            "source_record_id": str(rec[3]) if rec[3] is not None else None,
            "match_confidence": "exact",
        })

    # 2. Expenditure payments — MP-verified only, aggregated per date
    exp = exp_rows.get(key)
    if rec and exp:
        verified = [e for e in exp if e[0] == rec[0]]
        if verified:
            by_date: Dict[str, dict] = {}
            for e in verified:
                slot = by_date.setdefault(e[2], {"amount": 0.0, "count": 0, "statuses": set(), "ids": []})
                slot["amount"] += (e[1] or 0.0)
                slot["count"] += 1
                if e[3]:
                    slot["statuses"].add(str(e[3]))
                slot["ids"].append(str(e[4]))

            dates_sorted = sorted(by_date.keys())
            shown = dates_sorted[-MAX_EXPENDITURE_EVENTS:] if len(dates_sorted) > MAX_EXPENDITURE_EVENTS else dates_sorted
            for d in shown:
                slot = by_date[d]
                desc = f"₹{int(slot['amount']):,} across {slot['count']} payment{'s' if slot['count'] > 1 else ''}."
                notable = [s for s in slot["statuses"] if s and s.lower() not in ("payment success", "success", "paid")]
                if notable:
                    desc += f" Payment status: {'; '.join(sorted(notable))}."
                events.append({
                    "event_type": "expenditure",
                    "date": d,
                    "title": "Expenditure recorded",
                    "description": desc,
                    "amount": slot["amount"],
                    "progress_percentage": None,
                    "source_dataset": "expenditures",
                    "source_record_id": ",".join(slot["ids"][:5]),
                    "match_confidence": "mp_verified",
                })
            if len(dates_sorted) > MAX_EXPENDITURE_EVENTS:
                total = sum(s["amount"] for s in by_date.values())
                events.append({
                    "event_type": "expenditure",
                    "date": dates_sorted[0],
                    "title": "Earlier payments (summarised)",
                    "description": (
                        f"{len(dates_sorted) - MAX_EXPENDITURE_EVENTS} earlier payment date(s) not shown; "
                        f"recorded expenditure totals ₹{int(total):,} across {len(verified)} payment(s)."
                    ),
                    "amount": None,
                    "progress_percentage": None,
                    "source_dataset": "expenditures",
                    "source_record_id": None,
                    "match_confidence": "mp_verified",
                })

    # 3. Completion (only when a real date exists)
    if comp and comp[0]:
        desc = "Work recorded as completed."
        if comp[1]:
            desc += f" Final recorded amount: ₹{int(comp[1]):,}."
        events.append({
            "event_type": "completion",
            "date": comp[0],
            "title": "Completed",
            "description": desc,
            "amount": comp[1],
            "progress_percentage": 100.0,
            "source_dataset": "completed_works",
            "source_record_id": str(comp[2]) if comp[2] is not None else None,
            "match_confidence": "exact",
        })

    events.sort(key=lambda e: (e["date"] or "9999-12-31", e["event_type"]))
    return events


# ── Delay intelligence ──────────────────────────────────────────

def _delay_intelligence(project, events: List[dict]) -> dict:
    """
    Compute OBSERVED indicators only. Formal delay_days is not calculable
    (no expected-completion date exists in any source dataset) and is never
    fabricated. Possible factors are null — no recorded reason field exists
    at project level in the source data.
    """
    sanctioned = float(project.sanctioned_amount or 0)
    expenditure = float(project.expenditure or 0)
    completion = float(project.completion_percentage or 0)
    status = str(project.status or "")

    utilization = round(expenditure / sanctioned * 100, 1) if sanctioned > 0 else None

    indicators: List[dict] = []
    metrics: dict = {}

    rec_ev = next((e for e in events if e["event_type"] == "recommendation"), None)
    exp_events = [e for e in events if e["event_type"] == "expenditure" and e["amount"]]
    comp_ev = next((e for e in events if e["event_type"] == "completion"), None)

    rec_date = rec_ev["date"] if rec_ev else None
    first_exp_date = exp_events[0]["date"] if exp_events else None  # events sorted ascending
    last_activity_date = max(
        (e["date"] for e in events if e["date"]), default=None
    )

    # Timeline metrics (days between real recorded dates only)
    if rec_date and first_exp_date:
        d = _days_between(rec_date, first_exp_date)
        if d is not None and d >= 0:
            metrics["days_recommendation_to_first_expenditure"] = d
    if rec_date and comp_ev and comp_ev.get("date"):
        d = _days_between(rec_date, comp_ev["date"])
        if d is not None and d >= 0:
            metrics["days_recommendation_to_completion"] = d

    completed = status.lower() == "completed"

    if not completed and last_activity_date:
        d = _days_between(last_activity_date, date.today().isoformat())
        if d is not None and d >= 0:
            metrics["days_since_last_recorded_activity"] = d

    # Financial vs physical comparison
    fin_phys = None
    if utilization is not None:
        gap = round(utilization - completion, 1)
        fin_phys = {
            "financial_utilization_pct": utilization,
            "physical_completion_pct": completion,
            "gap_pct": gap,
        }
        if utilization > 100:
            fin_phys["verdict"] = "Reported expenditure exceeds the sanctioned amount."
        elif gap >= 20:
            fin_phys["verdict"] = "Significant financial–physical progress gap."
        elif gap >= 10:
            fin_phys["verdict"] = "Moderate gap between financial utilization and physical progress."
        else:
            fin_phys["verdict"] = "Financial utilization and physical progress are broadly consistent."

    # Observed indicators (each grounded in actual values)
    if utilization is not None and utilization - completion >= 20 and expenditure > 0:
        indicators.append({
            "indicator": "Financial–physical progress gap",
            "detail": f"Financial utilization is {utilization}% while reported physical completion is {completion}% (gap of {round(utilization - completion)} percentage points).",
            "severity": "high",
        })
    elif utilization is not None and 10 <= utilization - completion < 20 and expenditure > 0:
        indicators.append({
            "indicator": "Moderate financial–physical gap",
            "detail": f"Financial utilization is {utilization}% while reported physical completion is {completion}%.",
            "severity": "medium",
        })

    if not completed and metrics.get("days_since_last_recorded_activity") is not None:
        d = metrics["days_since_last_recorded_activity"]
        if d >= 365:
            indicators.append({"indicator": "No recent recorded activity", "detail": f"No expenditure, completion, or recommendation activity recorded for {d} days (last recorded: {last_activity_date}).", "severity": "high"})
        elif d >= 180:
            indicators.append({"indicator": "No recent recorded activity", "detail": f"Last recorded activity was {d} days ago ({last_activity_date}).", "severity": "medium"})

    if completed and completion < 100:
        indicators.append({
            "indicator": "Completion below 100%",
            "detail": f"Project is marked Completed but reported physical completion is {completion}% — completion records may require verification.",
            "severity": "medium" if completion < 50 else "low",
        })

    if expenditure > sanctioned > 0:
        indicators.append({
            "indicator": "Expenditure exceeds sanctioned amount",
            "detail": f"₹{int(expenditure):,} spent against ₹{int(sanctioned):,} sanctioned ({utilization}% utilization).",
            "severity": "high",
        })

    if rec_date and not exp_events and not completed:
        d = _days_between(rec_date, date.today().isoformat())
        if d is not None and d >= 180:
            indicators.append({
                "indicator": "No expenditure recorded since recommendation",
                "detail": f"Work was recommended on {rec_date} ({d} days ago) but no matching expenditure has been recorded. Progress data may be missing or outdated.",
                "severity": "medium",
            })

    if sanctioned >= 1000000 and completion == 0 and expenditure == 0:
        indicators.append({
            "indicator": "Zero progress and zero expenditure",
            "detail": f"₹{int(sanctioned):,} sanctioned with 0% progress and ₹0 expenditure recorded — progress data may require updating.",
            "severity": "medium",
        })

    # Status classification (conservative)
    if not events:
        timeline_status = "INSUFFICIENT TIMELINE DATA"
    elif completed:
        timeline_status = "COMPLETED"
    elif any(i["severity"] == "high" for i in indicators):
        timeline_status = "AT RISK"
    else:
        timeline_status = "ON TRACK"

    return {
        "status": timeline_status,
        "delay_days": None,
        "delay_calculable": False,
        "expected_completion_date": None,
        "delay_note": (
            "Formal delay cannot be calculated: no expected-completion (or sanction/start) "
            "date exists in the available MPLADS datasets. Only observed indicators are shown."
        ),
        "observed_indicators": indicators,
        "recorded_reason": None,
        "recorded_reason_note": "No recorded delay-reason field exists at project level in the source datasets.",
        "possible_factors": None,
        "financial_physical": fin_phys,
        "timeline_metrics": metrics,
    }


# ── Public API ──────────────────────────────────────────────────

def _persist_events(db, project_id: int, events: List[dict]):
    """Persist computed events so restarts don't recompute. Never raises."""
    try:
        db.query(models.ProjectTimelineEvent).filter(
            models.ProjectTimelineEvent.project_id == project_id
        ).delete()
        for e in events:
            db.add(models.ProjectTimelineEvent(
                project_id=project_id,
                event_type=e["event_type"],
                event_date=e["date"],
                title=e["title"],
                description=e["description"],
                amount=e["amount"],
                progress_percentage=e["progress_percentage"],
                source_dataset=e["source_dataset"],
                source_record_id=e["source_record_id"],
                match_confidence=e["match_confidence"],
            ))
        db.commit()
    except Exception as exc:  # persistence is an optimization, never a failure
        db.rollback()
        logger.warning("Timeline persistence failed for project %s: %s", project_id, exc)


def get_project_timeline(project_id: int) -> Optional[dict]:
    """
    Return the full timeline payload for a project, or None if the project
    does not exist. Results are cached in-process; events are persisted to
    the project_timeline_events table on first computation.
    """
    if project_id in _result_cache:
        return _result_cache[project_id]

    db = SessionLocal()
    try:
        project = db.query(models.Project).filter(models.Project.id == project_id).first()
        if not project:
            return None

        # Fast path: load previously persisted events
        persisted = (
            db.query(models.ProjectTimelineEvent)
            .filter(models.ProjectTimelineEvent.project_id == project_id)
            .order_by(models.ProjectTimelineEvent.event_date.asc().nullslast())
            .all()
        )
        if persisted:
            events = [
                {
                    "event_type": e.event_type,
                    "date": e.event_date,
                    "title": e.title,
                    "description": e.description,
                    "amount": e.amount,
                    "progress_percentage": e.progress_percentage,
                    "source_dataset": e.source_dataset,
                    "source_record_id": e.source_record_id,
                    "match_confidence": e.match_confidence,
                }
                for e in persisted
            ]
        else:
            events = _build_events(project)
            _persist_events(db, project_id, events)

        delay = _delay_intelligence(project, events)

        dates = [e["date"] for e in events if e["date"]]
        matched = {
            "recommended": any(e["event_type"] == "recommendation" for e in events),
            "expenditures": any(e["event_type"] == "expenditure" and e.get("amount") for e in events),
            "completed": any(e["event_type"] == "completion" for e in events),
            "expenditure_match_confidence": (
                "mp_verified" if any(e["event_type"] == "expenditure" for e in events) else None
            ),
        }

        payload = {
            "project_id": project_id,
            "events": events,
            "delay_intelligence": delay,
            "meta": {
                "matching": matched,
                "data_period": {"from": min(dates) if dates else None, "to": max(dates) if dates else None},
                "is_historical_dataset": True,
                "disclaimer": (
                    "Timeline events come from periodically published MPLADS work-level records, "
                    "not a live feed. Missing lifecycle stages (sanction, work start, expected "
                    "completion) are absent from the source data and are never estimated."
                ),
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "events_count": len(events),
            },
        }
        if len(_result_cache) < CACHE_MAX:
            _result_cache[project_id] = payload
        return payload
    finally:
        db.close()
