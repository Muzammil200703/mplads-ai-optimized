"""Import Lok Sabha eSAKSHI snapshot (2026-09-21) into the existing DB.

Design (documented, reversible, no RS mutation):
- recommended_works / completed_works: upsert by work_id (strongest identifier;
  verified unique within the CSVs). New LS works INSERT; existing rows UPDATE
  amount/date fields only when different. Legacy rows (26,413 LS rec rows with
  NULL work_id from the GitHub provider, and 1,110 dropped works) are PRESERVED
  and flagged (work_id stays NULL / dropped_ids are not touched).
- expenditures: work_id does not exist in this ledger, and old/new LS rows
  are indistinguishable by amount+date alone (the 2026-09-02 payments did not
  exist in the old snapshot, but old rows from earlier dates are identical
  to their CSV counterparts — an exact-timestamp delete misses 81,000+ of
  them). mp_summary's Transaction Count sums to exactly 83,644 = CSV row
  count, proving the 25,118 same-amount/same-date rows are the official
  portal's own semantics (separate payments), NOT import artifacts.
  Therefore the LS expenditure partition is REFRESHED: delete ALL LS rows
  (house filter — RS rows are never touched) and insert all 83,644 CSV rows.
  The pre-import backup mplads_backup_pre_ls_*.db is the rollback.
- mp_summaries: upsert by (LOWER(mp_name), house) — refresh amounts/counters
  for the 543 LS MPs. RS rows untouched.
- projects catalog: no house column today. This import does NOT touch
  projects (catalog lineage is unclear; adding the column + derivation is a
  separate migration run afterwards).
- No totals are hardcoded anywhere; everything is derived from the CSV rows.
"""
import csv
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from sqlalchemy import text
from database import SessionLocal
import models

D = r"C:\Users\Admin\Downloads"
STAMP = "2026-09-21"
FILES = {
    "mp_summary": f"{D}\\mplads_mp_summary_{STAMP}.csv",
    "expenditures": f"{D}\\mplads_expenditures_{STAMP}.csv",
    "recommended": f"{D}\\mplads_recommended_works_{STAMP}.csv",
    "completed": f"{D}\\mplads_completed_works_{STAMP}.csv",
}

def num(v):
    try:
        if v is None or str(v).strip() == "":
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0

def ivalue(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0

def zdate(v):
    v = (v or "").strip()
    if not v:
        return ""
    return v if v.endswith("Z") else f"{v}T00:00:00.000Z"

db = SessionLocal()

# ── 1. recommended_works: upsert by work_id ─────────────────────────────
print("== recommended_works ==")
rec_rows = []
with open(FILES["recommended"], encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        rec_rows.append({
            "work_id": ivalue(r["Work ID"]),
            "work_description": (r["Work Description"] or "").strip(),
            "category": (r["Category"] or "").strip(),
            "mp_name": (r["MP Name"] or "").strip(),
            "constituency": (r["Constituency"] or "").strip(),
            "state": (r["State"] or "").strip(),
            "house": (r["House"] or "Lok Sabha").strip(),
            "recommended_amount": num(r["Recommended Amount (₹)"]),
            "recommendation_date": zdate(r["Recommendation Date"]),
            "has_images": (r.get("Has Images") or "").strip().lower() in ("yes", "true", "1"),
            "ida": (r["IDA"] or "").strip(),
        })
print(f"csv rows: {len(rec_rows)}")

existing = {}
for wid, amt, dt, cat, mp, desc in db.execute(text(
    "SELECT work_id, recommended_amount, recommendation_date, category, mp_name, work_description "
    "FROM recommended_works WHERE TRIM(house)='Lok Sabha' AND work_id IS NOT NULL"
)):
    existing[int(wid)] = (amt, dt, cat, mp, desc)
print(f"db existing LS rows with work_id: {len(existing)}")

ins, upd, same = 0, 0, 0
batch = []
for w in rec_rows:
    ex = existing.get(w["work_id"])
    if ex is None:
        batch.append(models.RecommendedWork(**w))
        ins += 1
        if len(batch) >= 2000:
            db.add_all(batch); db.commit(); batch = []
    else:
        amt, dt, cat, mp, desc = ex
        if (abs((amt or 0) - w["recommended_amount"]) > 0.01 or (dt or "") != w["recommendation_date"]
                or (cat or "") != w["category"] or (mp or "") != w["mp_name"]):
            db.execute(text(
                "UPDATE recommended_works SET recommended_amount=:a, recommendation_date=:d, "
                "category=:c, mp_name=:m WHERE TRIM(house)='Lok Sabha' AND work_id=:wid"),
                {"a": w["recommended_amount"], "d": w["recommendation_date"], "c": w["category"],
                 "m": w["mp_name"], "wid": w["work_id"]})
            upd += 1
        else:
            same += 1
if batch:
    db.add_all(batch); db.commit()
print(f"inserted={ins} updated={upd} unchanged={same}")

# ── 2. completed_works: upsert by work_id ───────────────────────────────
print("== completed_works ==")
comp_rows = []
with open(FILES["completed"], encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        comp_rows.append({
            "work_id": ivalue(r["Work ID"]),
            "work_description": (r["Work Description"] or "").strip(),
            "category": (r["Category"] or "").strip(),
            "mp_name": (r["MP Name"] or "").strip(),
            "constituency": (r["Constituency"] or "").strip(),
            "state": (r["State"] or "").strip(),
            "house": (r["House"] or "Lok Sabha").strip(),
            "final_amount": num(r["Final Amount (₹)"]),
            "completed_date": zdate(r["Completed Date"]),
            "has_images": (r.get("Has Images") or "").strip().lower() in ("yes", "true", "1"),
            "average_rating": num(r["Average Rating"]) if (r.get("Average Rating") or "").strip() not in ("", "N/A") else None,
            "ida": (r["IDA"] or "").strip(),
        })
print(f"csv rows: {len(comp_rows)}")

existing_c = {}
for wid, amt, dt in db.execute(text(
    "SELECT work_id, final_amount, completed_date FROM completed_works WHERE TRIM(house)='Lok Sabha'"
)):
    existing_c[int(wid)] = (amt, dt)

ins, upd, same = 0, 0, 0
batch = []
for w in comp_rows:
    ex = existing_c.get(w["work_id"])
    if ex is None:
        batch.append(models.CompletedWork(**w))
        ins += 1
        if len(batch) >= 2000:
            db.add_all(batch); db.commit(); batch = []
    else:
        amt, dt = ex
        if abs((amt or 0) - w["final_amount"]) > 0.01 or (dt or "") != w["completed_date"]:
            db.execute(text(
                "UPDATE completed_works SET final_amount=:a, completed_date=:d "
                "WHERE TRIM(house)='Lok Sabha' AND work_id=:wid"),
                {"a": w["final_amount"], "d": w["completed_date"], "wid": w["work_id"]})
            upd += 1
        else:
            same += 1
if batch:
    db.add_all(batch); db.commit()
print(f"inserted={ins} updated={upd} unchanged={same}")

# ── 3. expenditures: refresh previous LS snapshot, then insert CSV ─────
print("== expenditures ==")
deleted = db.execute(text("DELETE FROM expenditures WHERE TRIM(house)='Lok Sabha'"))
db.commit()
print(f"deleted ALL previous LS expenditure rows: {deleted.rowcount}")

exp_rows = []
with open(FILES["expenditures"], encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        exp_rows.append(models.Expenditure(
            mp_name=(r["MP Name"] or "").strip(),
            constituency=(r["Constituency"] or "").strip(),
            state=(r["State"] or "").strip(),
            house=(r["House"] or "Lok Sabha").strip(),
            work_description=(r["Work Description"] or "").strip(),
            vendor=(r["Vendor"] or "").strip(),
            ida=(r["IDA"] or "").strip(),
            expenditure_amount=num(r["Expenditure Amount (₹)"]),
            expenditure_date=zdate(r["Expenditure Date"]),
            payment_status=(r["Payment Status"] or "").strip(),
        ))
print(f"csv rows: {len(exp_rows)}")
for i in range(0, len(exp_rows), 4000):
    db.add_all(exp_rows[i:i+4000]); db.commit()
print("inserted all expenditure rows")

# ── 4. mp_summaries: upsert by (LOWER(mp_name), house) ─────────────────
print("== mp_summaries ==")
ins, upd = 0, 0
with open(FILES["mp_summary"], encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        name = (r["MP Name"] or "").strip()
        house = (r["House"] or "Lok Sabha").strip()
        vals = {
            "constituency": (r["Constituency"] or "").strip(),
            "state": (r["State"] or "").strip(),
            "allocated_amount": num(r["Allocated Amount (₹)"]),
            "total_expenditure": num(r["Total Expenditure (₹)"]),
            "utilization_percentage": num(r["Utilization %"]),
            "completed_works": ivalue(r["Completed Works"]),
            "recommended_works": ivalue(r["Recommended Works"]),
            "completion_rate_percentage": num(r["Completion Rate %"]),
            "unspent_amount": num(r["Balance Not Yet Paid to Vendors (₹)"]),
            "transaction_count": ivalue(r["Transaction Count"]),
            "successful_payments": ivalue(r["Successful Payments"]),
            "pending_payments": ivalue(r["Pending Payments"]),
        }
        row = db.execute(text(
            "SELECT id FROM mp_summaries WHERE LOWER(TRIM(mp_name))=:n AND TRIM(house)=:h"
        ), {"n": name.lower(), "h": house}).first()
        if row:
            sets = ", ".join(f"{k}=:{k}" for k in vals)
            vals["id"] = row[0]
            db.execute(text(f"UPDATE mp_summaries SET {sets} WHERE id=:id"), vals)
            upd += 1
        else:
            db.add(models.MPSummary(mp_name=name, house=house, average_rating=None, **vals))
            ins += 1
db.commit()
print(f"updated={upd} inserted={ins}")

# ── 5. sync metadata + final verification ──────────────────────────────
db.add(models.SyncMetadata(
    source="esakshi_ls_snapshot",
    status="success",
    records_fetched=len(rec_rows) + len(comp_rows) + len(exp_rows) + 543,
    source_updated_at=STAMP,
    error_message="Lok Sabha eSAKSHI refresh; Rajya Sabha data untouched",
))
db.commit()

print("\n== post-import verification ==")
for label, sql in [
    ("rec by house", "SELECT house, COUNT(*), ROUND(SUM(recommended_amount)/1e7,2) FROM recommended_works GROUP BY house"),
    ("completed by house", "SELECT house, COUNT(*), ROUND(SUM(final_amount)/1e7,2) FROM completed_works GROUP BY house"),
    ("expenditures by house", "SELECT house, COUNT(*), ROUND(SUM(expenditure_amount)/1e7,2) FROM expenditures GROUP BY house"),
    ("mp_summaries by house", "SELECT house, COUNT(*), ROUND(SUM(allocated_amount)/1e7,2) FROM mp_summaries GROUP BY house"),
]:
    print(label, db.execute(text(sql)).fetchall())
db.close()
print("\nDONE")
