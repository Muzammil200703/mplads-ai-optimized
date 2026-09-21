"""Tag ledger rows by source so aggregates can restrict to the snapshot.

- recommended_works LS rows that came from the GitHub provider (work_id IS
  NULL) or were dropped from the current eSAKSHI view (work_id not in the
  2026-09-21 CSV) get source='github_legacy'; snapshot rows get
  source='esakshi'.
- completed_works LS rows not in the CSV get source='github_legacy'.
- RS rows all get source='esakshi' (their current DB partition IS the
  snapshot we hold; no newer RS export has been provided).
Expenditures and mp_summaries are already exactly the snapshot partitions.
Idempotent: re-running re-tags from scratch (all rows reset, then marked).
"""
import csv
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from sqlalchemy import text
from database import SessionLocal

D = r"C:\Users\Admin\Downloads"
REC_CSV = f"{D}\\mplads_recommended_works_2026-09-21.csv"
COMP_CSV = f"{D}\\mplads_completed_works_2026-09-21.csv"

db = SessionLocal()

# 0. Ensure source columns exist (idempotent)
for table in ("recommended_works", "completed_works"):
    cols = [r[1] for r in db.execute(text(f"PRAGMA table_info({table})")).fetchall()]
    if "source" not in cols:
        db.execute(text(f"ALTER TABLE {table} ADD COLUMN source TEXT"))
        db.commit()
        print(f"added source column to {table}")

# 1. Snapshot id sets from the CSVs (source of truth)
csv_rec_ids = set()
with open(REC_CSV, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        try:
            csv_rec_ids.add(int(float(r["Work ID"])))
        except (TypeError, ValueError):
            pass
csv_comp_ids = set()
with open(COMP_CSV, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        try:
            csv_comp_ids.add(int(float(r["Work ID"])))
        except (TypeError, ValueError):
            pass
print("csv snapshot ids — rec:", len(csv_rec_ids), "comp:", len(csv_comp_ids))

# 2. Reset tags, then tag in the correct order:
#    RS: every row is snapshot (their current DB partition IS the snapshot).
#    LS: work_id in the CSV -> esakshi; NULL work_id or dropped id -> legacy.
db.execute(text("UPDATE recommended_works SET source=NULL"))
db.execute(text("UPDATE completed_works SET source=NULL"))
db.commit()

# RS first — blanket esakshi (independent of id membership)
db.execute(text("UPDATE recommended_works SET source='esakshi' WHERE house='Rajya Sabha'"))
db.execute(text("UPDATE completed_works SET source='esakshi' WHERE house='Rajya Sabha'"))
# LS default = legacy, then promote CSV members
db.execute(text("UPDATE recommended_works SET source='github_legacy' WHERE house='Lok Sabha'"))
db.execute(text("UPDATE completed_works SET source='github_legacy' WHERE house='Lok Sabha'"))
db.commit()

CHUNK = 800
rec_ids = sorted(csv_rec_ids)
for i in range(0, len(rec_ids), CHUNK):
    db.execute(text(
        "UPDATE recommended_works SET source='esakshi' "
        f"WHERE house='Lok Sabha' AND work_id IN ({','.join(map(str, rec_ids[i:i+CHUNK]))})"
    ))
db.commit()

comp_ids = sorted(csv_comp_ids)
for i in range(0, len(comp_ids), CHUNK):
    db.execute(text(
        "UPDATE completed_works SET source='esakshi' "
        f"WHERE house='Lok Sabha' AND work_id IN ({','.join(map(str, comp_ids[i:i+CHUNK]))})"
    ))
db.commit()

print("\n== final tag distribution ==")
for t in ("recommended_works", "completed_works"):
    print(t, db.execute(text(f"SELECT source, house, COUNT(*) FROM {t} GROUP BY source, house")).fetchall())

print("\n== snapshot-only aggregates ==")
for label, sql in [
    ("rec esakshi by house", "SELECT house, COUNT(*), ROUND(SUM(recommended_amount)/1e7,2) FROM recommended_works WHERE source='esakshi' GROUP BY house"),
    ("comp esakshi by house", "SELECT house, COUNT(*), ROUND(SUM(final_amount)/1e7,2) FROM completed_works WHERE source='esakshi' GROUP BY house"),
]:
    print(label, db.execute(text(sql)).fetchall())

db.close()
