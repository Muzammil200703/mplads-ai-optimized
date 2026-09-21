"""Create/refresh reference_dashboard_metrics - the official eSAKSHI
dashboard values as backend data (single source of truth for the UI).

RS row: the official eSAKSHI Rajya Sabha dashboard screenshot (2026-09-21),
transcribed verbatim. LS row: derived with the official metric definitions
from the 2026-09-21 eSAKSHI LS CSVs (the same import batch).
Values are stored raw in rupees; nothing is hardcoded in the UI.
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from sqlalchemy import text
from database import SessionLocal

db = SessionLocal()
db.execute(text("""
CREATE TABLE IF NOT EXISTS reference_dashboard_metrics (
    id INTEGER PRIMARY KEY,
    house TEXT UNIQUE NOT NULL,
    source TEXT NOT NULL,
    snapshot_label TEXT NOT NULL,
    total_allocated REAL,
    total_expenditure REAL,
    fund_utilization_percentage REAL,
    expenditure_rate_percentage REAL,
    total_mps INTEGER,
    works_completed INTEGER,
    completed_work_value REAL,
    works_pending INTEGER,
    ongoing_work_payments REAL
)
"""))

# Official eSAKSHI RS dashboard (screenshot, 2026-09-21) - verbatim.
rs = dict(
    house="Rajya Sabha",
    source="Official eSAKSHI dashboard (Rajya Sabha), captured 2026-09-21",
    snapshot_label="Official eSAKSHI snapshot, 21 September 2026",
    total_allocated=3363.8e7,
    total_expenditure=1237.9e7,
    fund_utilization_percentage=66.1,
    expenditure_rate_percentage=36.8,
    total_mps=231,
    works_completed=9927,
    completed_work_value=759.6e7,
    works_pending=15217,
    ongoing_work_payments=478.4e7,
)

# LS: computed from the 2026-09-21 LS CSV batch with the official definitions.
ls = dict(
    house="Lok Sabha",
    source="eSAKSHI Lok Sabha CSV export, 2026-09-21 (imported batch)",
    snapshot_label="eSAKSHI Lok Sabha snapshot, 21 September 2026",
    total_allocated=8318.06e7,
    total_expenditure=2757.41e7,
    fund_utilization_percentage=66.93,
    expenditure_rate_percentage=33.15,
    total_mps=543,
    works_completed=34101,
    completed_work_value=1649.12e7,
    works_pending=37924,
    ongoing_work_payments=1108.29e7,
)

db.execute(text("DELETE FROM reference_dashboard_metrics"))
for row in (rs, ls):
    cols = ", ".join(row)
    ph = ", ".join(f":{k}" for k in row)
    db.execute(text(f"INSERT INTO reference_dashboard_metrics ({cols}) VALUES ({ph})"), row)
db.commit()

for r in db.execute(text("SELECT house, total_allocated/1e7, total_expenditure/1e7, total_mps FROM reference_dashboard_metrics")):
    print(tuple(round(v, 2) if isinstance(v, float) else v for v in r))
db.close()
