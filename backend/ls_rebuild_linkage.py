"""Rebuild project_rec_info from the refreshed (LS + RS) ledgers."""
import sys, time
sys.path.insert(0, ".")
import rec_info
from database import SessionLocal

db = SessionLocal()
t0 = time.time()
res = rec_info.rebuild(db, force=True)
print("rebuild:", res, f"{time.time()-t0:.1f}s")
db.close()
