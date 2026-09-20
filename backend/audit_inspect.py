import sqlite3

conn = sqlite3.connect('mplads.db')
cur = conn.cursor()

print('=== DATABASE INSPECTION REPORT ===')
print()

# Basic counts
count = cur.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
print(f'Total projects: {count}')

# NULL/invalid conditions
null_checks = {
    'completion_percentage IS NULL': cur.execute('SELECT COUNT(*) FROM projects WHERE completion_percentage IS NULL').fetchone()[0],
    'completion_percentage > 100': cur.execute('SELECT COUNT(*) FROM projects WHERE completion_percentage > 100').fetchone()[0],
    'completion_percentage < 0': cur.execute('SELECT COUNT(*) FROM projects WHERE completion_percentage < 0').fetchone()[0],
    'sanctioned_amount IS NULL': cur.execute('SELECT COUNT(*) FROM projects WHERE sanctioned_amount IS NULL').fetchone()[0],
    'sanctioned_amount < 0': cur.execute('SELECT COUNT(*) FROM projects WHERE sanctioned_amount < 0').fetchone()[0],
    'expenditure IS NULL': cur.execute('SELECT COUNT(*) FROM projects WHERE expenditure IS NULL').fetchone()[0],
    'expenditure < 0': cur.execute('SELECT COUNT(*) FROM projects WHERE expenditure < 0').fetchone()[0],
}

print('NULL/INVALID CONDITIONS:')
for check, val in null_checks.items():
    print(f'  {check}: {val}')

# Status distribution
print()
statuses = cur.execute('SELECT status, COUNT(*) FROM projects GROUP BY status').fetchall()
print('STATUS DISTRIBUTION:')
for s in statuses:
    print(f'  {s[0]}: {s[1]}')

# FY distribution
print()
fys = cur.execute('SELECT fy, COUNT(*) FROM projects WHERE fy IS NOT NULL AND fy != "" GROUP BY fy').fetchall()
print('FY DISTRIBUTION:')
for f in fys:
    print(f'  {f[0]}: {f[1]}')

# Projects with expenditure > sanctioned
print()
over_sanctioned = cur.execute('''
    SELECT p.id, p.project_name, p.state, p.sanctioned_amount, p.expenditure, p.completion_percentage, p.status
    FROM projects p
    WHERE p.sanctioned_amount > 0 AND (p.expenditure or 0) > p.sanctioned_amount
    LIMIT 10
''').fetchall()
print(f'Projects with expenditure > sanctioned (top 10):')
for o in over_sanctioned:
    print(f'  ID {o[0]}: {o[1]} | {o[2]} | sanctioned={o[3]} | expenditure={o[4]} | completion={o[5]}% | status={o[6]}')

# Projects with 0 completion but >0 expenditure
print()
zero_comp_expend = cur.execute('''
    SELECT p.id, p.project_name, p.state, p.sanctioned_amount, p.expenditure, p.completion_percentage, p.status
    FROM projects p
    WHERE p.completion_percentage = 0 AND (p.expenditure or 0) > 0
    LIMIT 10
''').fetchall()
print(f'Projects with 0% completion but expenditure > 0 (top 10):')
for z in zero_comp_expend:
    print(f'  ID {z[0]}: {z[1]} | {z[2]} | sanctioned={z[3]} | expenditure={z[4]} | completion={z[5]}% | status={z[6]}')

# Projects with completion > 0 and status containing "not yet"
print()
print('Projects with completion > 0% and status containing "not yet":')
not_started = cur.execute('''
    SELECT p.id, p.project_name, p.state, p.sanctioned_amount, p.expenditure, p.completion_percentage, p.status
    FROM projects p
    WHERE (p.completion_percentage or 0) > 0 
    AND LOWER(p.status) LIKE '%not yet%'
    LIMIT 10
''').fetchall()
for n in not_started:
    print(f'  ID {n[0]}: {n[1]} | completion={n[5]}% | status={n[6]}')

# Check rec_info status vs completion
print()
print('Checking rec_info start_status vs completion percentage:')
rec_info = cur.execute('''
    SELECT p.id, p.project_name, p.state, p.completion_percentage,
           r.start_status, r.has_expenditure, r.approx_start_date
    FROM projects p
    LEFT JOIN project_rec_info r ON p.id = r.project_id
    WHERE (p.completion_percentage or 0) > 0
    LIMIT 20
''').fetchall()
for r in rec_info:
    print(f'  ID {r[0]}: {r[1]} | completion={r[2]}% | start_status={r[3]} | has_expenditure={r[4]} | approx_date={r[5]}')

# Check for projects where physical completion > 0 but start_status = no_expenditure
print()
print('Projects with completion > 0 AND start_status = no_expenditure:')
comp_no_exp = cur.execute('''
    SELECT p.id, p.project_name, p.state, p.completion_percentage,
           r.start_status, r.has_expenditure
    FROM projects p
    LEFT JOIN project_rec_info r ON p.id = r.project_id
    WHERE (p.completion_percentage or 0) > 0
    AND r.start_status = 'no_expenditure'
    LIMIT 10
''').fetchall()
for c in comp_no_exp:
    print(f'  ID {c[0]}: {c[1]} | completion={c[2]}% | start_status={c[3]} | has_expenditure={c[4]}')

# Check for projects with 0 completion and expenditure
print()
print('Projects with completion = 0 AND start_status = no_expenditure:')
comp0_no_exp = cur.execute('''
    SELECT p.id, p.project_name, p.state, p.completion_percentage,
           r.start_status, r.has_expenditure
    FROM projects p
    LEFT JOIN project_rec_info r ON p.id = r.project_id
    WHERE (p.completion_percentage or 0) = 0
    AND r.start_status = 'no_expenditure'
    LIMIT 10
''').fetchall()
for c in comp0_no_exp:
    print(f'  ID {c[0]}: {c[1]} | completion={c[2]}% | start_status={c[3]} | has_expenditure={c[4]}')

# Check expenditure/sanctioned relationship
print()
print('Expenditure/Sanctioned analysis:')
sanctioned_nonzero = cur.execute('SELECT COUNT(*) FROM projects WHERE sanctioned_amount > 0').fetchone()[0]
expend_nonzero = cur.execute('SELECT COUNT(*) FROM projects WHERE (expenditure or 0) > 0').fetchone()[0]
both_nonzero = cur.execute('''
    SELECT COUNT(*) FROM projects 
    WHERE sanctioned_amount > 0 AND (expenditure or 0) > 0
''').fetchone()[0]
print(f'  Projects with sanctioned > 0: {sanctioned_nonzero}')
print(f'  Projects with expenditure > 0: {expend_nonzero}')
print(f'  Projects with both > 0: {both_nonzero}')
if sanctioned_nonzero > 0:
    util = (both_nonzero / sanctioned_nonzero) * 100
    print(f'  Utilization rate (both > 0): {util:.1f}%')

# Check project name / work description matching
print()
print('Sample projects with their matching expenditures:')
sample = cur.execute('''
    SELECT p.id, p.project_name, p.state, p.constituency,
           e.id, e.work_description, e.expenditure_amount, e.expenditure_date
    FROM projects p
    LEFT JOIN expenditures e 
      ON lower(trim(e.work_description)) = lower(trim(p.project_name))
     AND COALESCE(lower(trim(e.constituency)), '') = COALESCE(lower(trim(p.constituency)), '')
     AND COALESCE(lower(trim(e.state)), '') = COALESCE(lower(trim(p.state)), '')
    LIMIT 5
''').fetchall()
for s in sample:
    print(f'  Project {s[0]}: {s[1]} | {s[2]} | {s[3]}')
    print(f'    Matching expenditure: {s[4]} | {s[5]} | amount={s[6]} | date={s[7]}')

# Check for duplicate work descriptions
print()
print('Projects sharing same work description + constituency + state:')
dups = cur.execute('''
    SELECT project_name, constituency, state, COUNT(*) as cnt
    FROM projects
    GROUP BY project_name, constituency, state
    HAVING COUNT(*) > 1
    LIMIT 10
''').fetchall()
for d in dups:
    print(f'  {d[0]} | {d[1]} | {d[2]}: {d[3]} projects')

conn.close()
print()
print('=== END DATABASE INSPECTION ===')