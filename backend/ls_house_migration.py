"""Migration: add projects.house and derive it from recommended_works.

Derivation rule (documented): a catalog row gets the house of the
recommended_works rows whose normalized work_description equals the catalog's
project_name — but ONLY when those rows agree on a single house. Rows whose
name matches works of BOTH houses (or no works at all) stay NULL = unknown;
aggregations treat NULL as "unattributed", never as a guessed house.
"""
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import sqlite3

c = sqlite3.connect("mplads.db")
cols = [r[1] for r in c.execute("PRAGMA table_info(projects)")]
if "house" not in cols:
    c.execute("ALTER TABLE projects ADD COLUMN house TEXT")
    print("column added")

c.execute("CREATE TEMP TABLE namehouse(name TEXT, house TEXT)")
c.executemany(
    "INSERT INTO namehouse VALUES (?,?)",
    c.execute("SELECT DISTINCT TRIM(work_description), TRIM(house) FROM recommended_works WHERE TRIM(work_description) != ''").fetchall(),
)
c.execute("CREATE INDEX ix_nh ON namehouse(name)")

updated = c.execute("""
UPDATE projects SET house = (
    SELECT MIN(house) FROM namehouse WHERE name = TRIM(projects.project_name)
)
WHERE house IS NULL
  AND EXISTS (SELECT 1 FROM namehouse WHERE name = TRIM(projects.project_name))
  AND NOT EXISTS (
    SELECT 1 FROM namehouse nh1 WHERE name = TRIM(projects.project_name)
      AND EXISTS (SELECT 1 FROM namehouse nh2 WHERE nh2.name = nh1.name AND nh2.house != nh1.house)
  )
""").rowcount
c.commit()
print(f"rows attributed: {updated}")

for r in c.execute("SELECT COALESCE(NULLIF(TRIM(house),''),'(unattributed)'), COUNT(*) FROM projects GROUP BY 1"):
    print(r)
n = c.execute("SELECT COUNT(*) FROM projects p WHERE NOT EXISTS (SELECT 1 FROM namehouse WHERE name=TRIM(p.project_name))").fetchone()[0]
print(f"rows with NO name match at all: {n}")
c.close()
