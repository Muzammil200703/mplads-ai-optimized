import { useEffect, useState } from "react"
import { getProjectDetail, getSimilarProjects } from "../services/api"

function formatMoney(value) {
  const number = Number(value || 0)
  if (number >= 10000000) return `₹${(number / 10000000).toFixed(2)} Cr`
  if (number >= 100000) return `₹${(number / 100000).toFixed(2)} L`
  return `₹${number.toLocaleString("en-IN")}`
}

// Determine auditor-friendly badges from risk data
function getBadges(risk, project) {
  const badges = []
  if (!risk) return badges
  const reasons = risk.reasons || []
  const sanctioned = Number(project.sanctioned_amount || 0)
  const expenditure = Number(project.expenditure || 0)
  const completion = Number(project.completion_percentage || 0)

  if (risk.risk_level === "High") badges.push({ label: "HIGH RISK", color: "red" })
  else if (risk.risk_level === "Medium") badges.push({ label: "MEDIUM RISK", color: "amber" })

  if (reasons.some((r) => r.includes("exceeds sanctioned")))
    badges.push({ label: "COST OVERRUN", color: "red", detail: `Expenditure ₹${formatMoney(expenditure)} exceeds sanctioned ₹${formatMoney(sanctioned)} by ₹${formatMoney(Math.max(0, expenditure - sanctioned))}` })
  if (reasons.some((r) => r.includes("High expenditure")))
    badges.push({ label: "PROGRESS MISMATCH", color: "orange", detail: `Fund utilization at ${sanctioned > 0 ? ((expenditure / sanctioned) * 100).toFixed(0) : 0}% but progress only ${completion}%` })
  if (reasons.some((r) => r.includes("0% physical")))
    badges.push({ label: "ZERO PROGRESS", color: "red", detail: `₹${formatMoney(expenditure)} spent with 0% physical progress` })
  if (reasons.some((r) => r.includes("completed but")))
    badges.push({ label: "STATUS INCONSISTENCY", color: "amber", detail: `Marked Completed but progress is ${completion}%` })
  if (reasons.some((r) => r.includes("ML") || r.includes("ml")))
    badges.push({ label: "ML OUTLIER", color: "purple", detail: "Statistical outlier detected by ML model" })

  return badges
}

// Generate audit recommendation based on risk reasons
function getAuditRecommendation(reasons) {
  if (!reasons || reasons.length === 0) return null
  const recommendations = []
  for (const reason of reasons) {
    const r = reason.toLowerCase()
    if (r.includes("exceeds sanctioned"))
      recommendations.push("Review expenditure records and approved cost estimates. Verify whether additional sanctions were obtained for the excess amount.")
    else if (r.includes("high expenditure"))
      recommendations.push("Verify physical progress against expenditure. Request site inspection and progress documentation.")
    else if (r.includes("0% physical"))
      recommendations.push("Verify whether work has commenced. Review expenditure/disbursement records and contractor agreements.")
    else if (r.includes("completed but"))
      recommendations.push("Verify project status against actual completion. Review completion certificates and final inspection reports.")
    else if (r.includes("high-value project"))
      recommendations.push("Review execution timeline and identify causes of delay. Assess whether project requires administrative intervention.")
    else if (r.includes("high completion"))
      recommendations.push("Verify physical progress records against financial data. Check for data recording errors.")
    else if (r.includes("very low fund"))
      recommendations.push("Review fund utilization and project execution status. Assess whether project should be escalated.")
    else if (r.includes("ml"))
      recommendations.push("Review the project against comparable projects to determine whether the unusual pattern is legitimate.")
  }
  return recommendations
}

function ProjectDetail({ projectId, onClose }) {
  const [detail, setDetail] = useState(null)
  const [similar, setSimilar] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadingSimilar, setLoadingSimilar] = useState(false)
  const [activeTab, setActiveTab] = useState("overview")

  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    setDetail(null)
    setSimilar(null)
    setActiveTab("overview")

    Promise.all([
      getProjectDetail(projectId),
      getSimilarProjects(projectId, 5).catch(() => null),
    ]).then(([d, s]) => {
      setDetail(d)
      setSimilar(s)
    }).catch((err) => {
      console.error("Detail load error:", err)
    }).finally(() => {
      setLoading(false)
    })
  }, [projectId])

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-2xs" onClick={onClose}>
        <div className="rounded-2xl bg-white p-12 text-center shadow-2xl dark:bg-[#1f2937]" onClick={(e) => e.stopPropagation()}>
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-600 border-r-transparent" />
          <p className="mt-3 text-sm font-medium">Loading project details...</p>
        </div>
      </div>
    )
  }

  if (!detail) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-2xs" onClick={onClose}>
        <div className="rounded-2xl bg-white p-8 text-center shadow-2xl dark:bg-[#1f2937]" onClick={(e) => e.stopPropagation()}>
          <p className="text-sm text-gray-500">Project not found.</p>
          <button onClick={onClose} className="mt-4 rounded-lg bg-[#031632] px-4 py-2 text-xs font-bold text-white">Close</button>
        </div>
      </div>
    )
  }

  const proj = detail.project
  const risk = detail.risk
  const sanctioned = Number(proj.sanctioned_amount || 0)
  const expenditure = Number(proj.expenditure || 0)
  const completion = Number(proj.completion_percentage || 0)
  const utilization = sanctioned > 0 ? (expenditure / sanctioned * 100) : 0
  const remaining = Math.max(0, sanctioned - expenditure)
  const discrepancy = utilization - completion
  const badges = getBadges(risk, proj)
  const recommendations = getAuditRecommendation(risk?.reasons)

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-2xs transition-opacity" onClick={onClose}>
      <div className="absolute right-0 top-0 h-full w-full sm:w-[560px] max-w-[92vw] overflow-y-auto border-l border-gray-200 bg-white p-4 sm:p-6 text-gray-900 shadow-2xl dark:border-gray-700 dark:bg-[#1f2937] dark:text-white" onClick={(e) => e.stopPropagation()}>

        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <span className="rounded bg-blue-100 px-2.5 py-1 font-mono text-xs font-bold text-blue-800 dark:bg-blue-900/60 dark:text-blue-200">#{proj.id}</span>
            {proj.status && (
              <span className={`rounded px-2 py-0.5 text-xs font-bold ${
                proj.status === "Completed" ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300"
                : proj.status === "Ongoing" ? "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                : "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
              }`}>{proj.status}</span>
            )}
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700">✕</button>
        </div>

        <h2 className="mt-3 text-lg font-bold leading-snug">{proj.project_name || "Unnamed Project"}</h2>

        {/* Location */}
        <div className="mt-2 grid grid-cols-2 gap-2">
          <span className="text-xs text-gray-500">📍 {proj.state || "N/A"}</span>
          <span className="text-xs text-gray-500">🏛 {proj.constituency || "N/A"}</span>
        </div>

        {/* Badges */}
        {badges.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {badges.map((b, i) => (
              <span key={i} title={b.detail} className={`rounded px-2 py-0.5 text-[10px] font-bold cursor-help ${
                b.color === "red" ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
                : b.color === "amber" ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                : b.color === "orange" ? "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300"
                : b.color === "purple" ? "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300"
                : "bg-gray-100 text-gray-600 dark:bg-gray-700"
              }`}>{b.label}</span>
            ))}
          </div>
        )}

        {/* Tabs */}
        <div className="mt-5 flex gap-1 border-b border-gray-200 dark:border-gray-700">
          {[
            { id: "overview", label: "Overview" },
            { id: "financial", label: "Financial" },
            { id: "risk", label: "Risk & Audit" },
            ...(similar?.similar_projects?.length > 0 ? [{ id: "similar", label: "Similar" }] : []),
          ].map((tab) => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-2 text-xs font-bold transition ${activeTab === tab.id ? "border-b-2 border-blue-600 text-blue-600 dark:text-blue-400" : "text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"}`}>
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="mt-4 space-y-4">
          {activeTab === "overview" && (
            <>
              <InfoGrid items={[
                { label: "State", value: proj.state || "Not available" },
                { label: "Constituency", value: proj.constituency || "Not available" },
                { label: "Category", value: proj.project_type || "Not available" },
                { label: "Status", value: proj.status || "Not available" },
              ]} />
              <ProgressCard completion={completion} />
            </>
          )}

          {activeTab === "financial" && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <MetricCard label="Sanctioned" value={formatMoney(sanctioned)} color="blue" />
                <MetricCard label="Expenditure" value={formatMoney(expenditure)} color="purple" />
                <MetricCard label="Remaining" value={formatMoney(remaining)} color="green" />
                <MetricCard label="Utilization" value={`${utilization.toFixed(1)}%`} color={utilization > 100 ? "red" : "blue"} />
              </div>
              {/* Utilization Bar */}
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-[#111827]">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-gray-500">Fund Utilization</span>
                  <span className="font-mono font-bold">{utilization.toFixed(1)}%</span>
                </div>
                <div className="mt-2 h-3 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                  <div className={`h-full rounded-full transition-all duration-500 ${utilization > 100 ? "bg-red-500" : "bg-blue-600"}`}
                    style={{ width: `${Math.min(100, utilization)}%` }} />
                </div>
                <div className="mt-1.5 flex justify-between text-[10px] text-gray-400">
                  <span>Spent: {formatMoney(expenditure)}</span>
                  <span>Remaining: {formatMoney(remaining)}</span>
                </div>
              </div>
              {/* Expenditure vs Progress */}
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-[#111827]">
                <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-gray-400">Expenditure vs Physical Progress</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-[10px] font-bold text-gray-400">Financial Utilization</p>
                    <p className="font-mono text-lg font-bold">{utilization.toFixed(1)}%</p>
                    <div className="mt-1 h-2 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                      <div className="h-full rounded-full bg-purple-600" style={{ width: `${Math.min(100, utilization)}%` }} />
                    </div>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold text-gray-400">Physical Progress</p>
                    <p className="font-mono text-lg font-bold">{completion}%</p>
                    <div className="mt-1 h-2 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                      <div className="h-full rounded-full bg-blue-600" style={{ width: `${Math.min(100, completion)}%` }} />
                    </div>
                  </div>
                </div>
                {Math.abs(discrepancy) > 10 && (
                  <div className={`mt-3 rounded-lg p-2.5 text-xs font-semibold ${
                    discrepancy > 0
                      ? "border border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300"
                      : "border border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900/60 dark:bg-blue-950/30 dark:text-blue-300"
                  }`}>
                    {discrepancy > 0
                      ? `⚠ Expenditure-progress mismatch: Financial utilization (${utilization.toFixed(0)}%) exceeds physical progress (${completion}%) by ${Math.abs(discrepancy).toFixed(0)} percentage points.`
                      : `Physical progress (${completion}%) exceeds financial utilization (${utilization.toFixed(0)}%) by ${Math.abs(discrepancy).toFixed(0)} percentage points.`}
                  </div>
                )}
              </div>
              {/* Flag suspicious cases */}
              {expenditure > sanctioned && sanctioned > 0 && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300">
                  ⚠ Cost overrun: Expenditure exceeds sanctioned amount by {formatMoney(expenditure - sanctioned)}
                </div>
              )}
              {expenditure > 0 && completion === 0 && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300">
                  ⚠ Zero progress: {formatMoney(expenditure)} spent but physical progress is 0%
                </div>
              )}
            </>
          )}

          {activeTab === "risk" && (
            <>
              {/* Risk Score */}
              {risk && (
                <div className={`rounded-xl border p-4 ${
                  risk.risk_level === "High" ? "border-red-200 bg-red-50/60 dark:border-red-900/60 dark:bg-red-950/30"
                  : risk.risk_level === "Medium" ? "border-amber-200 bg-amber-50/60 dark:border-amber-900/60 dark:bg-amber-950/30"
                  : "border-green-200 bg-green-50/60 dark:border-green-900/60 dark:bg-green-950/30"
                }`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-[10px] font-bold uppercase text-gray-500">Risk Level</p>
                      <p className={`text-lg font-bold ${
                        risk.risk_level === "High" ? "text-red-600 dark:text-red-400"
                        : risk.risk_level === "Medium" ? "text-amber-600 dark:text-amber-400"
                        : "text-green-600 dark:text-green-400"
                      }`}>{risk.risk_level || "None"}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-[10px] font-bold uppercase text-gray-500">Score</p>
                      <p className="font-mono text-2xl font-bold">{risk.risk_score}<span className="text-sm text-gray-400">/100</span></p>
                    </div>
                  </div>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                    <div className={`h-full rounded-full ${risk.risk_level === "High" ? "bg-red-500" : risk.risk_level === "Medium" ? "bg-amber-500" : "bg-green-500"}`}
                      style={{ width: `${Math.min(100, risk.risk_score)}%` }} />
                  </div>
                </div>
              )}

              {/* Triggered Rules */}
              {risk?.reasons && risk.reasons.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Triggered Rules ({risk.reasons.length})</h4>
                  {risk.reasons.map((reason, i) => (
                    <div key={i} className="rounded-lg border border-red-100 bg-red-50/50 p-3 dark:border-red-900/40 dark:bg-red-950/20">
                      <p className="text-xs font-semibold text-red-700 dark:text-red-400">{reason}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Audit Insight Summary */}
              {risk && risk.risk_level !== "None" && risk.risk_level !== "Low" && (
                <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4 dark:border-blue-900/40 dark:bg-blue-950/20">
                  <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-blue-700 dark:text-blue-300">Audit Insight Summary</h4>
                  <div className="space-y-2 text-xs">
                    <p><span className="font-bold">Risk:</span> {risk.risk_level} (Score: {risk.risk_score}/100)</p>
                    <p><span className="font-bold">Key Finding:</span> {formatMoney(expenditure)} has been spent against {formatMoney(sanctioned)} sanctioned while physical progress is {completion}%.</p>
                    {discrepancy > 10 && (
                      <p><span className="font-bold">Primary Concern:</span> Expenditure is disproportionately high relative to reported physical progress (utilization {utilization.toFixed(0)}% vs progress {completion}%).</p>
                    )}
                    {expenditure > sanctioned && sanctioned > 0 && (
                      <p><span className="font-bold">Primary Concern:</span> Expenditure exceeds sanctioned amount by {formatMoney(expenditure - sanctioned)}.</p>
                    )}
                    {expenditure > 0 && completion === 0 && (
                      <p><span className="font-bold">Primary Concern:</span> Financial disbursements have been made but no physical progress is recorded.</p>
                    )}
                  </div>
                </div>
              )}

              {/* Recommended Audit Actions */}
              {recommendations && recommendations.length > 0 && (
                <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-4 dark:border-amber-900/40 dark:bg-amber-950/20">
                  <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-amber-700 dark:text-amber-300">Recommended Audit Actions</h4>
                  <div className="space-y-1.5">
                    {recommendations.map((rec, i) => (
                      <div key={i} className="flex items-start gap-2 text-xs text-amber-800 dark:text-amber-200">
                        <span className="mt-0.5">→</span>
                        <span>{rec}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {risk?.ml_anomaly && (
                <div className="rounded-lg border border-purple-200 bg-purple-50 p-3 dark:border-purple-900/60 dark:bg-purple-950/30">
                  <p className="text-xs font-bold text-purple-700 dark:text-purple-300">✨ ML Statistical Outlier Detected</p>
                  <p className="mt-1 text-[10px] text-purple-600 dark:text-purple-400">Isolation Forest model flagged this project as a multi-dimensional statistical anomaly.</p>
                </div>
              )}
            </>
          )}

          {activeTab === "similar" && similar && (
            <>
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-[#111827]">
                <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Comparison Criteria</p>
                <p className="mt-1 text-xs">
                  State: <strong>{similar.criteria.state}</strong> | Type: <strong>{similar.criteria.project_type}</strong> | Range: <strong>{similar.criteria.sanctioned_range}</strong>
                </p>
              </div>
              {similar.similar_projects.length > 0 ? (
                <div className="space-y-2">
                  {similar.similar_projects.map((sp) => (
                    <div key={sp.id} className="rounded-lg border border-gray-200 bg-gray-50/50 p-3 dark:border-gray-700 dark:bg-[#111827]">
                      <div className="flex items-start justify-between">
                        <div>
                          <span className="font-mono text-[10px] font-bold text-gray-400">#{sp.id}</span>
                          <p className="text-xs font-semibold">{sp.project_name}</p>
                          <p className="text-[10px] text-gray-500">{sp.constituency || "N/A"}</p>
                        </div>
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                          sp.risk_level === "High" ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
                          : sp.risk_level === "Medium" ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                          : "bg-gray-100 text-gray-600 dark:bg-gray-700"
                        }`}>{sp.risk_level} ({sp.risk_score})</span>
                      </div>
                      <div className="mt-2 grid grid-cols-4 gap-2 text-[10px]">
                        <div><p className="text-gray-400">Sanctioned</p><p className="font-bold">{formatMoney(sp.sanctioned_amount)}</p></div>
                        <div><p className="text-gray-400">Spent</p><p className="font-bold">{formatMoney(sp.expenditure)}</p></div>
                        <div><p className="text-gray-400">Utilization</p><p className="font-bold">{sp.sanctioned_amount > 0 ? ((sp.expenditure / sp.sanctioned_amount) * 100).toFixed(0) : 0}%</p></div>
                        <div><p className="text-gray-400">Progress</p><p className="font-bold">{sp.completion_percentage}%</p></div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-gray-500">No similar projects found matching the criteria.</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// Sub-components
function InfoGrid({ items }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {items.map((item) => (
        <div key={item.label} className="rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-[#111827]">
          <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{item.label}</p>
          <p className="mt-0.5 text-sm font-semibold">{item.value}</p>
        </div>
      ))}
    </div>
  )
}

function MetricCard({ label, value, color }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-[#111827]">
      <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{label}</p>
      <p className={`mt-1 font-mono text-lg font-bold text-${color}-600 dark:text-${color}-400`}>{value}</p>
    </div>
  )
}

function ProgressCard({ completion }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-[#111827]">
      <div className="flex items-center justify-between">
        <span className="text-sm font-bold">Physical Completion</span>
        <span className="font-mono text-lg font-bold text-blue-600 dark:text-blue-400">{completion}%</span>
      </div>
      <div className="mt-2 h-4 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
        <div className={`h-full rounded-full transition-all duration-500 ${
          completion >= 80 ? "bg-green-500" : completion >= 40 ? "bg-blue-600" : completion > 0 ? "bg-amber-500" : "bg-red-500"
        }`} style={{ width: `${Math.min(100, completion)}%` }} />
      </div>
      <p className="mt-2 text-xs text-gray-500">
        {completion >= 80 ? "On track" : completion >= 40 ? "Moderate progress" : completion > 0 ? "Early stage" : "No progress reported"}
      </p>
    </div>
  )
}

export default ProjectDetail
