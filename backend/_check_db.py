import sqlite3
c = sqlite3.connect('mplads.db')
cur = c.cursor()
tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("tables:", tables)
print("projects count:", cur.execute("SELECT COUNT(*) FROM projects").fetchone())
try:
    print("risk_scores count:", cur.execute("SELECT COUNT(*) FROM risk_scores").fetchone())
except Exception as e:
    print("risk_scores error:", e)
