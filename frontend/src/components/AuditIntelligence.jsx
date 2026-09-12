import { useEffect, useState } from "react"
import {
  getEvidenceGaps,
  getAnomalyExplorer,
  getPeerBenchmark,
  simulateRisk,
  getAuditCase,
  getInvestigation,
  startInvestigation,
  updateInvestigation,
  updateEvidenceItem,
} from "../services/api"
import { formatMoney } from "../utils/format"
import { parseReasons } from "../utils/reasons"
import { useAuth } from "../context/AuthContext"
import { saveAuditCase, createMyInvestigation } from "../services/api"

/* ═══════════════════════════════════════════════════════════
   MPLADS Audit Intelligence components
   Every value rendered here comes from the backend, which reads it
   from the project record / risk results. Nothing is estimated locally.
   ═══════════════════════════════════════════════════════════ */

const TIER_STYLE = {
  P1: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  P2: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300",
  P3: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  P4: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
}

const SEVERITY_STYLE = {
  high: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  medium: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  low: "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300",
  unknown: "bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400",
}

const STATUS_STYLE = {
  available: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300",
  reported_zero: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  partial: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  not_available: "bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400",
}

function Card({ children, className = "" }) {
  return (
    <div className={`rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-[#111827] ${className}`}>
      {children}
    </div>
  )
}

function SectionTitle({ children, right }) {
  return (
    <div className="mb-2 flex items-center justify-between gap-2">
      <h4 className="text-[0.875rem] font-bold uppercase tracking-wider text-gray-400">{children}</h4>
      {right}
    </div>
  )
}

function Chip({ children, className = "" }) {
  return <span className={`rounded px-2 py-0.5 text-[0.8125rem] font-bold ${className}`}>{children}</span>
}

function Spinner({ label }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-[#111827]">
      <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-600 border-r-transparent" />
      <span className="text-[0.9375rem] text-gray-400">{label}</span>
    </div>
  )
}

/* ═══════════════ 9. Digital Audit Card ═══════════════ */

export function DigitalAuditCard({ detail, onStartInvestigation, investigation }) {
  const proj = detail?.project
  const risk = detail?.risk
  const audit = detail?.audit_intelligence
  if (!proj || !risk) return null

  const priority = audit?.priority
  const exposure = audit?.financial_exposure
  const evidence = audit?.evidence_gap
  const actions = audit?.recommended_actions || []

  const reasons = parseReasons(risk.reasons)

  const sanctioned = Number(proj.sanctioned_amount || 0)
  const expenditure = Number(proj.expenditure || 0)
  const completion = Number(proj.completion_percentage || 0)
  const utilization = sanctioned > 0 ? (expenditure / sanctioned) * 100 : null
  const overspend = utilization !== null && utilization > 100

  const scoreColor =
    risk.risk_level === "High" ? "text-red-600 dark:text-red-400"
    : risk.risk_level === "Medium" ? "text-amber-600 dark:text-amber-400"
    : "text-green-600 dark:text-green-400"

  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-[#111827]">
      {/* RISK */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">Risk</p>
          <div className="flex items-baseline gap-1.5">
            <span className={`font-mono text-3xl font-bold ${scoreColor}`}>{risk.risk_score}</span>
            <span className="font-mono text-sm text-gray-400">/ 100</span>
          </div>
          <span className={`mt-1 inline-block rounded px-2 py-0.5 text-[0.8125rem] font-bold ${
            risk.risk_level === "High" ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
            : risk.risk_level === "Medium" ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
            : "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300"
          }`}>{(risk.risk_level || "None").toUpperCase()} RISK</span>
        </div>
        <div className="text-right">
          <p className="text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">How urgent?</p>
          {priority ? (
            <>
              <span className={`mt-0.5 inline-block rounded px-2 py-1 text-[0.8125rem] font-bold ${TIER_STYLE[priority.tier] || TIER_STYLE.P4}`} title={(priority.explanation || []).join(" ")}>
                {priority.tier} — {priority.tier_label}
              </span>
              <p className="mt-1 font-mono text-[0.8125rem] text-gray-400">
                Audit priority {priority.audit_priority_score}/100
              </p>
            </>
          ) : (
            <span className="text-[0.9375rem] text-gray-400">Not available</span>
          )}
        </div>
      </div>

      <div className="mt-3 h-2 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
        <div className={`h-full rounded-full ${
          risk.risk_level === "High" ? "bg-red-500" : risk.risk_level === "Medium" ? "bg-amber-500" : "bg-green-500"
        }`} style={{ width: `${Math.min(100, Number(risk.risk_score) || 0)}%` }} />
      </div>

      {/* WHY */}
      <div className="mt-4">
        <SectionTitle>Why?</SectionTitle>
        {reasons.length > 0 ? (
          <ul className="space-y-1">
            {reasons.slice(0, 4).map((r, i) => (
              <li key={i} className="flex items-start gap-1.5 text-[1rem] leading-relaxed text-gray-700 dark:text-gray-300">
                <span className="mt-0.5 text-red-500">→</span><span>{r}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[0.9375rem] text-gray-400">No risk conditions are currently triggered for this project.</p>
        )}
        {utilization !== null && (
          <p className="mt-1.5 font-mono text-[0.875rem] text-gray-500 dark:text-gray-400">
            Sanctioned {formatMoney(sanctioned)} · Spent {formatMoney(expenditure)} · Utilization {utilization.toFixed(1)}% · Progress {completion}%
          </p>
        )}
      </div>

      {/* WHAT IS MISSING */}
      <div className="mt-4">
        <SectionTitle>What is missing?</SectionTitle>
        {evidence ? (
          <>
            <p className="text-[1rem] leading-relaxed text-gray-600 dark:text-gray-300">{evidence.summary}</p>
            {evidence.missing_labels?.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {evidence.missing_labels.slice(0, 5).map((l) => (
                  <Chip key={l} className="bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300">{l}</Chip>
                ))}
                {evidence.missing_labels.length > 5 && (
                  <Chip className="bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400">
                    +{evidence.missing_labels.length - 5} more
                  </Chip>
                )}
              </div>
            )}
          </>
        ) : (
          <p className="text-[0.9375rem] text-gray-400">Evidence summary unavailable.</p>
        )}
      </div>

      {/* WHAT SHOULD I DO */}
      <div className="mt-4">
        <SectionTitle>What should I do?</SectionTitle>
        {actions.length > 0 ? (
          <ul className="space-y-1">
            {actions.slice(0, 4).map((a, i) => (
              <li key={i} className="flex items-start gap-1.5 text-[1rem] leading-relaxed text-gray-700 dark:text-gray-300">
                <span className="mt-0.5 text-blue-600 dark:text-blue-400">•</span><span>{a}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[0.9375rem] text-gray-400">No specific verification action was generated.</p>
        )}
      </div>

      {/* Exposure + review level */}
      <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {exposure && (
          <div className="rounded-lg border border-gray-200 bg-white p-2.5 dark:border-gray-700 dark:bg-[#1f2937]">
            <p className="text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">Funds under review</p>
            <p className="font-mono text-sm font-bold">{exposure.funds_under_review_display}</p>
            {overspend && exposure.overspend_display && (
              <p className="mt-0.5 text-[0.875rem] font-semibold text-red-600 dark:text-red-400">
                Overspend {exposure.overspend_display}
              </p>
            )}
          </div>
        )}
        {audit?.review_level && (
          <div className="rounded-lg border border-gray-200 bg-white p-2.5 dark:border-gray-700 dark:bg-[#1f2937]">
            <p className="text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">Suggested review level</p>
            <p className="text-[1rem] font-semibold text-gray-800 dark:text-gray-200">{audit.review_level.level}</p>
            <p className="mt-0.5 text-[0.8125rem] text-gray-400">{audit.review_level.basis}</p>
          </div>
        )}
      </div>

      {/* START INVESTIGATION */}
      <button
        onClick={onStartInvestigation}
        className="mt-4 w-full rounded-lg bg-[#031632] px-4 py-2.5 text-[0.9375rem] font-bold text-white transition hover:bg-[#0a2450] dark:bg-blue-600 dark:hover:bg-blue-500"
      >
        {investigation?.investigation
          ? `Open Investigation (${investigation.progress_pct}% complete)`
          : "START INVESTIGATION"}
      </button>

      <p className="mt-2 text-[0.8125rem] leading-relaxed text-gray-400">
        Priority, exposure and actions are system-generated indicators derived from the recorded project values.
        They identify work for review and do not establish delay, irregularity or wrongdoing.
      </p>
    </div>
  )
}

/* ═══════════════ 2. Evidence gap panel ═══════════════ */

export function EvidenceGapPanel({ projectId }) {
  const [gaps, setGaps] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    let alive = true
    setLoading(true); setError("")
    getEvidenceGaps(projectId)
      .then((d) => alive && setGaps(d))
      .catch(() => alive && setError("Could not load the evidence check."))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [projectId])

  if (loading) return <Spinner label="Checking evidence availability..." />
  if (error) return <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-[0.9375rem] font-semibold text-red-700 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300">{error}</div>
  if (!gaps) return null
  const conf = gaps.confidence
  return (
    <div className="space-y-3">
      <Card>
        <SectionTitle right={<Chip className={
          conf === "High" ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300"
          : conf === "Medium" ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
          : "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
        }>DATA CONFIDENCE: {conf}</Chip>}>
          What evidence is missing?
        </SectionTitle>
        <p className="text-[1rem] leading-relaxed text-gray-600 dark:text-gray-300">{gaps.summary}</p>
        {gaps.confidence_basis?.length > 0 && (
          <ul className="mt-2 space-y-1">
            {gaps.confidence_basis.map((b, i) => (
              <li key={i} className="text-[0.9375rem] leading-relaxed text-gray-500 dark:text-gray-400">• {b}</li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-[0.8125rem] text-gray-400">
          Risk score is calculated from the available data and is not reduced when evidence is missing.
        </p>
      </Card>

      <Card>
        <SectionTitle>Evidence availability</SectionTitle>
        <div className="divide-y divide-gray-100 dark:divide-gray-700/60">
          {gaps.items.map((item) => (
            <div key={item.key} className="py-2.5 first:pt-0 last:pb-0">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[1rem] font-semibold text-gray-800 dark:text-gray-200">{item.label}</p>
                  {item.value && <p className="font-mono text-[1rem] text-gray-500 dark:text-gray-400">{item.value}</p>}
                  {item.note && <p className="mt-0.5 text-[0.8125rem] text-gray-400">{item.note}</p>}
                </div>
                <Chip className={`flex-shrink-0 ${STATUS_STYLE[item.status] || STATUS_STYLE.not_available}`}>
                  {item.status_label}
                </Chip>
              </div>
              {item.source && <p className="mt-0.5 text-[0.8125rem] text-gray-400">source: {item.source}</p>}
            </div>
          ))}
        </div>
      </Card>

      {gaps.limitations?.length > 0 && (
        <Card className="border-amber-200 bg-amber-50/50 dark:border-amber-900/40 dark:bg-amber-950/20">
          <SectionTitle>Assessment limitations</SectionTitle>
          <ul className="space-y-1.5">
            {gaps.limitations.map((l, i) => (
              <li key={i} className="flex items-start gap-1.5 text-[0.9375rem] leading-relaxed text-amber-700 dark:text-amber-300">
                <span className="mt-0.5">⚠</span><span>{l}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}

/* ═══════════════ 1. Investigation workspace ═══════════════ */

const ITEM_STATUSES = ["Pending", "Verified", "Discrepancy Found", "Not Applicable"]
const ITEM_STATUS_SHORT = {
  "Pending": "Pending",
  "Verified": "Verified",
  "Discrepancy Found": "Discrepancy",
  "Not Applicable": "N/A",
}
const ITEM_STATUS_STYLE = {
  "Pending": "border-gray-300 text-gray-600 dark:border-gray-600 dark:text-gray-300",
  "Verified": "border-green-400 bg-green-50 text-green-700 dark:border-green-700 dark:bg-green-950/30 dark:text-green-300",
  "Discrepancy Found": "border-red-400 bg-red-50 text-red-700 dark:border-red-700 dark:bg-red-950/30 dark:text-red-300",
  "Not Applicable": "border-gray-400 bg-gray-100 text-gray-600 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300",
}

export function InvestigationWorkspace({ projectId, onWorkspaceChange }) {
  const [ws, setWs] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [note, setNote] = useState("")
  const [savedNote, setSavedNote] = useState(false)

  const apply = (payload) => {
    setWs(payload)
    if (onWorkspaceChange) onWorkspaceChange(payload)
  }

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError("")
    getInvestigation(projectId)
      .then((data) => {
        if (!alive) return
        apply(data)
        setNote(data?.investigation?.note || "")
      })
      .catch(() => alive && setError("Could not load the investigation workspace."))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  const handleStart = async () => {
    setBusy(true); setError("")
    try {
      const data = await startInvestigation(projectId)
      apply(data)
      setNote(data?.investigation?.note || "")
    } catch (e) { setError(e?.message || "Could not start the investigation.") }
    finally { setBusy(false) }
  }

  const handleItem = async (itemKey, status) => {
    setBusy(true); setError("")
    try {
      const data = await updateEvidenceItem(projectId, itemKey, status)
      apply(data)
    } catch (e) { setError(e?.message || "Could not update the checklist item.") }
    finally { setBusy(false) }
  }

  const handleStatus = async (status) => {
    setBusy(true); setError("")
    try {
      const data = await updateInvestigation(projectId, { status })
      apply(data)
    } catch (e) { setError(e?.message || "Could not update the investigation status.") }
    finally { setBusy(false) }
  }

  const handleSaveNote = async () => {
    setBusy(true); setError(""); setSavedNote(false)
    try {
      const data = await updateInvestigation(projectId, { note })
      apply(data)
      setSavedNote(true)
    } catch (e) { setError(e?.message || "Could not save the note.") }
    finally { setBusy(false) }
  }

  if (loading) return <Spinner label="Loading investigation workspace..." />

  const inv = ws?.investigation

  if (!inv) {
    return (
      <Card>
        <SectionTitle>AI Audit Investigation Workspace</SectionTitle>
        <p className="text-[1rem] leading-relaxed text-gray-600 dark:text-gray-300">
          An investigation converts this project's detected anomalies into an evidence checklist that an auditor can
          work through. The checklist items are recommended verification actions generated from the recorded values —
          they are not allegations.
        </p>
        {error && <p className="mt-2 text-[0.9375rem] font-semibold text-red-600 dark:text-red-400">{error}</p>}
        <button
          onClick={handleStart}
          disabled={busy}
          className="mt-3 w-full rounded-lg bg-[#031632] px-4 py-2.5 text-[0.9375rem] font-bold text-white transition hover:bg-[#0a2450] disabled:opacity-50 dark:bg-blue-600 dark:hover:bg-blue-500"
        >
          {busy ? "Starting..." : "START INVESTIGATION"}
        </button>
      </Card>
    )
  }

  const workflow = ws.workflow || []
  const progress = ws.progress_pct || 0

  return (
    <div className="space-y-3">
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-[0.9375rem] font-semibold text-red-700 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300">
          {error}
        </div>
      )}

      <Card>
        <SectionTitle
          right={
            <Chip className="bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300">
              {inv.status}
            </Chip>
          }
        >
          Investigation status
        </SectionTitle>

        {/* Workflow stepper */}
        <div className="flex flex-wrap items-center gap-1.5">
          {workflow.map((s, i) => (
            <div key={s} className="flex items-center gap-1.5">
              <button
                onClick={() => handleStatus(s)}
                disabled={busy}
                className={`rounded-lg border px-2.5 py-1.5 text-[0.875rem] font-bold transition disabled:opacity-60 ${
                  inv.status === s
                    ? "border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-300"
                    : "border-gray-200 text-gray-500 hover:border-gray-300 dark:border-gray-700 dark:text-gray-400"
                }`}
              >
                {s}
              </button>
              {i < workflow.length - 1 && <span className="text-[0.8125rem] text-gray-300 dark:text-gray-600">→</span>}
            </div>
          ))}
        </div>

        {/* Progress */}
        <div className="mt-3">
          <div className="flex items-center justify-between text-[0.8125rem] font-bold text-gray-400">
            <span>Investigation progress</span>
            <span className="font-mono">{progress}%</span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
            <div className="h-full rounded-full bg-blue-600 transition-all duration-300" style={{ width: `${progress}%` }} />
          </div>
          <p className="mt-1 text-[0.9375rem] leading-relaxed text-gray-500 dark:text-gray-400">
            {ws.resolved_items} of {ws.total_items} checklist items resolved
            {ws.discrepancies > 0 ? ` · ${ws.discrepancies} discrepancy note(s)` : ""}
          </p>
        </div>
      </Card>

      <Card>
        <SectionTitle>Evidence checklist</SectionTitle>
        <div className="space-y-2.5">
          {ws.items.map((item) => (
            <div key={item.item_key} className="rounded-lg border border-gray-200 p-2.5 dark:border-gray-700">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[1rem] font-semibold text-gray-800 dark:text-gray-200">{item.label}</p>
                  <p className="mt-0.5 text-[0.9375rem] leading-relaxed text-gray-500 dark:text-gray-400">{item.rationale}</p>
                </div>
                <Chip className={`flex-shrink-0 ${SEVERITY_STYLE[item.severity] || SEVERITY_STYLE.low}`}>
                  {(item.severity || "").toUpperCase()}
                </Chip>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {ITEM_STATUSES.map((s) => (
                  <button
                    key={s}
                    onClick={() => handleItem(item.item_key, s)}
                    disabled={busy}
                    className={`rounded border px-2 py-1 text-[0.8125rem] font-bold transition disabled:opacity-60 ${
                      item.status === s ? ITEM_STATUS_STYLE[s] : "border-gray-200 text-gray-400 hover:border-gray-300 dark:border-gray-700 dark:text-gray-500"
                    }`}
                  >
                    {ITEM_STATUS_SHORT[s]}
                  </button>
                ))}
              </div>
              <p className="mt-1 text-[0.8125rem] text-gray-400">
                {item.category} · updated {item.updated_at ? item.updated_at.replace("T", " ").slice(0, 16) : "—"}
              </p>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <SectionTitle>Investigation note</SectionTitle>
        <textarea
          value={note}
          onChange={(e) => { setNote(e.target.value); setSavedNote(false) }}
          rows={3}
          placeholder="Record the verification steps taken (stored with this investigation only)."
          className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-[1rem] text-gray-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-[#111827] dark:text-white"
        />
        <div className="mt-2 flex items-center gap-2">
          <button
            onClick={handleSaveNote}
            disabled={busy}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-[0.875rem] font-bold text-gray-700 transition hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800"
          >
            {busy ? "Saving..." : "Save note"}
          </button>
          {savedNote && <span className="text-[0.875rem] font-semibold text-green-600 dark:text-green-400">Saved</span>}
          <span className="ml-auto font-mono text-[0.8125rem] text-gray-400">
            Started {inv.created_at ? inv.created_at.replace("T", " ").slice(0, 16) : "—"} · risk at start {inv.risk_score_at_start ?? "—"}
          </span>
        </div>
      </Card>

      <p className="text-[0.8125rem] leading-relaxed text-gray-400">
        Checklist items and their rationale are generated from this project's recorded values and detected anomalies.
        Marking an item "Discrepancy Found" records your finding against this case only.
      </p>
    </div>
  )
}

/* ═══════════════ 4. Anomaly explorer ═══════════════ */

export function AnomalyExplorerPanel({ projectId }) {
  const [explorer, setExplorer] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    let alive = true
    setLoading(true); setError("")
    getAnomalyExplorer(projectId)
      .then((d) => alive && setExplorer(d))
      .catch(() => alive && setError("Could not load the anomaly explorer."))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [projectId])

  if (loading) return <Spinner label="Breaking down the anomaly dimensions..." />
  if (error) return <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-[0.9375rem] font-semibold text-red-700 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300">{error}</div>
  if (!explorer) return null
  return (
    <div className="space-y-3">
      <Card>
        <SectionTitle right={<Chip className="bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300">{explorer.highest_severity?.toUpperCase()} severity</Chip>}>
          Anomaly Explorer
        </SectionTitle>
        <p className="text-[1rem] leading-relaxed text-gray-600 dark:text-gray-300">{explorer.summary}</p>
      </Card>

      {explorer.dimensions.map((d) => (
        <Card key={d.dimension}>
          <SectionTitle
            right={
              <div className="flex gap-1">
                <Chip className={SEVERITY_STYLE[d.severity] || SEVERITY_STYLE.unknown}>{(d.severity || "").toUpperCase()}</Chip>
                <Chip className="bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400">{d.basis}</Chip>
              </div>
            }
          >
            {d.title}
          </SectionTitle>

          <p className={`text-[1rem] font-semibold ${
            d.status === "flagged" ? "text-gray-800 dark:text-gray-200" : "text-gray-500 dark:text-gray-400"
          }`}>{d.finding}</p>

          {/* Observed */}
          <div className="mt-2 rounded-lg bg-gray-50 p-2 dark:bg-[#0f1524]">
            <p className="text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">What we observed</p>
            <div className="mt-1 grid grid-cols-1 gap-1 sm:grid-cols-2">
              {d.observed.map((o, i) => (
                <div key={i} className="flex items-baseline justify-between gap-2">
                  <span className="text-[0.9375rem] leading-relaxed text-gray-500 dark:text-gray-400">{o.label}</span>
                  <span className="font-mono text-[1rem] font-bold text-gray-800 dark:text-gray-200">{o.value}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-2">
            <p className="text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">Why it matters</p>
            <p className="mt-0.5 text-[0.9375rem] leading-relaxed text-gray-600 dark:text-gray-300">{d.why_it_matters}</p>
          </div>

          <div className="mt-2">
            <p className="text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">What should be verified</p>
            <ul className="mt-0.5 space-y-1">
              {d.what_to_verify.map((v, i) => (
                <li key={i} className="flex items-start gap-1.5 text-[0.9375rem] leading-relaxed text-gray-600 dark:text-gray-300">
                  <span className="mt-0.5 text-blue-600 dark:text-blue-400">→</span><span>{v}</span>
                </li>
              ))}
            </ul>
          </div>

          {d.data_caveat && (
            <p className="mt-2 rounded-lg bg-amber-50 p-2 text-[0.9375rem] text-amber-700 dark:bg-amber-950/20 dark:text-amber-300">
              ⚠ {d.data_caveat}
            </p>
          )}
        </Card>
      ))}
    </div>
  )
}

/* ═══════════════ 6. What-if simulator ═══════════════ */

export function WhatIfSimulator({ detail }) {
  const proj = detail?.project
  const [form, setForm] = useState({ sanctioned_amount: "", expenditure: "", completion_percentage: "" })
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (!proj) return
    setForm({
      sanctioned_amount: String(proj.sanctioned_amount ?? 0),
      expenditure: String(proj.expenditure ?? 0),
      completion_percentage: String(proj.completion_percentage ?? 0),
    })
    setResult(null)
  }, [proj?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!proj) return null

  const run = async () => {
    setBusy(true); setError("")
    try {
      const payload = {}
      const s = parseFloat(form.sanctioned_amount)
      const e = parseFloat(form.expenditure)
      const c = parseFloat(form.completion_percentage)
      if (!Number.isNaN(s) && s !== Number(proj.sanctioned_amount || 0)) payload.sanctioned_amount = s
      if (!Number.isNaN(e) && e !== Number(proj.expenditure || 0)) payload.expenditure = e
      if (!Number.isNaN(c) && c !== Number(proj.completion_percentage || 0)) payload.completion_percentage = c
      if (Object.keys(payload).length === 0) {
        setError("Change at least one value to run a simulation.")
        setBusy(false)
        return
      }
      const data = await simulateRisk(proj.id, payload)
      setResult(data)
    } catch (err) {
      setError(err?.message || "Simulation failed.")
    } finally { setBusy(false) }
  }

  const reset = () => {
    setForm({
      sanctioned_amount: String(proj.sanctioned_amount ?? 0),
      expenditure: String(proj.expenditure ?? 0),
      completion_percentage: String(proj.completion_percentage ?? 0),
    })
    setResult(null)
    setError("")
  }

  const field = (key, label) => (
    <div>
      <label className="block text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">{label}</label>
      <input
        type="number"
        value={form[key]}
        onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
        className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 font-mono text-[1rem] text-gray-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-[#111827] dark:text-white"
      />
    </div>
  )

  return (
    <div className="space-y-3">
      <Card className="border-purple-200 bg-purple-50/50 dark:border-purple-900/40 dark:bg-purple-950/20">
        <SectionTitle>What would change the risk?</SectionTitle>
        <p className="text-[0.9375rem] leading-relaxed text-purple-700 dark:text-purple-300">
          Adjust the recorded values below to see which risk conditions would no longer be triggered. The simulated
          figures are recalculated with the same rules and model used for the stored risk score.
        </p>
      </Card>

      <Card>
        <SectionTitle>Simulation inputs</SectionTitle>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {field("sanctioned_amount", "Sanctioned amount (₹)")}
          {field("expenditure", "Expenditure (₹)")}
          {field("completion_percentage", "Physical progress (%)")}
        </div>
        <div className="mt-3 flex items-center gap-2">
          <button
            onClick={run}
            disabled={busy}
            className="rounded-lg bg-[#031632] px-4 py-2 text-[0.9375rem] font-bold text-white transition hover:bg-[#0a2450] disabled:opacity-50 dark:bg-blue-600 dark:hover:bg-blue-500"
          >
            {busy ? "Simulating..." : "Run simulation"}
          </button>
          <button
            onClick={reset}
            disabled={busy}
            className="rounded-lg border border-gray-300 px-3 py-2 text-[0.875rem] font-bold text-gray-600 transition hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            Reset
          </button>
        </div>
        {error && <p className="mt-2 text-[0.9375rem] font-semibold text-red-600 dark:text-red-400">{error}</p>}
      </Card>

      {result && (
        <>
          <Card className="border-red-300 bg-red-50 dark:border-red-800/60 dark:bg-red-950/30">
            <p className="text-[0.9375rem] font-bold text-red-700 dark:text-red-300">{result.notice}</p>
            <p className="mt-1 text-[0.8125rem] text-red-600 dark:text-red-400">
              The project record has not been modified. {result.method}
            </p>
          </Card>

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Card>
              <p className="text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">Current (actual data)</p>
              <p className="mt-1 font-mono text-2xl font-bold">{result.current.risk_score}<span className="text-sm text-gray-400">/100</span></p>
              <p className="text-[1rem] font-semibold text-gray-600 dark:text-gray-300">{result.current.risk_level}</p>
              <p className="mt-1 font-mono text-[0.875rem] text-gray-500">
                {formatMoney(result.current.sanctioned_amount)} sanctioned · {formatMoney(result.current.expenditure)} spent · {result.current.completion_percentage}%
              </p>
              <ul className="mt-2 space-y-1">
                {result.current.conditions.map((c) => (
                  <li key={c} className="text-[0.9375rem] leading-relaxed text-gray-500 dark:text-gray-400">• {c}</li>
                ))}
              </ul>
            </Card>
            <Card className="border-purple-300 dark:border-purple-800/60">
              <p className="text-[0.8125rem] font-bold uppercase tracking-wider text-purple-500">Simulated (not project data)</p>
              <p className="mt-1 font-mono text-2xl font-bold text-purple-700 dark:text-purple-300">
                {result.simulated.risk_score}<span className="text-sm text-gray-400">/100</span>
              </p>
              <p className="text-[1rem] font-semibold text-purple-700 dark:text-purple-300">{result.simulated.risk_level}</p>
              <p className="mt-1 font-mono text-[0.875rem] text-gray-500">
                {formatMoney(result.simulated.sanctioned_amount)} sanctioned · {formatMoney(result.simulated.expenditure)} spent · {result.simulated.completion_percentage}%
              </p>
              <ul className="mt-2 space-y-1">
                {result.simulated.conditions.length > 0
                  ? result.simulated.conditions.map((c) => (
                      <li key={c} className="text-[0.875rem] leading-relaxed text-purple-700 dark:text-purple-300">• {c}</li>
                    ))
                  : <li className="text-[0.9375rem] leading-relaxed text-gray-500 dark:text-gray-400">No risk conditions triggered.</li>}
              </ul>
            </Card>
          </div>

          <Card>
            <SectionTitle
              right={
                <Chip className={result.score_delta === 0 ? "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300"
                  : result.score_delta < 0 ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300"
                  : "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"}>
                  {result.score_delta > 0 ? `+${result.score_delta}` : result.score_delta} points
                </Chip>
              }
            >
              Simulation result
            </SectionTitle>
            <ul className="space-y-1">
              {result.explanation.map((n, i) => (
                <li key={i} className="text-[0.9375rem] leading-relaxed text-gray-600 dark:text-gray-300">• {n}</li>
              ))}
            </ul>
            {result.changed_inputs?.length > 0 && (
              <p className="mt-2 font-mono text-[0.8125rem] text-gray-400">simulated inputs: {result.changed_inputs.join(" · ")}</p>
            )}
            {!result.model_available && (
              <p className="mt-1 text-[0.8125rem] text-gray-400">ML model not loaded in this process — rule-based conditions only.</p>
            )}
          </Card>
        </>
      )}
    </div>
  )
}

/* ═══════════════ 3. Peer benchmarking ═══════════════ */

const SCOPE_OPTIONS = [
  { value: "constituency", label: "Constituency" },
  { value: "state", label: "State" },
  { value: "national", label: "National" },
]

export function PeerBenchmarkPanel({ projectId, onOpenProject }) {
  const [scope, setScope] = useState("state")
  const [typeFilter, setTypeFilter] = useState("")
  const [band, setBand] = useState("default")
  const [statusFilter, setStatusFilter] = useState("")
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    let alive = true
    setLoading(true); setError("")
    const params = { scope, band }
    if (typeFilter) params.project_type = typeFilter
    if (statusFilter) params.status = statusFilter
    getPeerBenchmark(projectId, params)
      .then((d) => alive && setData(d))
      .catch(() => alive && setError("Could not load the peer comparison."))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [projectId, scope, typeFilter, band, statusFilter])

  const fmtValue = (v, unit) => {
    if (v === null || v === undefined) return "N/A"
    if (unit === "₹") return formatMoney(v)
    if (unit === "points") return String(v)
    return `${v}%`
  }
  const fmtMetric = (m) => fmtValue(m.project_value, m.unit)
  const fmtPeer = (v, unit) => fmtValue(v, unit)

  return (
    <div className="space-y-3">
      <Card>
        <SectionTitle
          right={
            data && (
              <Chip className={
                data.reliability === "good" ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300"
                : data.reliability === "limited" ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                : "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
              }>
                {data.peer_count} comparable · {data.reliability}
              </Chip>
            )
          }
        >
          Compare with similar projects
        </SectionTitle>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div>
            <label className="block text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">Scope</label>
            <select value={scope} onChange={(e) => setScope(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-[0.875rem] text-gray-900 outline-none focus:border-blue-500 dark:border-gray-600 dark:bg-[#1f2937] dark:text-white">
              {SCOPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">Category</label>
            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-[0.875rem] text-gray-900 outline-none focus:border-blue-500 dark:border-gray-600 dark:bg-[#1f2937] dark:text-white">
              <option value="">Same category</option>
              <option value="all">All categories</option>
            </select>
          </div>
          <div>
            <label className="block text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">Value band</label>
            <select value={band} onChange={(e) => setBand(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-[0.875rem] text-gray-900 outline-none focus:border-blue-500 dark:border-gray-600 dark:bg-[#1f2937] dark:text-white">
              <option value="narrow">Narrow (0.7–1.4×)</option>
              <option value="default">Similar (0.3–3×)</option>
              <option value="all">Any value</option>
            </select>
          </div>
          <div>
            <label className="block text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">Status</label>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-[0.875rem] text-gray-900 outline-none focus:border-blue-500 dark:border-gray-600 dark:bg-[#1f2937] dark:text-white">
              <option value="">All statuses</option>
              <option value="Ongoing">Ongoing</option>
              <option value="Completed">Completed</option>
            </select>
          </div>
        </div>
      </Card>

      {loading && <Spinner label="Comparing with similar projects..." />}
      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-[0.9375rem] font-semibold text-red-700 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300">{error}</div>}

      {data && !loading && (
        <>
          <Card>
            <SectionTitle>This project vs comparable projects</SectionTitle>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="py-1.5 text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">Metric</th>
                    <th className="py-1.5 text-right text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">This project</th>
                    <th className="py-1.5 text-right text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">Peer median</th>
                    <th className="py-1.5 text-right text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">Peer average</th>
                  </tr>
                </thead>
                <tbody>
                  {data.metrics.map((m) => (
                    <tr key={m.metric} className="border-b border-gray-100 last:border-0 dark:border-gray-700/60">
                      <td className="py-1.5 text-[0.9375rem] leading-relaxed text-gray-600 dark:text-gray-300">{m.label}</td>
                      <td className="py-2 text-right font-mono text-[0.9375rem] font-bold">{fmtMetric(m)}</td>
                      <td className="py-2 text-right font-mono text-[0.9375rem] text-gray-500">{fmtPeer(m.peer_median, m.unit)}</td>
                      <td className="py-2 text-right font-mono text-[0.9375rem] text-gray-500">{fmtPeer(m.peer_average, m.unit)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data.interpretations?.length > 0 && (
              <div className="mt-3 space-y-1.5">
                {data.interpretations.map((t, i) => (
                  <p key={i} className="rounded-lg bg-gray-50 p-2 text-[0.9375rem] leading-relaxed text-gray-600 dark:bg-[#0f1524] dark:text-gray-300">{t}</p>
                ))}
              </div>
            )}
            <p className="mt-2 text-[0.8125rem] leading-relaxed text-gray-400">{data.methodology}</p>
            <p className="mt-1 text-[0.8125rem] font-semibold text-gray-400">{data.labels?.no_claim}</p>
          </Card>

          {data.comparable_projects?.length > 0 && (
            <Card>
              <SectionTitle>Comparable projects ({data.scope})</SectionTitle>
              <div className="space-y-1.5">
                {data.comparable_projects.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => onOpenProject && onOpenProject(p.id)}
                    className="w-full rounded-lg border border-gray-200 p-2 text-left transition hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-[#1f2937]"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-mono text-[0.8125rem] font-bold text-gray-400">#{p.id}</p>
                        <p className="truncate text-[1rem] font-semibold text-gray-800 dark:text-gray-200">{p.project_name || "Unnamed"}</p>
                        <p className="text-[0.8125rem] text-gray-500">{p.state} — {p.constituency || "N/A"}</p>
                      </div>
                      <span className={`flex-shrink-0 rounded px-2 py-0.5 text-[0.8125rem] font-bold ${
                        p.risk_level === "High" ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
                        : p.risk_level === "Medium" ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                        : "bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-300"
                      }`}>{p.risk_level || "N/A"}</span>
                    </div>
                    <div className="mt-1 grid grid-cols-4 gap-2">
                      <span className="font-mono text-[0.8125rem] text-gray-500">S {formatMoney(p.sanctioned_amount)}</span>
                      <span className="font-mono text-[0.8125rem] text-gray-500">E {formatMoney(p.expenditure)}</span>
                      <span className="font-mono text-[0.8125rem] text-gray-500">U {p.utilization_pct ?? "N/A"}%</span>
                      <span className="font-mono text-[0.8125rem] text-gray-500">P {p.completion_percentage}%</span>
                    </div>
                  </button>
                ))}
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}

/* ═══════════════ 7 + 8. Audit case + escalation draft ═══════════════ */

export function AuditCasePanel({ projectId }) {
  const { user, hasRole } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [copied, setCopied] = useState(false)
  const [caseSaved, setCaseSaved] = useState(false)
  const [caseSaveMsg, setCaseSaveMsg] = useState("")
  const [invStarted, setInvStarted] = useState(false)
  const [invMsg, setInvMsg] = useState("")

  useEffect(() => { setData(null); setError("") }, [projectId])

  const generate = async () => {
    setLoading(true); setError("")
    try {
      const caseData = await getAuditCase(projectId)
      setData(caseData)
    } catch (e) {
      setError(e?.message || "Could not generate the audit case.")
    } finally { setLoading(false) }
  }

  const copy = async () => {
    if (!data?.escalation_draft?.body) return
    try {
      await navigator.clipboard.writeText(data.escalation_draft.body)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setError("Clipboard not available in this browser.")
    }
  }

  const download = () => {
    if (!data) return
    const blob = new Blob([data.escalation_draft.body], { type: "text/plain;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${data.case_id}-escalation-draft.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const canManageCases = hasRole("auditor")
  const canInvestigate = hasRole("analyst")

  const handleSaveCase = async () => {
    setCaseSaveMsg("")
    try {
      await saveAuditCase(projectId)
      setCaseSaved(true)
      setCaseSaveMsg("Saved to My Audit Cases")
    } catch (e) { setCaseSaveMsg(e.message || "Could not save the case") }
  }

  const handleStartInvestigation = async () => {
    setInvMsg("")
    try {
      await createMyInvestigation(projectId)
      setInvStarted(true)
      setInvMsg("Investigation added to My Investigations")
    } catch (e) { setInvMsg(e.message || "Could not start the investigation") }
  }

  return (
    <div className="space-y-3">
      <Card>
        <SectionTitle>Automatic audit case generator</SectionTitle>
        <p className="text-[1rem] leading-relaxed text-gray-600 dark:text-gray-300">
          Generates a structured case from this project's recorded values, risk/anomaly results, peer comparison and
          missing evidence, together with a review-ready escalation draft.
        </p>
        <button
          onClick={generate}
          disabled={loading}
          className="mt-3 rounded-lg bg-[#031632] px-4 py-2 text-[0.9375rem] font-bold text-white transition hover:bg-[#0a2450] disabled:opacity-50 dark:bg-blue-600 dark:hover:bg-blue-500"
        >
          {loading ? "Generating..." : "CREATE AUDIT CASE"}
        </button>
        {error && <p className="mt-2 text-[0.9375rem] font-semibold text-red-600 dark:text-red-400">{error}</p>}
      </Card>

      {data && (
        <>
          <Card>
            <SectionTitle right={<Chip className={TIER_STYLE[data.priority.tier] || TIER_STYLE.P4}>{data.priority.tier} — {data.priority.tier_label}</Chip>}>
              {data.case_id}
            </SectionTitle>
            <div className="grid grid-cols-2 gap-2">
              {[
                ["Work", data.project.project_name || "Not recorded"],
                ["Location", `${data.project.constituency || "N/A"}, ${data.project.state || "N/A"}`],
                ["Category", data.project.project_type || "Not recorded"],
                ["Status", data.project.status || "Not recorded"],
                ["Sanctioned", data.financials.sanctioned_display],
                ["Expenditure", data.financials.expenditure_display],
                ["Reported progress", `${data.financials.completion_percentage}%`],
                ["Utilization", data.financials.utilization_pct !== null ? `${data.financials.utilization_pct}%` : "N/A"],
              ].map(([k, v]) => (
                <div key={k} className="rounded-lg bg-gray-50 p-2 dark:bg-[#0f1524]">
                  <p className="text-[0.8125rem] font-bold uppercase tracking-wider text-gray-400">{k}</p>
                  <p className="text-[1rem] font-semibold text-gray-800 dark:text-gray-200">{v}</p>
                </div>
              ))}
            </div>
            <p className="mt-2 font-mono text-[0.8125rem] text-gray-400">generated {data.generated_at?.replace("T", " ").slice(0, 19)}</p>
          </Card>

          <Card>
            <SectionTitle>Triggered anomalies</SectionTitle>
            <p className="text-[1rem] font-semibold text-gray-800 dark:text-gray-200">Main anomaly: {data.main_anomaly}</p>
            <ul className="mt-1.5 space-y-1">
              {data.risk.reasons?.map((r, i) => (
                <li key={i} className="flex items-start gap-1.5 text-[0.9375rem] leading-relaxed text-gray-600 dark:text-gray-300">
                  <span className="mt-0.5 text-red-500">•</span><span>{r}</span>
                </li>
              ))}
            </ul>
            {data.risk.ml_anomaly && (
              <p className="mt-1.5 text-[0.875rem] font-semibold text-purple-600 dark:text-purple-400">
                ✨ ML model finding: flagged as a statistical outlier.
              </p>
            )}
          </Card>

          <Card>
            <SectionTitle>Evidence available / missing</SectionTitle>
            <p className="text-[0.9375rem] leading-relaxed text-gray-500 dark:text-gray-400">Available — {
              data.evidence.items.filter((i) => i.status === "available").map((i) => i.label).join("; ") || "None beyond the project record."
            }</p>
            <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-gray-500 dark:text-gray-400">Missing — {
              data.evidence.missing_items.map((i) => i.label).join("; ") || "None identified."
            }</p>
          </Card>

          <Card>
            <SectionTitle>Recommended verification actions</SectionTitle>
            <ul className="space-y-1">
              {data.recommended_verification_actions.map((a, i) => (
                <li key={i} className="flex items-start gap-1.5 text-[0.9375rem] leading-relaxed text-gray-600 dark:text-gray-300">
                  <span className="mt-0.5 text-blue-600 dark:text-blue-400">→</span><span>{a}</span>
                </li>
              ))}
            </ul>
          </Card>

          <Card className="border-amber-200 bg-amber-50/40 dark:border-amber-900/40 dark:bg-amber-950/20">
            <SectionTitle>Suggested review level</SectionTitle>
            <p className="text-[1rem] font-semibold text-amber-700 dark:text-amber-300">{data.review_level.level}</p>
            <p className="mt-0.5 text-[0.875rem] text-amber-600 dark:text-amber-400">{data.review_level.basis}</p>
          </Card>

          <Card>
            <SectionTitle
              right={<Chip className="bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300">{data.escalation_draft.status_label}</Chip>}
            >
              Report / escalate
            </SectionTitle>
            <p className="text-[1rem] font-semibold text-gray-800 dark:text-gray-200">{data.escalation_draft.subject}</p>
            <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-gray-50 p-2.5 font-sans text-[0.875rem] leading-relaxed text-gray-600 dark:bg-[#0f1524] dark:text-gray-300">
{data.escalation_draft.body}
            </pre>
            <div className="mt-2 flex flex-wrap gap-2">
              <button onClick={generate} className="rounded-lg border border-gray-300 px-3 py-1.5 text-[0.875rem] font-bold text-gray-700 transition hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800">Generate Report</button>
              <button onClick={copy} className="rounded-lg border border-gray-300 px-3 py-1.5 text-[0.875rem] font-bold text-gray-700 transition hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800">{copied ? "Copied ✓" : "Copy Report"}</button>
              <button onClick={download} className="rounded-lg border border-gray-300 px-3 py-1.5 text-[0.875rem] font-bold text-gray-700 transition hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800">Download Report</button>
              {user && canManageCases && (
                <button onClick={handleSaveCase} className={`rounded-lg px-3 py-1.5 text-[0.875rem] font-bold text-white transition ${caseSaved ? "bg-green-600 hover:bg-green-500" : "bg-[#031632] hover:bg-[#0a2450] dark:bg-blue-600 dark:hover:bg-blue-500"}`}>
                  {caseSaved ? "✓ Case saved" : "Save case"}
                </button>
              )}
              {user && canInvestigate && (
                <button onClick={handleStartInvestigation} disabled={invStarted} className={`rounded-lg px-3 py-1.5 text-[0.875rem] font-bold transition disabled:opacity-60 ${invStarted ? "border border-green-400 bg-green-50 text-green-700 dark:border-green-700 dark:bg-green-950/40 dark:text-green-300" : "border border-gray-300 text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800"}`}>
                  {invStarted ? "✓ In My Investigations" : "Track investigation"}
                </button>
              )}
            </div>
            {(caseSaveMsg || invMsg) && (
              <p className={`mt-1.5 text-[0.8125rem] font-semibold ${
                (caseSaved || invStarted) ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
              }`}>
                {caseSaveMsg || invMsg}
              </p>
            )}
            {!user && (
              <p className="mt-1.5 text-[0.8125rem] text-gray-400">Sign in to save this case or track an investigation in your workspace.</p>
            )}
            <p className="mt-2 text-[0.8125rem] leading-relaxed text-gray-400">{data.escalation_draft.submission_note}</p>
          </Card>

          {data.disclaimers?.length > 0 && (
            <Card className="bg-gray-50 dark:bg-[#0f1524]">
              <ul className="space-y-1">
                {data.disclaimers.map((d, i) => (
                  <li key={i} className="text-[0.8125rem] leading-relaxed text-gray-400">• {d}</li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
    </div>
  )
}

/* Small re-exports used by the project drawer */
export { Card as AuditCard, SectionTitle as AuditSectionTitle, Spinner as AuditSpinner }
