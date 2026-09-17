"""
project_rec_info builder — backend source of truth for recommendation facts
===========================================================================

One derived, rebuildable table answering, per project:
  • recommendation_date — earliest recorded recommendation for this work
    (from recommended_works.recommendation_date)
  • recommended_by      — MP name from that recommended work
  • approx_start_date   — earliest MP-verified expenditure_date
    (proxy for project start; the UI always labels it "Approx.")
  • has_expenditure     — whether any MP-verified expenditure exists

Linkage is identical to activity.py: the normalized (name, constituency,
state) work key via SQL normkey() (expression-indexed), with the same
MP-verification rule (when a recommended work matches the key, only
expenditures whose MP equals that work's MP count). When no recommended
work matches, the earliest expenditure across any MP is used — exactly
what activity._verified_rows does.

Nothing is invented: projects with no matching recommended_works row get
no recommendation date/MP; projects with no matched expenditure get no
start date. The table is fully derived — rebuild(db) regenerates it after
any data sync. All aggregation runs inside SQLite; peak Python memory
stays flat (no row materialization).
"""

import threading
import time
from typing import Dict

from sqlalchemy import text

import models
from database import SessionLocal, normkey as _normkey

_build_lock = threading.Lock()
_last_build: Dict = {"ok": False, "rows": 0, "at": 0.0, "error": None}


def _normdate_sql(value) -> str:
    """SQL-side date normalizer: 'YYYY-MM-DD...' → 'YYYY-MM-DD', else ''."""
    s = str(value or "").strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        candidate = s[:10]
        try:
            time.strptime(candidate, "%Y-%m-%d")
            return candidate
        except ValueError:
            return ""
    return ""


def rebuild(db, force: bool = False) -> dict:
    """Rebuild project_rec_info from source tables in one SQL statement.

    Uses the same connection-level normkey()/normdate() SQL functions that
    the per-key lookups rely on. Row materialization happens inside SQLite
    only (transient tables spill to temp storage), so this is safe on a
    512MB container.
    """
    with _build_lock:
        if _last_build["ok"] and not force and time.time() - _last_build["at"] < 300:
            return {"skipped": True, "rows": _last_build["rows"]}

        conn = db.connection().connection  # raw sqlite3 connection
        conn.create_function("normkey", 1, _normkey, deterministic=True)
        conn.create_function("normdate", 1, _normdate_sql, deterministic=True)
        t0 = time.time()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM project_rec_info")
            cur.execute("""
                INSERT INTO project_rec_info
                    (project_id, recommendation_date, recommended_by,
                     approx_start_date, has_expenditure)
                WITH
                -- Earliest recommendation per work key (date, MP, normalized MP)
                rec_agg AS (
                    SELECT dk, ck, sk, rec_date, rec_mp, mpk FROM (
                        SELECT normkey(rw.work_description)              AS dk,
                               normkey(rw.constituency)                  AS ck,
                               normkey(rw.state)                         AS sk,
                               normdate(rw.recommendation_date)          AS rec_date,
                               TRIM(COALESCE(rw.mp_name, ''))            AS rec_mp,
                               normkey(rw.mp_name)                       AS mpk,
                               ROW_NUMBER() OVER (
                                   PARTITION BY normkey(rw.work_description),
                                                normkey(rw.constituency),
                                                normkey(rw.state)
                                   ORDER BY (normdate(rw.recommendation_date) = ''),
                                            normdate(rw.recommendation_date),
                                            rw.id
                               ) AS rn
                        FROM recommended_works rw
                    ) WHERE rn = 1
                ),
                -- Earliest expenditure per (work key, MP)
                exp_by_mp AS (
                    SELECT normkey(e.work_description)               AS dk,
                           normkey(e.constituency)                   AS ck,
                           normkey(e.state)                          AS sk,
                           normkey(e.mp_name)                        AS mpk,
                           MIN(NULLIF(normdate(e.expenditure_date), '')) AS first_exp
                    FROM expenditures e
                    GROUP BY dk, ck, sk, mpk
                ),
                -- Earliest expenditure per work key across any MP
                exp_any AS (
                    SELECT dk, ck, sk, MIN(first_exp) AS any_first
                    FROM exp_by_mp
                    GROUP BY dk, ck, sk
                )
                SELECT p.id,
                       CASE WHEN ra.rec_date IS NOT NULL AND ra.rec_date <> ''
                            THEN ra.rec_date END,
                       CASE WHEN ra.rec_mp IS NOT NULL AND ra.rec_mp <> ''
                            THEN ra.rec_mp END,
                       -- MP-verified when a recommendation exists, else any-MP
                       -- earliest (same rule as activity._verified_rows)
                       CASE
                           WHEN ra.mpk IS NOT NULL AND ev.first_exp IS NOT NULL THEN ev.first_exp
                           WHEN ra.mpk IS NULL     AND ea.any_first IS NOT NULL THEN ea.any_first
                       END,
                       CASE WHEN (ra.mpk IS NOT NULL AND ev.first_exp IS NOT NULL)
                                 OR (ra.mpk IS NULL AND ea.any_first IS NOT NULL)
                            THEN 1 ELSE 0 END
                FROM projects p
                LEFT JOIN rec_agg ra
                       ON ra.dk = normkey(p.project_name)
                      AND ra.ck = normkey(p.constituency)
                      AND ra.sk = normkey(p.state)
                LEFT JOIN exp_by_mp ev
                       ON ev.dk = normkey(p.project_name)
                      AND ev.ck = normkey(p.constituency)
                      AND ev.sk = normkey(p.state)
                      AND ra.mpk IS NOT NULL AND ev.mpk = ra.mpk
                LEFT JOIN exp_any ea
                       ON ea.dk = normkey(p.project_name)
                      AND ea.ck = normkey(p.constituency)
                      AND ea.sk = normkey(p.state)
            """)
            conn.commit()
            rows = cur.execute("SELECT COUNT(*) FROM project_rec_info").fetchone()[0]
            dated = cur.execute(
                "SELECT COUNT(*) FROM project_rec_info WHERE recommendation_date IS NOT NULL"
            ).fetchone()[0]
            with_exp = cur.execute(
                "SELECT COUNT(*) FROM project_rec_info WHERE has_expenditure = 1"
            ).fetchone()[0]
            _last_build.update(ok=True, rows=rows, at=time.time(), error=None)
            return {
                "ok": True,
                "rows": rows,
                "with_recommendation_date": dated,
                "with_expenditure": with_exp,
                "seconds": round(time.time() - t0, 2),
            }
        except Exception as exc:
            conn.rollback()
            _last_build.update(ok=False, error=str(exc), at=time.time())
            return {"ok": False, "error": str(exc)}


def rebuild_if_empty_async() -> None:
    """Kick off a background rebuild when the table has no rows yet.

    The table persists in the DB file, so this normally runs only once per
    database lifetime (or after a fresh data sync drops/recreates rows).
    Pure SQL work in a worker thread — startup stays lightweight.
    """
    def _worker():
        db = SessionLocal()
        try:
            existing = db.execute(
                text("SELECT COUNT(*) FROM project_rec_info")
            ).scalar() or 0
            if existing == 0:
                rebuild(db, force=True)
        except Exception:
            pass  # table may not exist yet — Base.metadata.create_all handles it
        finally:
            db.close()

    threading.Thread(target=_worker, name="rec-info-rebuild", daemon=True).start()
