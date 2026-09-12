import json, urllib.request, urllib.error

BASE = "http://127.0.0.1:8000"

def call(path, payload=None, method=None, token=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method or ("POST" if data else "GET"))
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try: return e.code, json.loads(body)
        except: return e.code, body

ok = fail = 0
def check(label, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  PASS {label} {extra}")
    else: fail += 1; print(f"  FAIL {label} {extra}")

print("== Signup & roles ==")
s, d = call("/auth/signup", {"name":"System Admin","email":"admin@auditportal.in","password":"Admin#2026secure","role":"auditor"})
check("first user becomes admin", s==201 and d.get("user",{}).get("role")=="admin", f"(status={s} role={d.get('user',{}).get('role') if isinstance(d,dict) else d})")
ADMIN = d.get("token") if isinstance(d, dict) else None
s, d = call("/auth/signup", {"name":"Test Analyst","email":"analyst@auditportal.in","password":"Analyst#2026x","role":"analyst"})
check("analyst signup", s==201 and d.get("user",{}).get("role")=="analyst", f"(status={s})")
ANALYST = d.get("token")
s, d = call("/auth/signup", {"name":"Field Auditor","email":"auditor@auditportal.in","password":"Auditor#2026x","role":"auditor"})
check("auditor signup", s==201 and d.get("user",{}).get("role")=="auditor", f"(status={s})")
AUDITOR = d.get("token")
s, _ = call("/auth/signup", {"name":"Dup","email":"admin@auditportal.in","password":"Whatever#123","role":"analyst"})
check("duplicate email rejected (409)", s==409, f"(status={s})")
s, _ = call("/auth/signup", {"name":"Bad","email":"bad@auditportal.in","password":"short","role":"analyst"})
check("short password rejected (422)", s==422, f"(status={s})")
s, _ = call("/auth/signup", {"name":"Evil","email":"evil@auditportal.in","password":"LongEnough#1","role":"admin"})
check("self-service admin role rejected (422)", s==422, f"(status={s})")

print("== Login & session ==")
s, d = call("/auth/login", {"email":"analyst@auditportal.in","password":"Analyst#2026x"})
check("login ok", s==200 and bool(d.get("token")))
s, _ = call("/auth/login", {"email":"analyst@auditportal.in","password":"wrongpass"})
check("wrong password 401", s==401)
s, d = call("/auth/me", token=ANALYST)
check("GET /auth/me with token", s==200 and isinstance(d,dict) and d.get("email")=="analyst@auditportal.in")
s, _ = call("/auth/me")
check("GET /auth/me without token 401", s==401, f"(status={s})")

print("== Saved projects ==")
s, d = call("/projects?limit=1")
pid = d["projects"][0]["id"] if isinstance(d, dict) and d.get("projects") else (d[0]["id"] if isinstance(d, list) and d else 3)
s, d = call("/auth/me/saved-projects", token=ANALYST)
check("list saved (empty)", s==200 and isinstance(d,dict) and d.get("total")==0)
s, d = call(f"/auth/me/saved-projects/{pid}", method="POST", token=ANALYST)
check("save project", s in (200,201) and isinstance(d,dict) and d.get("saved"))
s, d = call("/auth/me/saved-projects", token=ANALYST)
check("saved shows project with risk data", s==200 and d.get("total")==1 and d["items"][0].get("project_id")==pid and "risk_score" in d["items"][0])
s, d = call("/auth/me/saved-projects", token=AUDITOR)
check("other user cannot see analyst saves", s==200 and d.get("total")==0)
s, _ = call("/auth/me/saved-projects")
check("anonymous saved list 401", s==401)
s, _ = call(f"/auth/me/saved-projects/{pid}", method="POST", token=ADMIN)
check("admin can save too (rank pass)", s in (200,201))
s, _ = call(f"/auth/me/saved-projects/{pid}", method="DELETE", token=ADMIN)
check("admin cleanup own save", s==200)

print("== User investigations ==")
s, d = call(f"/auth/me/investigations/{pid}", method="POST", token=ANALYST)
check("create investigation", s in (200,201) and isinstance(d,dict) and d.get("investigation_status")=="Open", f"(status={s})")
s, d = call("/auth/me/investigations", token=ANALYST)
check("history lists it with priority+recommendations", s==200 and d.get("total")==1 and d["items"][0].get("priority_tier"))
recs = d["items"][0].get("recommendations") if isinstance(d, dict) and d.get("items") else []
check("recommendations generated from real risk reasons", isinstance(recs, list) and len(recs)>0, f"({len(recs)} items)")
s, d = call(f"/auth/me/investigations/{pid}", payload={"status":"Under Review"}, method="PATCH", token=ANALYST)
check("status update", s==200 and d.get("investigation_status")=="Under Review")
s, _ = call(f"/auth/me/investigations/{pid}", payload={"status":"Bogus"}, method="PATCH", token=ANALYST)
check("invalid status 400", s==400)
s, d = call("/auth/me/investigations", token=AUDITOR)
check("other user's history empty for auditor", s==200 and d.get("total")==0)

print("== Audit cases ==")
s, d = call(f"/auth/me/audit-cases/{pid}", method="POST", token=AUDITOR)
check("auditor saves case", s in (200,201) and isinstance(d,dict) and str(d.get("case_id","")).startswith("MPLADS-AUD"), f"(status={s})")
s, d = call("/auth/me/audit-cases", token=AUDITOR)
check("case list shows project+risk+priority", s==200 and d.get("total")==1 and d["items"][0].get("risk_score") is not None)
s, _ = call(f"/auth/me/audit-cases/{pid}", method="POST", token=ANALYST)
check("analyst blocked from cases (403)", s==403, f"(status={s})")
s, _ = call("/auth/me/audit-cases", token=ANALYST)
check("analyst blocked from case list (403)", s==403)
s, d = call(f"/auth/me/audit-cases/{pid}", payload={"status":"Resolved"}, method="PATCH", token=AUDITOR)
check("case status update", s==200 and d.get("case_status")=="Resolved")

print("== Admin ==")
s, d = call("/auth/users", token=ADMIN)
check("admin lists users", s==200 and d.get("total",0)>=3)
s, _ = call("/auth/users", token=ANALYST)
check("analyst blocked from users (403)", s==403)
s, d = call("/auth/admin/investigations", token=ADMIN)
check("admin sees system-wide investigations", s==200 and d.get("total",0)>=1)
s, _ = call("/auth/admin/investigations", token=AUDITOR)
check("auditor blocked from admin view (403)", s==403)
s, d = call("/auth/users", token=ADMIN)
uid = next(u["id"] for u in d["users"] if u["email"]=="analyst@auditportal.in")
s, d = call(f"/auth/users/{uid}", payload={"role":"auditor"}, method="PATCH", token=ADMIN)
check("admin promotes analyst->auditor", s==200 and d.get("role")=="auditor")
s, d = call(f"/auth/users/{uid}", payload={"role":"analyst"}, method="PATCH", token=ADMIN)
check("admin demotes back", s==200 and d.get("role")=="analyst")

print("== Forgot/reset password ==")
s, d = call("/auth/forgot-password", {"email":"analyst@auditportal.in"})
check("forgot returns token (documented no-mail flow)", s==200 and bool(d.get("reset_token")))
RT = d.get("reset_token")
s, d = call("/auth/forgot-password", {"email":"nobody@auditportal.in"})
check("unknown email: same response shape (no enumeration)", s==200 and d.get("reset_token") is None)
s, d = call("/auth/reset-password", {"token": RT, "new_password":"NewPass#2026x"})
check("reset works", s==200)
s, d = call("/auth/login", {"email":"analyst@auditportal.in","password":"NewPass#2026x"})
check("login with new password", s==200)
s, _ = call("/auth/reset-password", {"token": RT, "new_password":"Reuse#2026xx"})
check("token single-use (400 on reuse)", s==400)

print("== Existing public endpoints unaffected ==")
s, d = call("/projects?limit=1")
check("GET /projects still public", s==200)
s, d = call("/dashboard/overview")
check("GET /dashboard/overview still public", s==200)
s, d = call(f"/ai/evidence-gaps/{pid}")
check("evidence gaps still public", s==200)

print()
print(f"RESULT: {ok} passed, {fail} failed")
