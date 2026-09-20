import sqlite3

conn = sqlite3.connect('mplads.db')
cur = conn.cursor()

print('=== project_rec_info TABLE ANALYSIS ===')
print()

# Check start_status distribution
print('start_status distribution:')
statuses = cur.execute('SELECT start_status, COUNT(*) FROM project_rec_info GROUP BY start_status').fetchall()
for s in statuses:
    print(f'  {s[0]}: {s[1]}')

print()
print('has_expenditure distribution:')
he = cur.execute('SELECT has_expenditure, COUNT(*) FROM project_rec_info GROUP BY has_expenditure').fetchall()
for h in he:
    print(f'  has_expenditure={h[0]}: {h[1]}')

print()
print('approx_start_date NULL count:')
null_cnt = cur.execute('SELECT COUNT(*) FROM project_rec_info WHERE approx_start_date IS NULL OR approx_start_date = ""').fetchone()[0]
total = cur.execute('SELECT COUNT(*) FROM project_rec_info').fetchone()[0]
print(f'  NULL/empty: {null_cnt} out of {total}')

print()
print('recommendation_date NULL count:')
rec_null = cur.execute('SELECT COUNT(*) FROM project_rec_info WHERE recommendation_date IS NULL OR recommendation_date = ""').fetchone()[0]
print(f'  NULL/empty: {rec_null} out of {total}')

print()
print('Sample rows from project_rec_info:')
samples = cur.execute('''
    SELECT project_id, recommendation_date, recommended_by, approx_start_date, has_expenditure, start_status
    FROM project_rec_info
    LIMIT 20
''').fetchall()
for s in samples:
    print(f'  ID {s[0]}: rec_date={s[1]}, MP={s[2]}, approx_date={s[3]}, has_exp={s[4]}, start_status={s[5]}')

print()
print('Projects with start_status = valid:')
valid = cur.execute('''
    SELECT project_id, approx_start_date, recommended_by
    FROM project_rec_info
    WHERE start_status = 'valid'
    LIMIT 10
''').fetchall()
for v in valid:
    print(f'  ID {v[0]}: approx_date={v[1]}, MP={v[2]}')

print()
print('Projects with start_status = pre_recommendation:')
pre = cur.execute('''
    SELECT project_id, approx_start_date, recommended_by
    FROM project_rec_info
    WHERE start_status = 'pre_recommendation'
    LIMIT 10
''').fetchall()
for p in pre:
    print(f'  ID {p[0]}: approx_date={p[1]}, MP={p[2]}')

print()
print('Projects with start_status = no_expenditure:')
ne = cur.execute('''
    SELECT project_id, approx_start_date, recommended_by
    FROM project_rec_info
    WHERE start_status = 'no_expenditure'
    LIMIT 10
''').fetchall()
for n in ne:
    print(f'  ID {n[0]}: approx_date={n[1]}, MP={n[2]}')

# Check if start_status has numeric values mixed in
print()
print('Checking for numeric start_status values:')
numeric = cur.execute("SELECT start_status FROM project_rec_info WHERE start_status GLOB '[0-9]*'").fetchall()
print(f'  Rows with numeric start_status: {len(numeric)}')
if numeric:
    print(f'  Examples: {numeric[:5]}')

# Check start_status that are NOT the expected values
print()
print('start_status values that are NOT valid/pre_recommendation/no_expenditure:')
other = cur.execute("SELECT DISTINCT start_status FROM project_rec_info WHERE start_status NOT IN ('valid', 'pre_recommendation', 'no_expenditure')").fetchall()
print(f'  Unusual start_status values: {other}')
if other:
    for o in other[:10]:
        count = cur.execute(f"SELECT COUNT(*) FROM project_rec_info WHERE start_status = '{o[0]}'").fetchone()[0]
        print(f'    "{o[0]}": {count} rows')

# Check project IDs that have rec_info vs projects table
print()
print('Project-RecInfo match coverage:')
proj_count = cur.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
rec_count = cur.execute('SELECT COUNT(*) FROM project_rec_info').fetchone()[0]
print(f'  Projects: {proj_count}, RecInfo: {rec_count}')
matched = cur.execute('''
    SELECT COUNT(DISTINCT p.id) FROM projects p
    JOIN project_rec_info r ON p.id = r.project_id
''').fetchone()[0]
print(f'  Projects with rec_info match: {matched}')

# Check for projects where completion > 0 but start_status = no_expenditure 
print()
print('Projects with completion > 0 and start_status = no_expenditure:')
comp_gt0_ne = cur.execute('''
    SELECT p.id, p.project_name, p.completion_percentage,
           r.start_status, r.has_expenditure, r.approx_start_date
    FROM projects p
    JOIN project_rec_info r ON p.id = r.project_id
    WHERE (p.completion_percentage or 0) > 0
    AND r.start_status = 'no_expenditure'
    LIMIT 10
''').fetchall()
for c in comp_gt0_ne:
    print(f'  ID {c[0]}: {c[1]} | completion={c[2]}% | start_status={c[3]} | has_expenditure={c[4]} | approx={c[5]}')

# Check for projects where completion = 0 and start_status should be no_expenditure
print()
print('Projects with completion = 0 and start_status = no_expenditure:')
comp0_ne = cur.execute('''
    SELECT p.id, p.project_name, p.completion_percentage,
           r.start_status, r.has_expenditure, r.approx_start_date
    FROM projects p
    JOIN project_rec_info r ON p.id = r.project_id
    WHERE (p.completion_percentage or 0) = 0
    AND r.start_status = 'no_expenditure'
    LIMIT 10
''').fetchall()
for c in comp0_ne:
    print(f'  ID {c[0]}: {c[1]} | completion={c[2]}% | start_status={c[3]} | has_expenditure={c[4]} | approx={c[5]}')

conn.close()
print()
print('=== END project_rec_info ANALYSIS ===')