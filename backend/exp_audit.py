import sqlite3

conn = sqlite3.connect('mplads.db')
cur = conn.cursor()

print('=== EXPENDITURES TABLE ANALYSIS ===')
print()

# Basic counts
exp_count = cur.execute('SELECT COUNT(*) FROM expenditures').fetchone()[0]
print(f'Total expenditure records: {exp_count}')

# Expenditure by state
print()
print('Expenditures by state:')
state_exp = cur.execute('''
    SELECT e.state, COUNT(*) 
    FROM expenditures e
    GROUP BY e.state
    ORDER BY COUNT(*) DESC
''').fetchall()
for s in state_exp:
    print(f'  {s[0]}: {s[1]}')

# Expenditure by work description (top)
print()
print('Top work descriptions in expenditures:')
work_desc = cur.execute('''
    SELECT work_description, COUNT(*) as cnt
    FROM expenditures
    GROUP BY work_description
    ORDER BY cnt DESC
    LIMIT 15
''').fetchall()
for w in work_desc:
    print(f'  {w[0]}: {w[1]}')

# Expenditure amounts
print()
print('Expenditure amounts:')
amount_stats = cur.execute('''
    SELECT MIN(expenditure_amount), MAX(expenditure_amount), 
           AVG(expenditure_amount), SUM(expenditure_amount)
    FROM expenditures
''').fetchone()
print(f'  Min: {amount_stats[0]}')
print(f'  Max: {amount_stats[1]}')
print(f'  Avg: {amount_stats[2]:.2f}')
print(f'  Total: {amount_stats[3]:.2f}')

# Check expenditure matching to projects
print()
print('Expenditures matching projects by (work_description, constituency, state):')
matched = cur.execute('''
    SELECT COUNT(DISTINCT e.id) 
    FROM expenditures e
    WHERE EXISTS (
        SELECT 1 FROM projects p 
        WHERE lower(trim(e.work_description)) = lower(trim(p.project_name))
        AND COALESCE(lower(trim(e.constituency)), '') = COALESCE(lower(trim(p.constituency)), '')
        AND COALESCE(lower(trim(e.state)), '') = COALESCE(lower(trim(p.state)), '')
    )
''').fetchone()[0]
print(f'  Expenditures matching projects by name/constituency/state: {matched}')

# Check by normalized key
print()
print('Sample expenditure-to-project matches:')
samples = cur.execute('''
    SELECT e.id, e.work_description, e.expenditure_amount, e.expenditure_date,
           e.mp_name, e.constituency, e.state,
           p.id as project_id, p.project_name, p.state as proj_state, p.completion_percentage
    FROM expenditures e
    JOIN projects p 
      ON lower(trim(e.work_description)) = lower(trim(p.project_name))
     AND COALESCE(lower(trim(e.constituency)), '') = COALESCE(lower(trim(p.constituency)), '')
     AND COALESCE(lower(trim(e.state)), '') = COALESCE(lower(trim(p.state)), '')
    LIMIT 10
''').fetchall()
for s in samples:
    print(f'  Expenditure {s[0]}: {s[1]} | amount={s[2]} | date={s[3]} | MP={s[4]} | {s[5]} | {s[6]}')
    print(f'    -> Project {s[7]}: {s[8]} | {s[9]} | completion={s[10]}%')

# Check how many projects have matching expenditures
print()
print('Projects with at least one matching expenditure (by name/const/state):')
proj_with_exp = cur.execute('''
    SELECT COUNT(DISTINCT p.id) 
    FROM projects p
    WHERE EXISTS (
        SELECT 1 FROM expenditures e 
        WHERE lower(trim(e.work_description)) = lower(trim(p.project_name))
        AND COALESCE(lower(trim(e.constituency)), '') = COALESCE(lower(trim(p.constituency)), '')
        AND COALESCE(lower(trim(e.state)), '') = COALESCE(lower(trim(p.state)), '')
    )
''').fetchone()[0]
print(f'  {proj_with_exp} out of {cur.execute("SELECT COUNT(*) FROM projects").fetchone()[0]}')

# Check the Andaman projects specifically (they had 0 completion but no expenditure)
print()
print('Andaman And Nicobar projects:')
andaman = cur.execute('''
    SELECT id, project_name, state, completion_percentage, expenditure, status
    FROM projects
    WHERE state = 'Andaman And Nicobar Islands'
    LIMIT 20
''').fetchall()
for a in andaman:
    print(f'  ID {a[0]}: {a[1]} | completion={a[3]}% | expenditure={a[4]} | status={a[5]}')

# Check if Andaman projects have expenditures
print()
print('Expenditures in Andaman And Nicobar Islands:')
an_exp = cur.execute('''
    SELECT COUNT(*) FROM expenditures WHERE state = 'Andaman And Nicobar Islands'
''').fetchone()[0]
print(f'  {an_exp} expenditure records')

# Check work descriptions in Andaman
print()
print('Work descriptions in Andaman expenditures:')
an_work = cur.execute('''
    SELECT work_description, COUNT(*) as cnt
    FROM expenditures
    WHERE state = 'Andaman And Nicobar Islands'
    GROUP BY work_description
    ORDER BY cnt DESC
''').fetchall()
for w in an_work[:10]:
    print(f'  {w[0]}: {w[1]}')

# Check the duplicate work descriptions phenomenon
print()
print('Most common work descriptions overall:')
common_work = cur.execute('''
    SELECT work_description, COUNT(*) as cnt
    FROM projects
    GROUP BY work_description
    ORDER BY cnt DESC
    LIMIT 15
''').fetchall()
for w in common_work:
    print(f'  {w[0]}: {w[1]} projects')

conn.close()
print()
print('=== END EXPENDITURES ANALYSIS ===')