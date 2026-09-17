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
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import exists, func, or_, text
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
    (r"what\s+is\s+(the\s+)?risk\s+center|risk\s+center", "risk_center"),
    (r"why\s+is\s+(this\s+|my\s+)?(project\s+|it\s+)?p[1-4]\b", "priority_tiers"),
    (r"how\s+(do|can)\s+i\s+compare|compare\s+(two|projects)", "compare_help"),
    (r"how\s+(do|can)\s+i\s+check\s+a\s+vendor|check\s+vendors?|vendor\s+.{0,10}search", "vendor_intelligence"),
    (r"how\s+(do|can)\s+i\s+(see|find|view)\s+high.risk|see\s+risky", "search_help"),
    (r"how\s+(do|can)\s+i\s+respond\s+to\s+an?\s+inquiry", "respond_inquiry"),
    (r"how\s+(do|can)\s+i\s+use\s+vendor\s+network", "vendor_network"),
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
    "risk_center": (
        "The **Risk Center** ranks projects by their 0–100 risk score with the contributing factors "
        "(fund utilization, progress mismatch, delays), plus first/latest expenditure dates and the "
        "estimated 'Delayed By' duration. A high score is a review priority, not a finding."
    ),
    "compare_help": (
        "To compare projects: open **Compare Projects**, pick two projects, and you'll see sanctioned "
        "amounts, expenditure, physical progress and risk factors side by side. You can also ask me "
        "about a specific project by ID (e.g. \u201ctell me about project 80649\u201d) and I'll pull its record."
    ),
    "respond_inquiry": (
        "Responding to an inquiry: open **My District** — auditor inquiries for your assigned area are "
        "listed there with the project, the auditor's question and a deadline. Write your official "
        "response and submit; the issuing auditor is notified and reviews it. Every response is "
        "timestamped with your identity and role."
    ),
}


# ═══════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    page: Optional[str] = Field(None, max_length=60)
    session_id: Optional[str] = Field(None, max_length=64)


class ActionOut(BaseModel):
    label: str
    action: str            # "navigate" | "open_project"
    target: str


class AskResponse(BaseModel):
    answer: str
    source: str            # "knowledge" | "data" | "help"
    actions: List[ActionOut] = []
    project_id: Optional[int] = None   # project discussed — client keeps it for follow-ups


# ── Conversational session memory ────────────────────────────────────
# Remembers the last project each conversation discussed so pronoun
# follow-ups ("why is it risky?", "open it") resolve without re-typing the
# ID. Bounded: TTL expiry + hard cap, values are one small dict each.

_SESSION_LAST_PROJECT: Dict[str, Dict] = {}
_SESSION_LOCK = threading.Lock()
_SESSION_TTL = 3600.0     # seconds
_SESSION_MAX = 500        # hard cap on remembered sessions


def _session_get_project(session_id: Optional[str]) -> Optional[int]:
    if not session_id:
        return None
    now = time.time()
    with _SESSION_LOCK:
        entry = _SESSION_LAST_PROJECT.get(session_id)
        if not entry or now - entry["ts"] > _SESSION_TTL:
            _SESSION_LAST_PROJECT.pop(session_id, None)
            return None
        entry["ts"] = now
        return entry["project_id"]


def _session_set_project(session_id: Optional[str], project_id: Optional[int]) -> None:
    if not session_id or not project_id:
        return
    now = time.time()
    with _SESSION_LOCK:
        # Opportunistic TTL sweep keeps the dict bounded without a job.
        if len(_SESSION_LAST_PROJECT) >= _SESSION_MAX:
            expired = [k for k, v in _SESSION_LAST_PROJECT.items() if now - v["ts"] > _SESSION_TTL]
            for k in expired:
                _SESSION_LAST_PROJECT.pop(k, None)
        while len(_SESSION_LAST_PROJECT) >= _SESSION_MAX:
            _SESSION_LAST_PROJECT.pop(next(iter(_SESSION_LAST_PROJECT)))
        _SESSION_LAST_PROJECT[session_id] = {"project_id": int(project_id), "ts": now}


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
    """Conservative project-ID extraction. Only treats a number as a project
    reference when the phrasing anchors it: a project/proj/work prefix, an
    action verb (show/open/take me to…), a risk/status/details mention, a #
    prefix, or a standalone number message. Prevents false positives like the
    "2024" in \u201chow many projects completed in 2024?\u201d."""
    patterns = (
        r"#(\d{1,10})\b",
        r"\b(?:project|proj|work)\s*(?:no\.?|number|id)?\s*#?(\d{1,10})\b",
        r"\b(?:show|open|take\s+me\s+to|go\s*to|goto|jump\s+to|find|tell\s+me\s+about)\s+(?:of\s+|for\s+)?#?(\d{1,10})\b",
        r"\b(?:why\s+is|risk|status|details?)\s+(?:of\s+|for\s+)?#?(\d{1,10})\b",
        r"^\s*#?(\d{1,10})\s*\??$",
    )
    for pat in patterns:
        m = re.search(pat, question, re.I)
        if m:
            return int(m.group(1))
    return None  # "this project" context resolution handled by the caller


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

# ═══════════════════════════════════════════════════════════════════
# Navigation — "take me to X" / "open X". Targets are the app's REAL page
# keys; guards mirror the sidebar's own visibility rules so the assistant
# never offers a page the user's role cannot open.
# ═══════════════════════════════════════════════════════════════════

NAV_PAGES = [  # (pattern, page key, guard) — specific patterns first
    (r"ground\s+(truth\s+)?verif|verification\s+portal", "Ground Truth Verification", "verification:submit_or_guest"),
    (r"my\s+verifications?", "My Verifications", "verification:read_own"),
    (r"my\s+district", "My District", "inquiry:respond"),
    (r"evidence\s+queue|verification\s+queue", "Evidence Queue", "verification:review"),
    (r"\binquiries?\b", "Inquiries", "inquiry:review"),
    (r"saved\s+projects?", "Saved Projects", "analyst"),
    (r"my\s+investigations?", "My Investigations", "analyst"),
    (r"my\s+audit\s+cases?", "My Audit Cases", "analyst"),
    (r"admin(istration)?\s*(page|panel|area)?|^\badmin\b$", "Administration", "users:manage"),
    (r"vendor\s+intelligence", "Vendor Intelligence", "public_or_analyst"),
    (r"vendor\s+network", "Vendor Network", "public_or_analyst"),
    (r"ai\s+audit(\s+(command\s+)?center)?|audit\s+(command\s+)?center", "AI Audit Center", "public_or_analyst"),
    (r"audit\s+priority", "Audit Priority", "public_or_analyst"),
    (r"risk\s+center", "Risk Center", None),
    (r"state\s+intelligence", "State Intelligence", None),
    (r"compare\s+(projects?|two\s+projects?)", "Compare Projects", None),
    (r"\breports?\b", "Reports", None),
    (r"\bprojects?\b\s*(page|list|tab|explorer)?", "Projects", None),
    (r"\boverview\b|\bhome\b\s*(page|screen)?", "Overview", None),
    (r"\bsettings?\b", "Settings", None),
    (r"\bfaq\b", "FAQ", None),
]

_NAV_TRIGGER = re.compile(
    r"\btake\s+me\b|\bbring\s+me\b|\bgo\s*to\b|\bgoto\b|\bjump\s+to\b|\bnavigate\b|\bopen\b"
    r"|\bshow\s+me\b|\bswitch\s+to\b|\bhead\s+to\b|\bwhere\s+(is|are|can\s+i)", re.I,
)


def _nav_guard_error(page: str, guard: Optional[str], user) -> Optional[str]:
    """None when the user may open the page, else an honest explanation."""
    caps = auth.user_capabilities(user) if user else set()
    if guard is None:
        return None
    if guard == "analyst":
        if user and auth.has_role_rank(user, "analyst"):
            return None
        return f"The **{page}** workspace is available to analyst-tier accounts (analysts, auditors and administrators)."
    if guard == "public_or_analyst":
        if user is None or auth.has_role_rank(user, "analyst"):
            return None
        return f"The **{page}** section is available to analysts, auditors and administrators."
    if guard == "verification:submit_or_guest":
        if user is None or "verification:submit" in caps:
            return None
        if "inquiry:respond" in caps:
            return ("Ground Verification submissions are made by citizens, field verifiers and auditors. "
                    "Your role's workspace is **My District**, where auditor inquiries await your official response.")
        return "Submitting ground evidence needs a citizen, field verifier, auditor or administrator account."
    if guard in caps:
        return None
    return (f"The **{page}** section needs the \u201c{guard.replace(':', ' ').strip()}\u201d permission, "
            "which your account doesn't hold.")


def _intent_navigate(q: str, ql: str, ctx_project_id: Optional[int], user, db: Session):
    """"Take me to X" / "open X" / "where is X" — returns a navigation action,
    or None when the question isn't navigation (so data intents still run).
    Project-number navigation is handled by the project lookup intent."""
    # Pronoun navigation follow-up: "open it" / "take me to this project"
    if re.match(r"^(open|show|go\s*to|goto|take\s+me\s+to|jump\s+to)\s+(it|this\s+(project|one)?|that\s+(project|one)?)\b", ql):
        if ctx_project_id:
            p = db.query(models.Project).filter(models.Project.id == ctx_project_id).first()
            if p:
                return (f"Opening **#{p.id} {p.project_name}** — its details open over the Projects list.",
                        [ActionOut(label="Open Project Details", action="open_project", target=str(p.id))],
                        p.id)
        return ("Which project? Give me the ID (e.g. \u201copen project 80649\u201d) or open one from the "
                "Projects page first.",
                [ActionOut(label="Browse projects", action="navigate", target="Projects")])

    if not _NAV_TRIGGER.search(ql):
        return None
    # A numbered reference ("open project 80649") belongs to project lookup.
    if _extract_project_id(q) is not None:
        return None
    # Risk/anomaly phrasings are data questions even with "show me".
    if re.search(r"high\s+risk|riskiest|anomal|unusual|suspicious", ql):
        return None
    for pat, page, guard in NAV_PAGES:
        if re.search(pat, ql):
            err = _nav_guard_error(page, guard, user)
            if err:
                return (err, [])
            blurb = PAGE_HELP.get(page, "")
            text_out = f"**{page}**" + (f" — {blurb}" if blurb else "")
            return text_out, [ActionOut(label=f"Open {page}", action="navigate", target=page)]
    return None


def _project_profile_answer(p, risk) -> Tuple[str, List[ActionOut]]:
    """Full project profile composed ONLY from the real record + risk row."""
    reasons = [r.strip() for r in (risk.reasons or "").split(",") if r.strip()] if risk else []
    util = (p.expenditure / p.sanctioned_amount * 100) if p.sanctioned_amount else 0
    lines = [
        "**PROJECT**",
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
    actions = [ActionOut(label="Open Project Details", action="open_project", target=str(p.id))]
    if reasons:
        actions.append(ActionOut(label="View Audit Details", action="navigate", target="AI Audit Center"))
    return "\n".join(lines), actions


def _intent_project_lookup(
    q: str, ql: str, ctx_project_id: Optional[int], user, db: Session
):
    """Every question anchored to a specific project ID — lookup, navigation
    (\u201copen project 80649\u201d, \u201cshow 80649\u201d), and detail asks — plus pronoun
    follow-ups (\u201cwhy is it risky?\u201d) resolved against the selected-project
    context. Returns None when no project reference is present."""
    # Any explicit project-anchored number must be answered (found OR
    # not-found), never silently dropped to the fallback.
    pid = _extract_project_id(q)
    if pid is None and not re.match(r"^(open|show|go\s*to|goto|take\s+me\s+to|jump\s+to|display|find)\b", ql) \
            and not (ctx_project_id and re.search(r"\b(its?|this\s+project|this\s+one|that\s+project|that\s+one)\b", ql)):
        return None
    if re.search(r"compar|versus|\bvs\.?\b", ql) and len(re.findall(r"\b\d{1,10}\b", q)) >= 2:
        return ("To compare two specific projects, open **Compare Projects** and pick them — "
                "you'll get sanctioned amounts, expenditure, progress and risk side by side.",
                [ActionOut(label="Open Compare Projects", action="navigate", target="Compare Projects")])

    nav_ish = bool(re.match(r"^(open|show|go\s*to|goto|take\s+me\s+to|jump\s+to|display|find)\b", ql))

    # Pronoun/possessive follow-up with a selected project: "why is it risky?",
    # "tell me about this project", "what is its status?"
    if pid is None and ctx_project_id is not None:
        pronoun = re.search(r"\b(its?|this\s+project|this\s+one|that\s+project|that\s+one)\b", ql)
        asks = re.search(r"open|show|risk|anomal|about|tell|status|explain|check|verif", ql)
        if pronoun and asks and not re.search(r"page|section|website|site|workflow", ql):
            pid = ctx_project_id

    if pid is None:
        return None

    p = db.query(models.Project).filter(models.Project.id == pid).first()
    if not p:
        return (f"❓ I couldn't find a project with ID {pid}. Please check the Project ID and try "
                "again — IDs are the numeric identifiers shown as #12345 on project cards.", [])
    risk = db.query(models.RiskScore).filter(models.RiskScore.project_id == pid).first()

    # Pure navigation ask → compact found-card + action.
    if nav_ish and not re.search(r"why|risk|anomal|status|about|tell|explain|sanction|verif|detail", ql):
        loc = p.state + (f", {p.constituency}" if p.constituency else "")
        line = f"**Project found:** **#{p.id} {p.project_name}**\n{loc} · sanctioned {_fmt_money(p.sanctioned_amount)}"
        if p.completion_percentage is not None:
            line += f" · {p.completion_percentage:.0f}% complete"
        if risk:
            line += f" · risk {risk.risk_score} ({risk.risk_level})"
        return line, [ActionOut(label="Open Project Details", action="open_project", target=str(p.id))], p.id

    answer, actions = _project_profile_answer(p, risk)
    return answer, actions, p.id


def _intent_risk_methodology(ql: str, user, ctx_project_id: Optional[int], db: Session):
    """Explains the ACTUAL scoring rules from ml/predictor.py — real point
    weights and thresholds, no invented percentages."""
    if not re.search(
        r"how\s+(is|does).{0,30}risk.{0,20}(calculat|comput|determin|work|scored|built|made)"
        r"|how.{0,8}risk.{0,8}score.{0,15}(calculat|work)"
        r"|what\s+factors?.{0,25}(affect|contribute|go\s+into|drive|make).{0,15}risk"
        r"|risk\s+(score|index|methodology).{0,25}(calculat|comput|work|factors|methodology)"
        r"|what\s+makes?.{0,12}(a\s+)?(project|something).{0,10}(suspicious|risky)",
        ql,
    ):
        return None
    answer = (
        "The 0–100 **risk score** combines fixed rule checks on each project's own recorded data "
        "with an ML anomaly signal. Points add up when a check triggers:\n\n"
        "**Rule checks**\n"
        "• Expenditure exceeds the sanctioned amount — **+40**\n"
        "• 80%+ of sanctioned funds spent while physical completion is below 50% — **+35**\n"
        "• Any expenditure recorded with 0% physical completion — **+30**\n"
        "• Marked Completed while physical progress is below 90% — **+25**\n"
        "• Sanctioned ≥ ₹10 lakh with completion below 25% — **+20**\n"
        "• Completion reported ≥ 80% but zero expenditure recorded — **+20**\n"
        "• Sanctioned ≥ ₹5 lakh with under 10% utilization and completion below 30% — **+15**\n\n"
        "**ML anomaly** — flagged by an Isolation Forest model vs. similar projects — **+25**\n\n"
        "The total is capped at 100. **Levels:** High ≥ 60 · Medium ≥ 30 · Low above 0 · None = 0.\n\n"
        "A high score is a review-priority signal — **not** proof of wrongdoing."
    )
    if ctx_project_id:
        risk = db.query(models.RiskScore).filter(models.RiskScore.project_id == ctx_project_id).first()
        if risk:
            answer += f"\n\nThis project (#{ctx_project_id}) currently scores **{risk.risk_score} ({risk.risk_level})**."
    return answer, [
        ActionOut(label="Open Risk Center", action="navigate", target="Risk Center"),
        ActionOut(label="Audit Priority", action="navigate", target="Audit Priority"),
    ]


def _intent_vendor(q: str, ql: str, user, db: Session):
    """Vendor analytics — specific-vendor lookup and concentration ranking.
    Analyst-tier data (guests get the public demo, lateral roles don't)."""
    if not re.search(r"\bvendors?\b", ql):
        return None
    allowed = user is None or auth.has_role_rank(user, "analyst")

    # ── concentration / top vendors (pure SQL aggregate, tiny result) ──
    if re.search(r"concentration|which\s+vendors?.{0,30}(most|top|highest|largest|many)|top\s+vendors?"
                 r"|vendor\s+(spend|spending|totals?)", ql):
        if not allowed:
            return ("Vendor analytics are available to analysts, auditors and administrators. "
                    "I can still help with MPLADS basics, project lookups and Ground Verification.", [])
        rows = db.execute(text("""
            SELECT trim(vendor) AS name, COUNT(*) AS tx,
                   COALESCE(SUM(expenditure_amount), 0) AS total,
                   COUNT(DISTINCT work_description) AS works
            FROM expenditures
            WHERE vendor IS NOT NULL AND trim(vendor) <> ''
            GROUP BY normkey(vendor)
            ORDER BY works DESC, total DESC
            LIMIT 8
        """)).fetchall()
        if not rows:
            return "I don't have vendor expenditure data to answer that.", []
        lines = "\n".join(
            f"• **{r.name}** — {r.works:,} distinct works · {r.tx:,} transactions · {_fmt_money(r.total)}"
            for r in rows
        )
        return (f"**Vendors serving the most distinct works** (potential concentration — "
                f"investigative leads, not proof):\n{lines}", [
                    ActionOut(label="Open Vendor Network", action="navigate", target="Vendor Network"),
                    ActionOut(label="Open Vendor Intelligence", action="navigate", target="Vendor Intelligence"),
                ])

    # ── specific vendor lookup ──
    m = re.search(r"vendor[s]?\s+(?:named\s+|called\s+)?([A-Za-z][\w&\.\'\- ]{1,60}?)(?:\s+in\s+|\s+from\s+|\?|$)", q or "", re.I)
    if not m:
        return None
    candidate = m.group(1).strip(" ?.,!")
    stop = {"in", "from", "at", "for", "and", "the", "a", "an", "of", "on", "with", "by"}
    words = [w for w in candidate.split() if w.lower() not in stop]
    candidate = " ".join(words).strip()
    if len(candidate) < 3:
        return ("Which vendor? Give me the vendor's name (e.g. \u201ctell me about vendor DARSH BUILDCON\u201d).", [])
    if not allowed:
        return (f"Vendor profiles like \u201c{candidate}\u201d are available to analysts, auditors and "
                "administrators. I can still help with MPLADS basics, project lookups and Ground Verification.", [])
    row = db.execute(text("""
        SELECT trim(vendor) AS name, COUNT(*) AS tx,
               COALESCE(SUM(expenditure_amount), 0) AS total,
               COUNT(DISTINCT work_description) AS works
        FROM expenditures
        WHERE normkey(vendor) = normkey(:name)
        GROUP BY trim(vendor)
    """), {"name": candidate}).first()
    alternates = []
    if row is None:
        like = f"%{candidate}%"
        rows = db.execute(text("""
            SELECT trim(vendor) AS name, COUNT(*) AS tx,
                   COALESCE(SUM(expenditure_amount), 0) AS total,
                   COUNT(DISTINCT work_description) AS works
            FROM expenditures
            WHERE vendor LIKE :like
            GROUP BY normkey(vendor)
            ORDER BY total DESC
            LIMIT 5
        """), {"like": like}).fetchall()
        if not rows:
            return (f"I couldn't find a vendor named \u201c{candidate}\u201d in the expenditure records.", [])
        row, alternates = rows[0], [r.name for r in rows[1:]]
    states = [r[0] for r in db.execute(text("""
        SELECT DISTINCT trim(state) FROM expenditures
        WHERE normkey(vendor) = normkey(:name) AND state IS NOT NULL AND trim(state) <> ''
        LIMIT 5
    """), {"name": row.name}).fetchall()]
    lines = [
        f"**VENDOR — {row.name}**",
        f"• Total paid: {_fmt_money(row.total)} across {row.tx:,} transactions",
        f"• Distinct works (expenditure items): {row.works:,}",
    ]
    if states:
        lines.append(f"• States: {', '.join(states)}")
    if alternates:
        lines.append(f"• Similar names also found: {', '.join(alternates[:3])}")
    lines.append("")
    lines.append("Vendor signals are investigative leads — they don't prove wrongdoing.")
    return "\n".join(lines), [
        ActionOut(label="Open Vendor Intelligence", action="navigate", target="Vendor Intelligence"),
        ActionOut(label="Open Vendor Network", action="navigate", target="Vendor Network"),
    ]


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
    if not re.search(r"high[- ]risk|highest.?risk|risky projects|riskiest", ql):
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
    state = _extract_state(ql)
    q = (
        db.query(models.Project, models.RiskScore)
        .join(models.RiskScore, models.RiskScore.project_id == models.Project.id)
        .filter(models.RiskScore.risk_level.ilike("high"))
    )
    if state:
        q = q.filter(models.Project.state == state)
    rows = q.order_by(models.RiskScore.risk_score.desc()).limit(6).all()
    if not rows:
        scope = f" in {state.title()}" if state else ""
        return f"No high-risk projects are currently flagged in the risk data{scope}.", []
    lines = "\n".join(_fmt_project_line(p, r) for p, r in rows)
    count_q = db.query(func.count(models.RiskScore.id)).filter(models.RiskScore.risk_level.ilike("high"))
    if state:
        count_q = count_q.join(models.Project, models.Project.id == models.RiskScore.project_id).filter(models.Project.state == state)
    count = count_q.scalar() or 0
    scope = f" in {state.title()}" if state else ""
    answer = (
        f"{count:,} projects{scope} are flagged **high risk**. Top 6 by score:\n{lines}\n\n"
        "A high score is a review priority, not proof of wrongdoing."
    )
    return answer, [
        ActionOut(label="Open Risk Center", action="navigate", target="Risk Center"),
        ActionOut(label="Audit Priority", action="navigate", target="Audit Priority"),
    ]


def _intent_project_detail(q: str, ql: str, ctx_project_id: Optional[int], user, db: Session):
    """Context/attribute questions about a project ("why is this risky?",
    "what is the sanctioned amount?" with a project open). ID-anchored asks
    are handled by _intent_project_lookup; this catches the residue. Returns
    (answer, actions, discussed_project_id) — a 3-tuple."""
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
            None,
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
                "or open the project first and ask again.", [], None)
    p = db.query(models.Project).filter(models.Project.id == pid).first()
    if not p:
        return (f"❓ I couldn't find a project with ID {pid}. Please check the Project ID and try "
                "again.", [], None)
    risk = db.query(models.RiskScore).filter(models.RiskScore.project_id == pid).first()
    answer, actions = _project_profile_answer(p, risk)
    return answer, actions, pid


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


def _intent_analytical_screening(ql: str, user, db: Session):
    """Analytical screening questions: cost deviation, progress/expenditure
    mismatch, delayed, and ground-verification needs — all answered from a
    single SQL-side query per filter so the 512MB RAM budget is respected.
    Neutral terminology throughout: potential anomalies, never accusations."""
    is_cost = bool(re.search(r"cost (deviation|deviations|overrun|outlier)|unusual cost", ql))
    is_mismatch = bool(re.search(r"progress.{0,25}expenditure.{0,15}mismatch|expenditure.{0,25}progress.{0,15}mismatch|financial.{0,20}physical.{0,15}mismatch|money.{0,20}progress.{0,15}mismatch", ql))
    is_delayed = bool(re.search(r"\bdelayed\b|\bdelays\b|delayed projects|behind schedule", ql))
    is_verify = bool(re.search(r"(require|need|needs|which projects?).{0,20}(ground|field) verification|projects? (that )?need.{0,15}verification|requiring verification", ql))
    if not (is_cost or is_mismatch or is_delayed or is_verify):
        return None
    if user is None or not auth.has_role_rank(user, "analyst"):
        return ("Analytical screening is available to analysts, auditors and administrators. "
                "I can still help with project lookups, Ground Verification and general MPLADS questions.", [])

    # Optional state narrowing — "high cost deviation in Uttar Pradesh"
    state = _extract_state(ql)
    q = (
        db.query(models.Project, models.RiskScore)
        .join(models.RiskScore, models.RiskScore.project_id == models.Project.id)
        .filter(models.Project.sanctioned_amount > 0)
    )
    label = ""
    if is_cost:
        q = q.filter(models.Project.expenditure > models.Project.sanctioned_amount * 1.1)
        label = "expenditure exceeds the sanctioned amount by more than 10% (potential cost deviation)"
    elif is_mismatch:
        q = q.filter(
            models.Project.expenditure > 0,
            models.Project.completion_percentage < 25,
            models.Project.expenditure >= models.Project.sanctioned_amount * 0.5,
        )
        label = ("expenditure is at least 50% of the sanctioned amount while recorded "
                 "physical completion is below 25% (potential progress/expenditure mismatch)")
    elif is_delayed:
        q = q.filter(models.Project.status == "Not Started", models.Project.expenditure > 0)
        label = "recorded status is 'Not Started' while expenditure has already been booked (potential execution delay)"
    else:  # verification needs
        q = q.filter(
            models.RiskScore.risk_score >= 50,
            models.RiskScore.risk_level != "HIGH",
            ~exists().where(models.VerificationReport.project_id == models.Project.id),
            ~exists().where(models.Inquiry.project_id == models.Project.id),
        )
        label = ("risk score 50–99 (MEDIUM band) with no ground-verification evidence and no "
                 "open inquiry — candidates for field verification")
    if state:
        q = q.filter(models.Project.state == state)
    rows = q.order_by(models.RiskScore.risk_score.desc()).limit(6).all()
    count = q.order_by(None).count()
    if count == 0:
        scope = f" in {state.title()}" if state else ""
        return f"No projects currently match that screen{scope}.", []
    lines = "\n".join(_fmt_project_line(p, r) for p, r in rows)
    scope = f" in {state.title()}" if state else " across all states"
    answer = (f"{count:,} projects{scope} have {label}. Top {len(rows)} by risk score:\n\n{lines}\n\n"
              "These are AI/analytical indicators for review prioritisation — not confirmed findings.")
    return answer, [ActionOut(label="Open Risk Center", action="navigate", target="Risk Center")]


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

def _answer(question: str, page: Optional[str], user, db: Session,
            session_id: Optional[str] = None) -> Tuple[str, str, List[ActionOut], Optional[int]]:
    ql = question.lower().strip()
    ctx_project_id = None
    if page and page.startswith("project:"):
        try:
            ctx_project_id = int(page.split(":", 1)[1])
        except ValueError:
            ctx_project_id = None
    # Conversational memory: the project discussed earlier in this session —
    # used when the user refers to "it" without the page context carrying one.
    if ctx_project_id is None:
        ctx_project_id = _session_get_project(session_id)
    real_page = page if page and not page.startswith("project:") else None

    # 0. Page-context questions FIRST — "how does this work" while sitting on
    #    Ground Verification must explain Ground Verification, not something else.
    asks_page_context = bool(re.search(
        r"what is this|what am i looking at|what does this (page|show)|help.{0,10}this page|"
        r"where am i|about this page|how does this (page )?work",
        ql,
    ))
    if asks_page_context and real_page and real_page in PAGE_HELP:
        return PAGE_HELP[real_page], "help", [], None

    # 1. Data intents first (they may fall through with None). Order matters:
    #    navigation, then ID-anchored lookups, then role/data analytics.
    discussed_pid: Optional[int] = None
    results = [
        (lambda: _intent_navigate(question, ql, ctx_project_id, user, db), "data"),
        (lambda: _intent_project_lookup(question, ql, ctx_project_id, user, db), "data"),
        # List/screening intents BEFORE _intent_project_detail: plural data
        # requests ("show high-risk projects", "progress/expenditure mismatch")
        # must not be swallowed by the project-context attribute regex.
        (lambda: _intent_high_risk(ql, user, db), "data"),
        (lambda: _intent_analytical_screening(ql, user, db), "data"),
        (lambda: _intent_anomalies(ql, user, db), "data"),
        (lambda: _intent_project_detail(q=question, ql=ql, ctx_project_id=ctx_project_id, user=user, db=db), "data"),
        (lambda: _intent_risk_methodology(ql, user, ctx_project_id, db), "data"),
        (lambda: _intent_my_role_data(ql, user, db), "data"),
        (lambda: _intent_investigate_next(ql, user, db), "data"),
        (lambda: _intent_vendor(question, ql, user, db), "data"),
        (lambda: _intent_portfolio_stats(question, user, db), "data"),
        (lambda: _intent_state_top(ql, user, db), "data"),
    ]
    for fn, source in results:
        result = fn()
        if result is None:
            continue
        if len(result) == 3:
            answer, actions, discussed_pid = result
        else:
            answer, actions = result
        if discussed_pid:
            _session_set_project(session_id, discussed_pid)
        return answer, source, actions, discussed_pid

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
                "risk_center": ("Open Risk Center", "Risk Center"),
                "compare_help": ("Open Compare Projects", "Compare Projects"),
                "respond_inquiry": ("Open My District", "My District"),
            }.get(key)
            if nav:
                actions.append(ActionOut(label=nav[0], action="navigate", target=nav[1]))
            return answer, "knowledge", actions, None

    # 3. Generic "how does this work / what is this" without a matching page
    #    (unknown or project-context page) — route to the Projects explainer.
    if asks_page_context:
        return PAGE_HELP["Projects"], "help", [], None

    # 3b. Page-scoped how-to questions on a known page — "what should an
    #     auditor check?" on AI Audit Center. Only generic phrasings, so
    #     role/data intents above still win for data questions.
    if real_page and re.search(
        r"what should (an|the) (auditor|verifier|authority) check|what.{0,12}check (here|on this page)|"
        r"how do i use this|what can i do here",
        ql,
    ):
        return PAGE_HELP[real_page], "help", [], None

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
        None,
    )


@router.post("/ask", response_model=AskResponse)
def ask(
    payload: AskRequest,
    user: Optional[models.User] = Depends(_optional_user),
    db: Session = Depends(get_db),
):
    """Ask the MPLADS assistant. Role enforcement is server-side: every data
    intent re-checks auth.has_role_rank / capabilities before answering.
    Returns project_id so clients can keep conversation context for
    follow-ups like "why is it risky?" → "open it"."""
    session_id = payload.session_id or str(uuid.uuid4())
    answer, source, actions, discussed_pid = _answer(
        payload.question, payload.page, user, db, session_id=session_id
    )
    return AskResponse(answer=answer, source=source, actions=actions,
                       project_id=discussed_pid)


@router.get("/suggestions")
def suggestions(page: Optional[str] = None):
    """Suggested questions per role, optionally blended with page-specific
    chips. Page chips come first (they match the user's current context);
    the client keeps the list compact."""
    if not page or page not in PAGE_SUGGESTIONS:
        return SUGGESTIONS
    # Dedupe while preserving order — page chips often overlap role defaults.
    blended = list(dict.fromkeys(PAGE_SUGGESTIONS[page] + SUGGESTIONS["general"][:2]))
    return {"general": blended}


@router.get("/context-help")
def context_help(page: str):
    """One-paragraph explanation of the page currently on screen — used by
    the assistant's 'about this page' context chip."""
    text = PAGE_HELP.get(page)
    if not text:
        raise HTTPException(status_code=404, detail="Unknown page")
    return {"page": page, "help": text}
    return {"page": page, "help": text}
