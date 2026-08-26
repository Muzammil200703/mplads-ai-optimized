"""Patch generate_risk_scores.py to use INSERT OR REPLACE"""
with open('ml/generate_risk_scores.py', 'r') as f:
    content = f.read()

old_block = """        print("Writing risk scores to database...")
        batch_size = 5000
        rows = df[["id", "ml_anomaly", "ml_score", "risk_score", "risk_level", "reasons"]].values.tolist()

        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            objs = [
                RiskScore(
                    project_id=int(r[0]),
                    ml_anomaly=bool(r[1]),
                    ml_score=float(r[2]),
                    risk_score=int(r[3]),
                    risk_level=str(r[4]),
                    reasons=str(r[5]),
                )
                for r in batch
            ]
            db.bulk_save_objects(objs)
            db.commit()
            print(f"  Written {min(start + batch_size, len(rows))}/{len(rows)}")"""

new_block = """        print("Writing risk scores to database...")
        batch_size = 5000
        rows = df[["id", "ml_anomaly", "ml_score", "risk_score", "risk_level", "reasons"]].values.tolist()

        import sqlite3 as _sqlite3
        db_url = str(db.get_bind().url.database)
        conn = _sqlite3.connect(db_url)
        cur = conn.cursor()
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            cur.executemany(
                "INSERT OR REPLACE INTO risk_scores (project_id, ml_anomaly, ml_score, risk_score, risk_level, reasons) VALUES (?, ?, ?, ?, ?, ?)",
                [(int(r[0]), bool(r[1]), float(r[2]), int(r[3]), str(r[4]), str(r[5])) for r in batch]
            )
            conn.commit()
            print(f"  Written {min(start + batch_size, len(rows))}/{len(rows)}")
        conn.close()"""

content = content.replace(old_block, new_block)
with open('ml/generate_risk_scores.py', 'w') as f:
    f.write(content)
print("Patched successfully")
