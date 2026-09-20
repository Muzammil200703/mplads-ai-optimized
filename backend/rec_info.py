"""
project_rec_info builder — backend source of truth for recommendation facts
===========================================================================

One derived, rebuildable table answering, per project:
  • recommendation_date — earliest recorded recommendation for this work
    (from recommended_works.recommendation_date)
  • recommended_by      — MP name from that recommended work
  • approx_start_date   — earliest VALID expenditure_date, where "valid"
    means the record is genuinely linked to THIS project's work AND is on
    or after the recommendation date (a payment can only follow the work
    being recommended — anything earlier indicates a cross-project match
    or a data anomaly, never a real project start)
  • start_status        — 'valid' | 'pre_recommendation' | 'no_expenditure'
  • has_expenditure     — whether any linked expenditure exists at all
  • linked_expenditure  — SUM of the MP+IDA-verified linked payments,
    attributed to the project ONLY when its work key maps to exactly ONE
    catalog row (see work_key_rows below). The AUTHORITATIVE per-project
    spend; the catalog's projects.expenditure column is a zeroed legacy
    stamp — never aggregate it.
  • linked_tx_count / first_expenditure_date / latest_expenditure_date —
    count and date span of the linked payments (powers the "no linked
    records vs ₹0 recorded" distinction in the UI)
  • work_key            — the normalized name|constituency|state key, kept
    so consumers can detect multiple catalog rows sharing one work key
  • work_key_expenditure / work_key_rows — the verified work-key payment
    total regardless of uniqueness, and how many catalog rows share the
    key. When work_key_rows > 1 the ledger total CANNOT be split among the
    sharing catalog rows (same generic description, same district, several
    sanctioned works), so per-project spend is AMBIGUOUS: linked_expenditure
    is 0 and the UI reports "shared work — attribution unknown" instead of
    assigning every row the full work total (which would fabricate
    utilization figures of thousands of percent).

UNIQUENESS RULE (data integrity): per-project attribution requires a
one-to-one work-key ↔ catalog-row relationship. Shared keys keep their
verified payment totals at the work level (work_key_expenditure) for state
reconciliation, but never fabricate per-project values.

Linkage (strongest reliable identifier available in this dataset):
  The normalized (name, constituency, state) work key via SQL normkey()
  — the same base key activity.py uses — TIGHTENED with two anchors:
    1. MP match      (normkey(mp_name) equals the recommended work's MP)
    2. IDA match     (the implementing-district-authority prefix, e.g.
      "AMRAVATI(...)" → "amravati", equals the recommended work's IDA)
  Both expenditures and recommended_works carry the IDA field 100%
  populated. The generic constituency values ("Sitting Rajya Sabha",
  "Nominated Rajya Sabha") are shared by every RS/TLS MP of a state, so
  name+constituency+state alone demonstrably cross-matches payments from
  unrelated districts; the IDA anchor removes those false links.

Validation: only expenditures ON/AFTER recommendation_date feed the start
proxy (start_status='valid'). If every linked expenditure predates the
recommendation, the dates are NOT shown as a start (start_status=
'pre_recommendation' → UI shows "Start date unavailable"). Projects with
no linked expenditure are 'no_expenditure'. When no recommended work
matches a project at all, there is no recommendation date to validate
against, so the conservative any-MP earliest expenditure is kept (same
rule as activity._verified_rows) with status 'valid'.

Nothing is invented: dates come from recommended_works.recommendation_date
and expenditures.expenditure_date; the MP comes from recommended_works.
The table is fully derived — rebuild(db) regenerates it after any data
sync. All aggregation runs inside SQLite; peak Python memory stays flat
(no row materialization).
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


def _idapfx_sql(value) -> str:
    """SQL-side IDA prefix: 'AMRAVATI(DISTRICT COLLECTOR AMRAVATI_IDA)' →
    normkey('AMRAVATI'). The prefix (before the parenthetical) is stable
    across the datasets while tolerating punctuation/spacing variants."""
    s = str(value or "").split("(")[0]
    return _normkey(s)


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
        conn.create_function("idapfx", 1, _idapfx_sql, deterministic=True)
        t0 = time.time()
        cur = conn.cursor()
        try:
            # Idempotent schema upgrades for deployments with earlier table
            # shapes (each is a no-op once the column exists).
            for _stmt in (
                "ALTER TABLE project_rec_info ADD COLUMN start_status TEXT",
                "ALTER TABLE project_rec_info ADD COLUMN linked_expenditure REAL",
                "ALTER TABLE project_rec_info ADD COLUMN linked_tx_count INTEGER",
                "ALTER TABLE project_rec_info ADD COLUMN first_expenditure_date TEXT",
                "ALTER TABLE project_rec_info ADD COLUMN latest_expenditure_date TEXT",
                "ALTER TABLE project_rec_info ADD COLUMN work_key TEXT",
                "ALTER TABLE project_rec_info ADD COLUMN work_key_expenditure REAL",
                "ALTER TABLE project_rec_info ADD COLUMN work_key_rows INTEGER",
            ):
                try:
                    cur.execute(_stmt)
                except Exception:
                    pass  # column already exists

            cur.execute("DELETE FROM project_rec_info")
            cur.execute("""
                INSERT INTO project_rec_info
                    (project_id, recommendation_date, recommended_by,
                     approx_start_date, has_expenditure, start_status,
                     linked_expenditure, linked_tx_count,
                     first_expenditure_date, latest_expenditure_date, work_key,
                     work_key_expenditure, work_key_rows)
                WITH
                -- Earliest recommendation per work key (date, MP, IDA)
                rec_agg AS (
                    SELECT dk, ck, sk, rec_date, rec_mp, mpk, idapk FROM (
                        SELECT normkey(rw.work_description)              AS dk,
                               normkey(rw.constituency)                  AS ck,
                               normkey(rw.state)                         AS sk,
                               normdate(rw.recommendation_date)          AS rec_date,
                               TRIM(COALESCE(rw.mp_name, ''))            AS rec_mp,
                               normkey(rw.mp_name)                       AS mpk,
                               idapfx(rw.ida)                            AS idapk,
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
                -- MP+IDA-verified expenditures for recommended work keys:
                -- first_exp    = earliest linked expenditure (any date)
                -- first_valid  = earliest expenditure ON/AFTER the
                --                recommendation date (the only ones usable
                --                as a start proxy)
                exp_verified AS (
                    SELECT ra.dk, ra.ck, ra.sk,
                           MIN(NULLIF(normdate(e.expenditure_date), '')) AS first_exp,
                           MIN(CASE
                                   WHEN ra.rec_date IS NOT NULL AND ra.rec_date <> ''
                                    AND normdate(e.expenditure_date) >= ra.rec_date
                                   THEN normdate(e.expenditure_date)
                               END) AS first_valid,
                           MAX(NULLIF(normdate(e.expenditure_date), '')) AS latest_exp,
                           COUNT(e.id) AS tx_count,
                           SUM(e.expenditure_amount) AS linked_amount
                    FROM expenditures e
                    JOIN rec_agg ra
                      ON ra.dk    = normkey(e.work_description)
                     AND ra.ck    = normkey(e.constituency)
                     AND ra.sk    = normkey(e.state)
                     AND ra.mpk   = normkey(e.mp_name)
                     AND ra.idapk = idapfx(e.ida)
                    GROUP BY ra.dk, ra.ck, ra.sk
                ),
                -- Fallback: earliest expenditure per work key across any
                -- MP/IDA — used ONLY when no recommended work matches the
                -- project key (then there is no rec date to validate
                -- against; same rule as activity._verified_rows).
                exp_any AS (
                    SELECT normkey(e.work_description)  AS dk,
                           normkey(e.constituency)      AS ck,
                           normkey(e.state)             AS sk,
                           MIN(NULLIF(normdate(e.expenditure_date), '')) AS any_first
                    FROM expenditures e
                    GROUP BY dk, ck, sk
                ),
                -- How many catalog rows share each work key: per-project
                -- attribution is only possible when this is exactly 1.
                cat_agg AS (
                    SELECT normkey(project_name) AS dk,
                           normkey(constituency)  AS ck,
                           normkey(state)         AS sk,
                           COUNT(*)               AS nrows
                    FROM projects
                    GROUP BY dk, ck, sk
                )
                SELECT p.id,
                       CASE WHEN ra.rec_date IS NOT NULL AND ra.rec_date <> ''
                            THEN ra.rec_date END,
                       CASE WHEN ra.rec_mp IS NOT NULL AND ra.rec_mp <> ''
                            THEN ra.rec_mp END,
                       CASE
                           -- verified linkage: only valid (>= rec) dates
                           WHEN ra.mpk IS NOT NULL AND ev.first_exp IS NOT NULL
                               THEN ev.first_valid
                           -- no recommendation matched: conservative fallback
                           WHEN ra.mpk IS NULL AND ea.any_first IS NOT NULL
                               THEN ea.any_first
                       END,
                       CASE WHEN (ra.mpk IS NOT NULL AND ev.first_exp IS NOT NULL)
                                 OR (ra.mpk IS NULL AND ea.any_first IS NOT NULL)
                            THEN 1 ELSE 0 END,
                       CASE
                           WHEN ra.mpk IS NOT NULL AND ev.first_exp IS NOT NULL THEN
                               CASE WHEN ev.first_valid IS NOT NULL
                                    THEN 'valid'
                                    ELSE 'pre_recommendation' END
                           WHEN ra.mpk IS NULL AND ea.any_first IS NOT NULL
                               THEN 'valid'
                           ELSE 'no_expenditure'
                       END,
                       -- Attributable spend: only when the work key maps to
                       -- exactly ONE catalog row (uniqueness rule).
                       CASE WHEN ca.nrows = 1
                                 AND ra.mpk IS NOT NULL
                                 AND ev.linked_amount IS NOT NULL
                            THEN ev.linked_amount ELSE 0.0 END,
                       CASE WHEN ra.mpk IS NOT NULL AND ev.tx_count IS NOT NULL
                            THEN ev.tx_count ELSE 0 END,
                       CASE WHEN ra.mpk IS NOT NULL THEN ev.first_exp END,
                       CASE WHEN ra.mpk IS NOT NULL THEN ev.latest_exp END,
                       ra.dk || '|' || ra.ck || '|' || ra.sk,
                       -- Work-level verified total (regardless of uniqueness)
                       -- + how many catalog rows share the key.
                       CASE WHEN ra.mpk IS NOT NULL AND ev.linked_amount IS NOT NULL
                            THEN ev.linked_amount ELSE 0.0 END,
                       COALESCE(ca.nrows, 1)
                FROM projects p
                LEFT JOIN rec_agg ra
                       ON ra.dk = normkey(p.project_name)
                      AND ra.ck = normkey(p.constituency)
                      AND ra.sk = normkey(p.state)
                LEFT JOIN cat_agg ca
                       ON ca.dk = normkey(p.project_name)
                      AND ca.ck = normkey(p.constituency)
                      AND ca.sk = normkey(p.state)
                LEFT JOIN exp_verified ev
                       ON ev.dk = normkey(p.project_name)
                      AND ev.ck = normkey(p.constituency)
                      AND ev.sk = normkey(p.state)
                LEFT JOIN exp_any ea
                       ON ra.mpk IS NULL
                      AND ea.dk = normkey(p.project_name)
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
            linked_sum = cur.execute(
                "SELECT COALESCE(SUM(linked_expenditure), 0) FROM project_rec_info"
            ).fetchone()[0]
            linked_keys = cur.execute(
                "SELECT COUNT(DISTINCT work_key) FROM project_rec_info WHERE linked_tx_count > 0"
            ).fetchone()[0]
            _last_build.update(ok=True, rows=rows, at=time.time(), error=None)
            return {
                "ok": True,
                "rows": rows,
                "with_recommendation_date": dated,
                "with_expenditure": with_exp,
                "linked_expenditure_total": float(linked_sum or 0),
                "linked_work_keys": int(linked_keys),
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
