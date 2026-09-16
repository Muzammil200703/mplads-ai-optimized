"""
MPLADS AI Assistant engine
==========================

A deterministic, role-aware question router — NOT a generative LLM. Every
answer is either:

  1. Static knowledge-base guidance (general MPLADS / website help), or
  2. Composed from REAL database query results (SQL with LIMITs).

Nothing is invented: if no intent matches or data is missing, the assistant
says so. Role enforcement happens here on the server — the same
auth.require_* machinery the rest of the app uses — so a citizen can never
pull audit data regardless of what they type.

Memory discipline (512MB Render): every query is aggregated or LIMIT-ed;
nothing is cached beyond FastAPI's existing bounded cache; no pandas.
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import auth
import models

router = APIRouter(prefix="/assistant", tags=["AI Assistant"])

_bearer = HTTPBearer(auto_error=False)


def get_db():
    from database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    """Best-effort identity — the assistant works for guests too. A valid
    token attaches the user so role-gated intents can unlock."""
    if credentials is None or not credentials.credentials:
        return None
    uid = auth._decode_token(credentials.credentials)
    if uid is None:
        return None
    return db.query(models.User).filter(models.User.id == uid, models.User.is_active.is_(True)).first()


# ═══════════════════════════════════════════════════════════════════
# Constants / knowledge base
# ═══════════════════════════════════════════════════════════════════

TIER_MEANING = {
    "P1": "P1 — Critical: investigate immediately (highest risk score, biggest financial exposure, strongest audit flags).",
    "P2": "P2 — High: schedule review this week (strong risk indicators or large funds at stake).",
    "P3": "P3 — Medium: routine monitoring (some indicators present).",
    "P4": "P4 — Low: healthy-looking on current data (few or weak indicators).",
}

KNOWLEDGE = [
    # (patterns, answer_key) — answer keys resolved against _knowledge_answer()
    (r"what\s+is\s+mplads|mplads\s+mean|about\s+mplads", "what_is_mplads"),
    (r"purpose\s+of\s+(this\s+)?(website|site|app|platform)|what\s+(does|can)\s+(this|the)\s+(site|website|app)\s+do", "purpose"),
    (r"what\s+can\s+i\s+do|how\s+(does|do)\s+(this|the)\s+(site|website|app)\s+work|sections?\s+of\s+(the\s+)?(website|app)", "sections"),
    (r"how\s+(does|do)\s+mplads\s+work|mplads\s+fund|who\s+funds", "how_mplads_works"),
    (r"ground\s+(truth\s+)?verif", "ground_verification"),
    (r"(submit|upload|report).{0,30}(evidence|photo|project)|how\s+can\s+i\s+report", "submit_evidence"),
    (r"what\s+happens?\s+after\s+i\s+(submit|upload)", "after_submit"),
    (r"who\s+verif", "who_verifies"),
    (r"what\s+is\s+(a\s+)?risk\s+score|risk\s+score\s+mean|risk\s+level", "risk_score"),
    (r"\bp[1-4]\b.{0,20}(mean|priority)|what\s+does\s+p[1-4]|priority\s+tier", "priority_tiers"),
    (r"what\s+is\s+vendor\s+intelligence|vendor\s+intelligence", "vendor_intelligence"),
    (r"what\s+is\s+vendor\s+network|vendor\s+network", "vendor_network"),
    (r"what\s+is\s+ai\s+audit|audit\s+command\s+center|ai\s+audit\s+center", "ai_audit"),
    (r"what\s+happens?.{0,20}inquiry|inquiry\s+work|what\s+is\s+an?\s+inquiry", "inquiry_flow"),
    (r"search\s+for\s+a\s+project|how\s+do\s+i\s+search|find\s+a\s+project|how\s+to\s+filter|use\s+the\s+filters?", "search_help"),
    (r"citizen\s+evidence|evidence\s+submission", "citizen_evidence"),
    # ── Upgrade additions: status vocabulary, reporting, verifying ──
    (r"what\s+(do|does)\s+(the\s+)?status.{0,20}(mean)|what\s+does\s+ongoing|status\s+mean|project\s+statuses?", "status_meanings"),
    (r"report\s+an\s+issue|report\s+a\s+problem|something\s+wrong|report\s+incorrect|report\s+corrupt", "report_issue"),
    (r"how\s+(do|can)\s+i\s+verify\s+a\s+project|verify\s+a\s+project|check\s+a\s+project\s+on?\s*the\s+ground", "verify_project"),
    (r"why\s+is\s+gps|why\s+location|do\s+i\s+need\s+(to\s+)?(share\s+)?gps", "why_gps"),
    (r"what\s+(does|do)\s+.{0,12}(flagged|flag)\s+mean|flagged\s+for\s+review", "flagged_meaning"),
    (r"what\s+does\s+(high|medium|low)\s+risk\s+mean|high\s+risk\s+mean", "risk_levels_meaning"),
    (r"what\s+is\s+audit\s+priority", "priority_tiers"),
    (r"what\s+is\s+(a\s+)?project\?*$|^what\s+is\s+a\s+project", "what_is_project"),
]

KNOWLEDGE_ANSWERS = {
    "what_is_mplads": (
        "**MPLADS** (Member of Parliament Local Area Development Scheme) gives every MP a yearly fund "
        "(₹5 crore) for development works in their constituency — roads, school buildings, water supply, "
        "community halls, and similar public assets. This portal monitors the resulting projects: their "
        "sanctioned amounts, expenditure, physical progress, and risk indicators."
    ),
    "purpose": (
        "This platform helps auditors, analysts, citizens and officials monitor MPLADS projects "
        "transparently: browse the project portfolio, see risk scores and anomalies, verify work on the "
        "ground, and follow up flagged projects through inquiries and audit cases."
    ),
    "sections": (
        "**Main sections**\n"
        "• Overview — portfolio dashboard and AI insights\n"
        "• Projects — search/filter all projects\n"
        "• Risk Center — risk scores and delay indicators\n"
        "• State Intelligence — state-wise analysis\n"
        "• Reports — exportable summaries\n"
        "• AI Audit Center — anomaly detection (auditors)\n"
        "• Audit Priority — P1–P4 review ranking (auditors)\n"
        "• Vendor Network / Vendor Intelligence — vendor analysis\n"
        "• Ground Verification — submit and review field evidence (everyone)"
    ),
    "how_mplads_works": (
        "MPLADS flow: the central government releases funds to each MP's authority → the MP recommends "
        "works to an implementing agency (district authority) → projects are sanctioned and executed → "
        "expenditure is recorded against each project. This portal tracks the recorded projects, money and "
        "progress, and adds risk analytics on top of the published data."
    ),
    "ground_verification": (
        "**Ground Verification** lets anyone strengthen the data with on-the-ground evidence: look up a "
        "project by its ID, take a photo, capture your GPS location, and report what you actually see "
        "(Functional / Non-Functional / Work Not Started). Submissions go into a verification queue — "
        "they are evidence, not official status changes."
    ),
    "submit_evidence": (
        "To submit evidence: open **Ground Verification** in the sidebar, enter the project's numeric ID "
        "(shown as #12345 on any project card), optionally take/upload a photo, capture your location, pick "
        "the status you observe, and submit. Signed-in citizens can see all their own submissions under "
        "**My Verifications**."
    ),
    "after_submit": (
        "After you submit: your report (photo, GPS, status, note, timestamp) enters the verification "
        "queue. A field verifier reviews it and marks it Verified or Rejected with a note. Auditors can "
        "escalate disputed evidence for deeper review. The official project record is never changed by "
        "evidence submissions."
    ),
    "who_verifies": (
        "Citizen evidence is reviewed by **Field Verifiers** — personnel assigned to physically check "
        "projects. If evidence looks suspicious or is disputed, **Auditors** can independently review it "
        "and escalate."
    ),
    "risk_score": (
        "A **risk score** (0–100) flags projects that may deserve a closer look. It combines financial "
        "utilization (e.g. high spend with 0% progress), physical progress vs. money spent, project "
        "status and age, delays, and statistical anomalies vs. similar projects. A high score is a "
        "priority signal — **not** proof of wrongdoing."
    ),
    "priority_tiers": (
        "• P1 — Critical: investigate first\n"
        "• P2 — High: review this week\n"
        "• P3 — Medium: routine monitoring\n"
        "• P4 — Low: healthy on current data\n\n"
        "Tiers are computed from the composite priority score (risk index, financial exposure, evidence "
        "gaps, delay indicators)."
    ),
    "vendor_intelligence": (
        "**Vendor Intelligence** (BETA) aggregates every vendor appearing in the expenditure records: "
        "total paid, transaction counts, number of distinct projects, states/constituencies served. "
        "Search a vendor by name, state or constituency and open a profile with its engagements."
    ),
    "vendor_network": (
        "**Vendor Network** (BETA) visualizes possible vendor clusters — groups sharing a registered "
        "office or similar name families — as a graph. Flags are investigative leads for auditors, not "
        "proof of collusion."
    ),
    "ai_audit": (
        "The **AI Audit Command Center** scans all projects for anomaly indicators — photo duplication, "
        "cost outliers vs. category/state benchmarks, GPS mismatches, delayed SLAs — and ranks them on a "
        "0–100 audit risk index. Auditors inspect flagged projects and record dispositions."
    ),
    "inquiry_flow": (
        "Inquiry workflow: an **Auditor** issues an inquiry on a flagged project (from the inspection "
        "modal) → the **District Authority** for that area sees it in My District and posts an official "
        "response → the Auditor reviews the response and closes the inquiry. Everything is timestamped "
        "with the responder's identity."
    ),
    "search_help": (
        "Finding projects: use **Projects** in the sidebar. The search box matches project names/IDs; the "
        "filters narrow by state, constituency, district, status, project type and financial year. The "
        "header search jumps straight to matching projects from any page."
    ),
    "citizen_evidence": (
        "**Citizen Evidence** is the public layer of Ground Verification: any signed-in citizen can report "
        "what a project looks like on the ground with a photo, GPS and status. Each submission is "
        "reviewed by a field verifier before it counts as verified evidence — and it never alters "
        "official project data."
    ),
    # ── Upgrade additions ──
    "what_is_project": (
        "In this portal, a **project** is one sanctioned MPLADS work — a road, school building, water "
        "supply, community hall or similar public asset — identified by a numeric ID (shown as #12345). "
        "Each carries its sanctioned amount, recorded expenditure, physical progress, status and risk "
        "indicators."
    ),
    "status_meanings": (
        "**Project statuses**\n"
        "• Ongoing — work is sanctioned and in progress (or not yet reported complete)\n"
        "• Completed — the work is reported as finished\n"
        "Status comes from the published MPLADS data; evidence you submit does not change it."
    ),
    "report_issue": (
        "To report an issue with a project: open **Ground Verification**, enter the project ID, and "
        "submit what you observe — a photo, your GPS location, and the status you see (e.g. "
        "**Work Not Started** or **Non-Functional**), plus an optional note. Field verifiers review every "
        "submission. It never alters official records, but it creates a timestamped evidence trail."
    ),
    "verify_project": (
        "To verify a project: open **Ground Verification** in the sidebar → enter the project's numeric "
        "ID → take or upload a photo → capture your GPS location → pick the status you actually observe "
        "(Functional / Non-Functional / Work Not Started) → submit. Signed-in users can track their "
        "submissions under **My Verifications**."
    ),
    "why_gps": (
        "GPS tells reviewers **where** the photo was taken. Matching coordinates help a field verifier "
        "confirm the evidence belongs to that project's site — evidence without location is still "
        "accepted, just weaker. Sharing your location is optional."
    ),
    "flagged_meaning": (
        "**Flagged** means the system's checks marked a project as worth a human look — e.g. money spent "
        "with no reported progress, or statistical outliers vs. similar projects. It is a review signal, "
        "**not** a finding of wrongdoing. Auditors verify flagged projects before any conclusion."
    ),
    "risk_levels_meaning": (
        "**Risk levels**\n"
        "• High — multiple strong indicators; review soon\n"
        "• Medium — some indicators; worth monitoring\n"
        "• Low — few weak indicators\n"
        "• None — nothing flagged on current data\n\n"
        "Levels come from the 0–100 risk score. A high level flags a project for review — it is not "
        "proof of wrongdoing."
    ),
}


# ═══════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    page: Optional[str] = Field(None, max_length=60)


class ActionOut(BaseModel):
    label: str
    action: str            # "navigate" | "open_project"
    target: str


class AskResponse(BaseModel):
    answer: str
    source: str            # "knowledge" | "data" | "help"
    actions: List[ActionOut] = []


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _fmt_money(v) -> str:
    v = float(v or 0)
    if v >= 1e7:
        return f"₹{v/1e7:.2f} Cr"
    if v >= 1e5:
        return f"₹{v/1e5:.2f} L"
    return f"₹{v:,.0f}"


def _extract_state(question: str) -> Optional[str]:
    """Match a state name mentioned in the question against the real state list."""
    m = re.search(
        r"(?:in|from|of|for)\s+([a-z][a-z \.&']{2,40}?)(?:\?|$|,|\s+(?:show|which|what|how|list|give|tell))",
        question, re.I,
    )
    if not m:
        return None
    candidate = m.group(1).strip(" ?.,")
    return candidate or None


def _extract_project_id(question: str) -> Optional[int]:
    m = re.search(r"#?\b(?:project\s*)?(?:id\s*)?(\d{3,7})\b", question, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(?:this|current)\s+project", question, re.I)
    return None  # context resolution handled by the caller (page context)


def _fmt_project_line(p, risk=None) -> str:
    line = f"• **#{p.id} {p.project_name}** — {p.state}"
    if p.constituency:
        line += f", {p.constituency}"
    line += f" · sanctioned {_fmt_money(p.sanctioned_amount)}"
    if p.completion_percentage is not None:
        line += f" · {p.completion_percentage:.0f}% complete"
    if risk is not None:
        line += f" · risk {risk.risk_score if risk else '—'} ({risk.risk_level if risk else 'n/a'})"
    return line


# ═══════════════════════════════════════════════════════════════════
# Data intents — each returns (answer, actions) or None. Every query is
# role-gated and LIMIT-ed.
# ═══════════════════════════════════════════════════════════════════

def _intent_portfolio_stats(q: str, user, db: Session):
    ql = q.lower()
    if not re.search(r"how many|total.{0,12}projects|portfolio.{0,12}(size|overview|stats)|project count", ql):
        return None
    state = _extract_state(q)
    base = db.query(models.Project)
    if state:
        # match against the real state list (case-insensitive contains both ways)
        rows = db.query(models.Project.state).distinct().all()
        match = next((s for s in (r[0] for r in rows) if s and state.lower() in s.lower()), None)
        if not match:
            return ("I don't have enough data to answer that — I couldn't find a state "
                    f"named \u201c{state}\u201d in the dataset. Try the exact state name.", [])
        base = base.filter(models.Project.state == match)
        label = match
    else:
        label = "the whole portfolio"
    stats = base.with_entities(
        func.count(models.Project.id),
        func.coalesce(func.sum(models.Project.sanctioned_amount), 0),
        func.coalesce(func.sum(models.Project.expenditure), 0),
        func.sum(case_completed()),
    ).one()
    n, sanc, exp, completed = int(stats[0] or 0), float(stats[1] or 0), float(stats[2] or 0), int(stats[3] or 0)
    if n == 0:
        return f"No projects found for {label}.", []
    answer = (
        f"**{label}**: {n:,} projects\n"
        f"• Sanctioned: {_fmt_money(sanc)}\n"
        f"• Recorded expenditure: {_fmt_money(exp)} ({(exp/sanc*100) if sanc else 0:.1f}% utilization)\n"
        f"• Completed: {completed:,}"
    )
    actions = [ActionOut(label="Browse projects", action="navigate", target="Projects")]
    if not state:
        actions.append(ActionOut(label="State Intelligence", action="navigate", target="State Intelligence"))
    return answer, actions


def case_completed():
    from sqlalchemy import case
    return case((models.Project.status.ilike("%completed%"), 1), else_=0)


def _intent_state_top(ql: str, user, db: Session):
    if not re.search(r"which states?|states? (with|have|has)|top states|most projects", ql):
        return None
    rows = (
        db.query(models.Project.state, func.count(models.Project.id).label("n"))
        .filter(models.Project.state.isnot(None))
        .group_by(models.Project.state)
        .order_by(func.count(models.Project.id).desc())
        .limit(8)
        .all()
    )
    if not rows:
        return "I don't have enough data to answer that.", []
    lines = "\n".join(f"• {s}: {n:,} projects" for s, n in rows)
    return f"**Top states by project count:**\n{lines}", [
        ActionOut(label="Open State Intelligence", action="navigate", target="State Intelligence")
    ]


def _intent_high_risk(ql: str, user, db: Session):
    # Concept question ("what does high risk mean?") → knowledge, not data.
    # Only treat as a data request when the user wants actual projects/lists.
    if re.search(r"what (does|do|is|are).{0,16}(high|risk).{0,8}(risk )?mean|risk level.{0,10}mean", ql):
        return None
    if not re.search(r"high risk|highest.?risk|risky projects|riskiest", ql):
        return None
    # Risk rankings are internal analysis — citizens/guests get the concept,
    # not the list.
    if user is None or not auth.has_role_rank(user, "analyst"):
        return (
            "Risk scores are internal review indicators used by analysts and auditors. "
            "A high score flags a project for closer review — it is not proof of "
            "wrongdoing. If you're a citizen, you can browse public project information "
            "on the Projects page or strengthen the record through Ground Verification.",
            [ActionOut(label="Open Ground Verification", action="navigate", target="Ground Truth Verification")],
        )
    rows = (
        db.query(models.Project, models.RiskScore)
        .join(models.RiskScore, models.RiskScore.project_id == models.Project.id)
        .filter(models.RiskScore.risk_level.ilike("high"))
        .order_by(models.RiskScore.risk_score.desc())
        .limit(6)
        .all()
    )
    if not rows:
        return "No high-risk projects are currently flagged in the risk data.", []
    lines = "\n".join(_fmt_project_line(p, r) for p, r in rows)
    count = db.query(func.count(models.RiskScore.id)).filter(models.RiskScore.risk_level.ilike("high")).scalar() or 0
    answer = (
        f"{count:,} projects are flagged **high risk**. Top 6 by score:\n{lines}\n\n"
        "A high score is a review priority, not proof of wrongdoing."
    )
    return answer, [
        ActionOut(label="Open Risk Center", action="navigate", target="Risk Center"),
        ActionOut(label="Audit Priority", action="navigate", target="Audit Priority"),
    ]


def _intent_project_detail(q: str, ql: str, ctx_project_id: Optional[int], user, db: Session):
    # Attribute questions only resolve against a *selected* project context
    # ("what is the sanctioned amount?" while a project is open) — without a
    # selected project there is nothing to answer about.
    asks_attribute = bool(re.search(
        r"sanctioned amount|expenditure|current status|what.*(status|completion)|"
        r"main anomalies|what should (be|we|i) verif|explain this project|about this project",
        ql,
    ))
    if asks_attribute and not ctx_project_id:
        return (
            "Open a project first (click any row on the Projects page), then ask me about "
            "its sanctioned amount, expenditure, status or anomalies — I'll use that "
            "project's actual record.",
            [ActionOut(label="Browse projects", action="navigate", target="Projects")],
        )
    if not re.search(
        r"why is (this )?(project|it)|risk(y)?\s*(of|for)?\s*project|explain.{0,20}risk|about project|"
        r"tell me about project|details (of|for) project|what.{0,10}anomal|"
        r"sanctioned amount|expenditure|current status|what should (be|we|i) verif|explain this project|about this project",
        ql,
    ):
        return None
    pid = _extract_project_id(q) or ctx_project_id
    if not pid:
        return ("Which project? Give me the numeric ID (e.g. \u201cwhy is project 80649 risky?\u201d) "
                "or open the project first and ask again.", [])
    p = db.query(models.Project).filter(models.Project.id == pid).first()
    if not p:
        return f"I don't have project #{pid} in the dataset.", []
    risk = db.query(models.RiskScore).filter(models.RiskScore.project_id == pid).first()
    reasons = [r.strip() for r in (risk.reasons or "").split(",") if r.strip()] if risk else []
    util = (p.expenditure / p.sanctioned_amount * 100) if p.sanctioned_amount else 0
    lines = [
        f"**PROJECT**",
        f"Project ID: #{p.id}",
        f"Name: {p.project_name}",
        f"Location: {p.state}" + (f", {p.constituency}" if p.constituency else ""),
        f"Sanctioned: {_fmt_money(p.sanctioned_amount)} · Expenditure: {_fmt_money(p.expenditure)} ({util:.0f}% utilization)",
        f"Physical completion: {p.completion_percentage if p.completion_percentage is not None else '—'}% · Status: {p.status or '—'}",
        "",
        f"**Risk Score:** {risk.risk_score if risk else 'not scored'} ({risk.risk_level if risk else 'n/a'})",
    ]
    if reasons:
        lines.append("")
        lines.append("**KEY FINDINGS**")
        lines += [f"• {r}" for r in reasons[:6]]
    if risk and getattr(risk, "ml_anomaly", False):
        lines.append("• Flagged as a statistical anomaly by the ML model vs. similar projects")
    lines.append("")
    lines.append("**RECOMMENDED NEXT STEP**")
    lines.append("• Open the project's AI Forensics tab for the full evidence picture" if reasons
                 else "• No risk indicators recorded — routine monitoring is enough for now")
    actions = [ActionOut(label="Open project", action="open_project", target=str(p.id))]
    if reasons:
        actions.append(ActionOut(label="View Audit Details", action="navigate", target="AI Audit Center"))
    return "\n".join(lines), actions


def _intent_investigate_next(ql: str, user, db: Session):
    """Auditor/admin only."""
    if not re.search(r"what should i (investigate|review)|investigate (today|next)|inspect today|which projects should i", ql):
        return None
    if user is None or not auth.has_role_rank(user, "auditor"):
        return ("Project triage (\u201cwhat should I investigate\u201d) is available to auditors and "
                "administrators. You can still ask me about MPLADS, Ground Verification, or any "
                "public project.", [])
    rows = (
        db.query(models.Project, models.RiskScore)
        .join(models.RiskScore, models.RiskScore.project_id == models.Project.id)
        .order_by(models.RiskScore.risk_score.desc())
        .limit(5)
        .all()
    )
    pending_evidence = (
        db.query(func.count(models.VerificationReport.id))
        .filter(models.VerificationReport.status.isnot(None))
        .scalar() or 0
    )
    if not rows:
        return "No scored projects available right now.", []
    lines = "\n".join(
        f"• **#{p.id} {p.project_name}** — risk {r.risk_score} ({r.risk_level}), "
        f"{p.state}, {_fmt_money(p.sanctioned_amount)}"
        for p, r in rows
    )
    answer = (
        "**Suggested investigation queue (top risk first):**\n"
        f"{lines}\n\n"
        f"{pending_evidence:,} verification reports exist in the evidence pool. "
        "Open any project's AI Forensics tab before deciding a disposition."
    )
    return answer, [
        ActionOut(label="Open Audit Priority", action="navigate", target="Audit Priority"),
        ActionOut(label="View Audit Details", action="navigate", target="AI Audit Center"),
    ]


def _intent_my_role_data(ql: str, user, db: Session):
    """Role-aware personal data: verifications, inquiries, submissions."""
    if user is None:
        return None
    caps = auth.user_capabilities(user)

    if re.search(r"(my|assigned).{0,20}(submission|verification|report)s?|submissions? (needing|pending|awaiting)", ql):
        if "verification:read_own" in caps:
            mine = (
                db.query(models.VerificationReport)
                .filter(models.VerificationReport.user_id == user.id)
                .order_by(models.VerificationReport.created_at.desc())
                .limit(8)
                .all()
            )
            total = (
                db.query(func.count(models.VerificationReport.id))
                .filter(models.VerificationReport.user_id == user.id)
                .scalar() or 0
            )
            if total == 0:
                role_word = "verifications" if user.role != "citizen" else "evidence submissions"
                return (f"You have no {role_word} yet. Open Ground Verification, look up a project "
                        "ID, and submit your first report.", [
                            ActionOut(label="Open Ground Verification", action="navigate",
                                      target="Ground Truth Verification")])
            lines = "\n".join(
                f"• #{r.project_id} — {r.status} · {r.created_at[:16].replace('T', ' ')}"
                for r in mine
            )
            return (f"You have {total:,} submissions (latest {len(mine)}):\n{lines}", [
                ActionOut(label="My Verifications", action="navigate", target="My Verifications")])
        return None

    if re.search(r"(my|pending).{0,15}inquir|inquiries?.{0,15}(me|my|district)", ql):
        if "inquiry:respond" in caps and (user.assigned_district or user.assigned_state):
            scope_label = user.assigned_district or user.assigned_state
            if user.assigned_district:
                n_open = (
                    db.query(func.count(models.Inquiry.id))
                    .filter(models.Inquiry.district == user.assigned_district,
                            models.Inquiry.status == "open")
                    .scalar() or 0
                )
            else:
                n_open = (
                    db.query(func.count(models.Inquiry.id))
                    .join(models.Project, models.Project.id == models.Inquiry.project_id)
                    .filter(models.Project.state == user.assigned_state,
                            models.Inquiry.status == "open")
                    .scalar() or 0
                )
            return (f"Your area ({scope_label}) has {n_open} open inquiries. "
                    "Respond from My District; the issuing auditor reviews your reply.", [
                        ActionOut(label="Open My District", action="navigate", target="My District")])
        if "inquiry:respond" in caps:
            return ("No district/state is assigned to your account yet, so inquiries can't be "
                    "routed to you. Ask an administrator to set your assignment.", [])
        if "inquiry:review" in caps:
            counts = dict(
                db.query(models.Inquiry.status, func.count(models.Inquiry.id))
                .group_by(models.Inquiry.status).all()
            )
            return (f"Inquiries: {counts.get('open', 0)} open · {counts.get('responded', 0)} awaiting "
                    "your review · "
                    f"{counts.get('closed', 0)} closed. Issue new ones from an inspection modal.", [
                        ActionOut(label="Open Inquiries", action="navigate", target="Inquiries")])
        return ("Inquiries are exchanged between auditors and district authorities. "
                "Ask me about anything else — projects, evidence, or MPLADS basics.", [])
    return None


def _intent_anomalies(ql: str, user, db: Session):
    if not re.search(r"unusual spending|unusual spend|anomal(y|ies)|suspicious", ql):
        return None
    if user is None or not auth.has_role_rank(user, "analyst"):
        return ("Anomaly analysis is available to analysts, auditors and administrators. "
                "I can still help with project lookups, Ground Verification and MPLADS questions.", [])
    rows = (
        db.query(models.Project, models.RiskScore)
        .join(models.RiskScore, models.RiskScore.project_id == models.Project.id)
        .filter(models.RiskScore.ml_anomaly.is_(True))
        .order_by(models.RiskScore.risk_score.desc())
        .limit(6)
        .all()
    )
    total = db.query(func.count(models.RiskScore.id)).filter(models.RiskScore.ml_anomaly.is_(True)).scalar() or 0
    if total == 0:
        return "No ML-flagged anomalies in the current risk data.", []
    lines = "\n".join(_fmt_project_line(p, r) for p, r in rows)
    return (f"{total:,} projects are flagged as statistical anomalies (Isolation Forest vs. similar "
            f"projects). Top 6:\n{lines}", [
                ActionOut(label="Open Risk Center", action="navigate", target="Risk Center")])


# ═══════════════════════════════════════════════════════════════════
# Page-context help
# ═══════════════════════════════════════════════════════════════════

PAGE_HELP = {
    "Overview": "This Overview is the portfolio dashboard: fund utilization, completion mix, risk insights and AI narrative summaries generated from live data.",
    "Projects": "The Projects page lists every monitored project. Use the search box and filters (state, constituency, district, status, type, FY) to narrow the list; click a project to open its full detail drawer.",
    "Risk Center": "The Risk Center ranks projects by their 0–100 risk score with the contributing factors (utilization, progress mismatch, delays). It also shows first/latest expenditure dates and the estimated 'Delayed By' duration.",
    "State Intelligence": "State Intelligence compares states/UTs: project counts, sanctioned vs. spent, completion rates. Click a state to drill into its projects.",
    "Reports": "Reports offers exportable summaries of the portfolio for offline analysis and briefings.",
    "AI Audit Center": "The AI Audit Command Center scans for photo fraud, cost outliers, GPS mismatches and delayed SLAs, and ranks projects by a 0–100 audit risk index. Click Inspect on any row for the forensic summary.",
    "Audit Priority": "Audit Priority converts detected risk into a P1–P4 review order so auditors know what to look at first. P1 = investigate immediately.",
    "Compare Projects": "Compare Projects lets you pick two or more projects side by side — money, progress, risk factors — to see relative standing.",
    "Vendor Network": "Vendor Network (BETA) maps vendor clusters sharing offices or name families. Edges are shared-office/name signals; flags are leads, not proof.",
    "Vendor Intelligence": "Vendor Intelligence (BETA) profiles every vendor in the expenditure records — totals, transaction counts, distinct projects, geography. Search by vendor, state or constituency.",
    "Ground Truth Verification": "Ground Verification is the evidence portal: look up a project ID, take a photo, capture GPS, report the observed status. Signed-in users can track their own submissions; field verifiers and auditors review them.",
    "My Verifications": "My Verifications lists every evidence report you personally submitted, with status and timestamps.",
    "My District": "My District is the district-authority portal: scoped projects plus auditor inquiries awaiting your official response.",
    "Inquiries": "Inquiries tracks every auditor-issued inquiry, the district authority's response, and closure status.",
    "Saved Projects": "Saved Projects is your bookmarked list for quick follow-up.",
    "My Investigations": "My Investigations tracks projects you opened an investigation on, with priority tier and recommendations.",
    "My Audit Cases": "My Audit Cases holds the audit cases you saved; case content is regenerated from live data whenever opened.",
    "Settings": "Settings controls appearance (theme, font size) and account preferences.",
}

# Contextual starter chips per page (intersected with role defaults client-side
# via /assistant/suggestions?page=…). Ordered most-specific first.
PAGE_SUGGESTIONS = {
    "Overview": ["What is the purpose of this website?", "What do the risk levels mean?"],
    "Projects": ["How do I find a project?", "What does High Risk mean?", "What is a project?"],
    "Risk Center": ["What does High Risk mean?", "What is a risk score?", "What is 'Delayed By'?"],
    "State Intelligence": ["Which states have the most projects?", "How many projects are in Karnataka?"],
    "Reports": ["What reports can I export?", "What is the purpose of this website?"],
    "AI Audit Center": ["Why was this project flagged?", "Explain the risk score", "What should an auditor check?"],
    "Audit Priority": ["What does P1 mean?", "Why is this project prioritized?", "What is a risk score?"],
    "Compare Projects": ["How do I compare two projects?", "What does High Risk mean?"],
    "Vendor Network": ["What is Vendor Network?", "What does a vendor cluster mean?"],
    "Vendor Intelligence": ["What is Vendor Intelligence?", "How do I search for a vendor?"],
    "Ground Truth Verification": [
        "How do I submit evidence?",
        "Why is GPS useful?",
        "What happens after submission?",
    ],
    "My Verifications": ["Show my submissions", "What happens after I submit?"],
    "My District": ["Show my pending inquiries", "How do I respond to an inquiry?"],
    "Inquiries": ["What is an inquiry?", "How does the inquiry workflow work?"],
    "Evidence Queue": ["Which submissions need verification?", "How does verification work?"],
    "FAQ": ["What is MPLADS?", "How can I report an issue?"],
}


# ═══════════════════════════════════════════════════════════════════
# Suggestions per role
# ═══════════════════════════════════════════════════════════════════

SUGGESTIONS = {
    "general": [
        "What is MPLADS?",
        "What is the purpose of this website?",
        "How does Ground Verification work?",
        "How do I search for a project?",
    ],
    "citizen": [
        "How do I submit project evidence?",
        "What happens after I upload a photo?",
        "How many projects are in the portfolio?",
        "What is a risk score?",
    ],
    "field_verifier": [
        "Show my submissions",
        "What does a risk score mean?",
        "How does verification work?",
        "Who verifies citizen evidence?",
    ],
    "district_authority": [
        "Show my pending inquiries",
        "How do I respond to an inquiry?",
        "What is an inquiry?",
        "How do I search for a project?",
    ],
    "analyst": [
        "How many projects are in Karnataka?",
        "Which states have the most projects?",
        "Which projects have high risk?",
        "What is a risk score?",
    ],
    "auditor": [
        "What should I investigate today?",
        "Which projects have high risk?",
        "Find unusual spending.",
        "What does P1 mean?",
    ],
    "admin": [
        "What should I investigate today?",
        "Which projects have high risk?",
        "Show unusual spending.",
        "How does the inquiry workflow work?",
    ],
}


# ═══════════════════════════════════════════════════════════════════
# Main router
# ═══════════════════════════════════════════════════════════════════

def _answer(question: str, page: Optional[str], user, db: Session) -> Tuple[str, str, List[ActionOut]]:
    ql = question.lower().strip()
    ctx_project_id = None
    if page and page.startswith("project:"):
        try:
            ctx_project_id = int(page.split(":", 1)[1])
        except ValueError:
            ctx_project_id = None
    real_page = page if page and not page.startswith("project:") else None

    # 0. Page-context questions FIRST — "how does this work" while sitting on
    #    Ground Verification must explain Ground Verification, not something else.
    asks_page_context = bool(re.search(
        r"what is this|what am i looking at|what does this (page|show)|help.{0,10}this page|"
        r"where am i|about this page|how does this (page )?work",
        ql,
    ))
    if asks_page_context and real_page and real_page in PAGE_HELP:
        return PAGE_HELP[real_page], "help", []

    # 1. Data intents first (they may fall through with None)
    for fn in (
        lambda: _intent_project_detail(q=question, ql=ql, ctx_project_id=ctx_project_id, user=user, db=db),
        lambda: _intent_my_role_data(ql, user, db),
        lambda: _intent_investigate_next(ql, user, db),
        lambda: _intent_high_risk(ql, user, db),
        lambda: _intent_anomalies(ql, user, db),
        lambda: _intent_portfolio_stats(question, user, db),
        lambda: _intent_state_top(ql, user, db),
    ):
        result = fn()
        if result is not None:
            answer, actions = result
            return answer, "data", actions

    # 2. Knowledge base — answers gain a contextual action chip pointing at
    #    the screen matching the topic asked about.
    for pattern, key in KNOWLEDGE:
        if re.search(pattern, ql):
            answer = KNOWLEDGE_ANSWERS[key]
            actions: List[ActionOut] = []
            nav = {
                "ground_verification": ("Open Ground Verification", "Ground Truth Verification"),
                "submit_evidence": ("Open Ground Verification", "Ground Truth Verification"),
                "citizen_evidence": ("Open Ground Verification", "Ground Truth Verification"),
                "report_issue": ("Open Ground Verification", "Ground Truth Verification"),
                "verify_project": ("Open Ground Verification", "Ground Truth Verification"),
                "search_help": ("Browse projects", "Projects"),
                "vendor_intelligence": ("Open Vendor Intelligence", "Vendor Intelligence"),
                "vendor_network": ("Open Vendor Network", "Vendor Network"),
                "ai_audit": ("Open AI Audit Center", "AI Audit Center"),
                "priority_tiers": ("Open Audit Priority", "Audit Priority"),
                "status_meanings": ("Browse projects", "Projects"),
            }.get(key)
            if nav:
                actions.append(ActionOut(label=nav[0], action="navigate", target=nav[1]))
            return answer, "knowledge", actions

    # 3. Generic "how does this work / what is this" without a matching page
    #    (unknown or project-context page) — route to the Projects explainer.
    if asks_page_context:
        return PAGE_HELP["Projects"], "help", []

    # 3b. Page-scoped how-to questions on a known page — "what should an
    #     auditor check?" on AI Audit Center. Only generic phrasings, so
    #     role/data intents above still win for data questions.
    if real_page and re.search(
        r"what should (an|the) (auditor|verifier|authority) check|what.{0,12}check (here|on this page)|"
        r"how do i use this|what can i do here",
        ql,
    ):
        return PAGE_HELP[real_page], "help", []

    # 4. Fallback — honest "can't answer" with pointers
    role_note = ""
    if user is None:
        role_note = " You're browsing as a guest — sign in to submit evidence or use workspace features."
    return (
        "I don't have enough data to answer that. I can help with:\n"
        "• MPLADS basics and how this site works\n"
        "• Ground Verification and evidence submissions\n"
        "• Project lookups and risk explanations (try \u201cwhy is project 80649 risky?\u201d)\n"
        "• Portfolio stats (\u201chow many projects in Karnataka?\u201d)"
        + role_note,
        "help",
        [],
    )


@router.post("/ask", response_model=AskResponse)
def ask(
    payload: AskRequest,
    user: Optional[models.User] = Depends(_optional_user),
    db: Session = Depends(get_db),
):
    """Ask the MPLADS assistant. Role enforcement is server-side: every data
    intent re-checks auth.has_role_rank / capabilities before answering."""
    answer, source, actions = _answer(payload.question, payload.page, user, db)
    return AskResponse(answer=answer, source=source, actions=actions)


@router.get("/suggestions")
def suggestions(page: Optional[str] = None):
    """Suggested questions per role, optionally blended with page-specific
    chips. Page chips come first (they match the user's current context);
    the client keeps the list compact."""
    if not page or page not in PAGE_SUGGESTIONS:
        return SUGGESTIONS
    return {"general": PAGE_SUGGESTIONS[page] + SUGGESTIONS["general"][:2]}


@router.get("/context-help")
def context_help(page: str):
    """One-paragraph explanation of the page currently on screen — used by
    the assistant's 'about this page' context chip."""
    text = PAGE_HELP.get(page)
    if not text:
        raise HTTPException(status_code=404, detail="Unknown page")
    return {"page": page, "help": text}
