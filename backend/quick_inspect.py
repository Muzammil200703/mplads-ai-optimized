import sqlite3

conn = sqlite3.connect('mplads.db')
cur = conn.cursor()

print('=== QUICK INSPECTION ===')
print()

# Basic counts
print('Expenditure count:', cur.execute('SELECT COUNT(*) FROM expenditures').fetchone()[0])
print('Project count:', cur.execute('SELECT COUNT(*) FROM projects').fetchone()[0])
print()

# Expenditure amount stats
row = cur.execute('SELECT MIN(expenditure_amount), MAX(expenditure_amount), AVG(expenditure_amount) FROM expenditures').fetchone()
print(f'Expenditure amount stats: Min: {row[0]}, Max: {row[1]}, Avg: {row[2]:.2f}')

pos = cur.execute('SELECT COUNT(*) FROM expenditures WHERE expenditure_amount > 0').fetchone()[0]
total_exp = cur.execute('SELECT COUNT(*) FROM expenditures').fetchone()[0]
print(f'With amount > 0: {pos} out of {total_exp}')

# Top states
print()
print('Top 10 states by expenditure count:')
for r in cur.execute('SELECT state, COUNT(*) FROM expenditures GROUP BY state ORDER BY COUNT(*) DESC LIMIT 10').fetchall():
    print(f'  {r[0]}: {r[1]}')

# Top work descriptions
print()
print('Top 10 work descriptions by count:')
for r in cur.execute('SELECT work_description, COUNT(*) FROM expenditures GROUP BY work_description ORDER BY COUNT(*) DESC LIMIT 10').fetchall():
    desc = r[0]
    cnt = r[1]
    # Truncate if too long
    print(f'  {desc[:80] if len(desc) > 80 else desc}: {cnt}')

# Expenditure dates
print()
print('Expenditures with valid dates:')
valid_dates = cur.execute('SELECT COUNT(*) FROM expenditures WHERE expenditure_date IS NOT NULL AND expenditure_date != ""').fetchone()[0]
print(f'  {valid_dates} out of {total_exp}')

# Sample dates
print()
print('Sample expenditure dates:')
for r in cur.execute('SELECT DISTINCT expenditure_date FROM expenditures WHERE expenditure_date IS NOT NULL AND expenditure_date != "" LIMIT 10').fetchall():
    print(f'  {r[0]}')

# Projects with completion > 0
print()
print('Projects with completion > 0:')
comp_gt0 = cur.execute('SELECT COUNT(*) FROM projects WHERE completion_percentage > 0').fetchone()[0]
print(f'  {comp_gt0} out of 83625')

print()
print('Projects with completion = 100:')
comp_100 = cur.execute('SELECT COUNT(*) FROM projects WHERE completion_percentage = 100').fetchone()[0]
print(f'  {comp_100} out of 83625')

# Check projects with completion > 0 and their rec_info status
print()
print('Sample: projects with completion > 0 and their start_status:')
samples = cur.execute('''
    SELECT p.id, p.project_name, p.completion_percentage,
           r.start_status, r.has_expenditure, r.approx_start_date
    FROM projects p
    LEFT JOIN project_rec_info r ON p.id = r.project_id
    WHERE (p.completion_percentage or 0) > 0
    LIMIT 15
''').fetchall()
for s in samples:
    print(f'  ID {s[0]}: {s[1][:50] if s[1] else "N/A"} | completion={s[2]}% | start_status={s[3]} | has_exp={s[4]} | approx={s[5]}')

# Check Andaman projects
print()
print('Andaman projects (completion and expenditure):')
andaman = cur.execute('''
    SELECT id, project_name, completion_percentage, expenditure, status
    FROM projects
    WHERE state = 'Andaman And Nicobar Islands'
''').fetchall()
for a in andaman:
    print(f'  ID {a[0]}: completion={a[2]}% | expenditure={a[3]} | status={a[4]}')

conn.close()
print()
print('=== DONE ===')