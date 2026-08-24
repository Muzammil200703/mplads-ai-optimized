import { useEffect, useState } from "react"
import {
  getDashboardOverview,
  getAINarrativeInsights,
  getDashboardStates,
  getAnomaliesSummary,
} from "../services/api"

function formatCrore(amount) {
  const crore = Number(amount || 0) / 10000000
  return crore.toLocaleString("en-IN", {
    maximumFractionDigits: 2,
  })
}

function Overview({ darkMode, onDrillDown }) {
  const [overview, setOverview] = useState(null)
  const [narratives, setNarratives] = useState([])
  const [stateData, setStateData] = useState([])
  const [anomaliesSummary, setAnomaliesSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [backendConnected, setBackendConnected] = useState(false)

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true)
        setError("")

        const [ovRes, narrRes, statesRes, anomRes] = await Promise.allSettled([
          getDashboardOverview(),
          getAINarrativeInsights(),
          getDashboardStates(),
          getAnomaliesSummary(),
        ])

        if (ovRes.status === "fulfilled") {
          setOverview(ovRes.value)
          setBackendConnected(true)
        }

        if (narrRes.status === "fulfilled" && narrRes.value?.insights) {
          setNarratives(narrRes.value.insights)
        }

        if (statesRes.status === "fulfilled" && Array.isArray(statesRes.value)) {
          setStateData(statesRes.value)
        }

        if (anomRes.status === "fulfilled") {
          setAnomaliesSummary(anomRes.value)
        }

        if (ovRes.status === "rejected" && statesRes.status === "rejected") {
          setBackendConnected(false)
          setError("Unable to connect to backend server at http://127.0.0.1:8000. Please start the backend.")
        }
      } catch (err) {
        console.error("Overview error:", err)
        setError("Error loading dashboard metrics.")
        setBackendConnected(false)
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [])

  const pageClasses = darkMode
    ? "bg-[#111827] text-[#f3f4f6]"
    : "bg-[#f8fafc] text-[#151c27]"

  const cardClasses = darkMode
    ? "bg-[#1f2937] border-[#374151]"
    : "bg-white border-[#d9dee8]"

  const mutedText = darkMode ? "text-[#9ca3af]" : "text-[#64748b]"

  const topStates = stateData.slice(0, 6)
  const maxProjectsInState = topStates.length > 0
    ? Math.max(...topStates.map((s) => s.total_projects))
    : 1

  const totalWorks = overview?.total_projects || 0
  const sanctionedAmount = overview?.total_sanctioned_amount || overview?.total_allocated_amount || 0
  const expenditure = overview?.total_expenditure || 0
  const highRiskWorks = anomaliesSummary?.high_risk || 0
  const completedWorks = overview?.completed_projects || 0
  const utilization = overview?.utilization_percentage || 0

  if (loading) {
    return (
      <div className={`min-h-screen p-4 sm:p-6 ${pageClasses}`}>
        <h1 className="text-xl sm:text-2xl md:text-3xl font-bold">Executive Overview</h1>
        <div className={`mt-6 rounded-xl border p-12 text-center ${cardClasses}`}>
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-600 border-r-transparent" />
          <p className={`mt-3 font-medium ${mutedText}`}>Loading live MPLADS intelligence from backend...</p>
        </div>
      </div>
    )
  }

  return (
    <div className={`min-h-screen p-4 sm:p-6 transition-colors duration-200 ${pageClasses}`}>
      {/* HEADER */}
      <div className="mb-4 sm:mb-6 flex flex-col gap-3 sm:gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl md:text-3xl font-bold">Executive Overview</h1>
          <p className={`mt-1 sm:mt-2 text-sm sm:text-base ${mutedText}`}>
            AI-driven monitoring of MPLADS allocations, physical progress, and financial anomalies.
          </p>
        </div>

        <div className="flex flex-wrap gap-2 sm:gap-3">
          <button
            onClick={() => window.print()}
            className={`rounded-lg border px-3 sm:px-5 py-2 sm:py-2.5 text-xs sm:text-sm font-semibold transition hover:opacity-80 ${cardClasses}`}
          >
            ↓ Export Overview
          </button>
          <div className="flex items-center gap-2 rounded-lg bg-blue-500/10 px-3 sm:px-4 py-1.5 sm:py-2 text-xs font-bold text-blue-600 dark:text-blue-300">
            <span>●</span> Live Backend Data
          </div>
        </div>
      </div>

      {/* ERROR NOTICE */}
      {error && (
        <div className="mb-6 rounded-xl border border-red-500/40 bg-red-500/10 p-4 text-sm font-semibold text-red-600 dark:text-red-400">
          ⚠ {error}
        </div>
      )}

      {/* AI NARRATIVE INSIGHTS BANNER */}
      {narratives.length > 0 && (
        <div className="mb-7 rounded-xl border border-blue-200 bg-gradient-to-r from-blue-50 via-white to-blue-50/50 p-5 shadow-xs dark:border-blue-900/60 dark:from-[#1e293b] dark:via-[#1f2937] dark:to-[#172033]">
          <div className="mb-3 flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-600 text-xs text-white">✨</span>
            <h3 className="text-xs font-bold uppercase tracking-wider text-blue-950 dark:text-blue-200">
              AI Audit Insights & Discrepancy Findings
            </h3>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
            {narratives.map((item, idx) => (
              <div
                key={idx}
                className="rounded-lg border border-blue-100 bg-white/80 p-3 shadow-2xs dark:border-gray-700/60 dark:bg-[#111827]/70"
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm">
                    {item.type === "risk" ? "⚠️" : item.type === "financial" ? "💰" : item.type === "completion" ? "🏗️" : "📍"}
                  </span>
                  <span className="text-xs font-bold text-gray-900 dark:text-white">
                    {item.title}
                  </span>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-gray-600 dark:text-gray-300">
                  {item.message}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* CORE STAT CARDS */}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
        {/* TOTAL WORKS */}
        <div className={`rounded-xl border p-6 shadow-xs cursor-pointer transition hover:shadow-md ${cardClasses}`} onClick={() => onDrillDown && onDrillDown("Projects")}>
          <div className="flex items-start justify-between">
            <div>
              <p className={`text-xs font-bold uppercase tracking-wider ${mutedText}`}>
                TOTAL MONITORED WORKS
              </p>
              <h2 className="mt-3 text-2xl sm:text-3xl font-bold font-mono">
                {totalWorks.toLocaleString("en-IN")}
              </h2>
            </div>
            <div className="rounded-xl bg-blue-500/10 p-3 text-2xl">
              🏗️
            </div>
          </div>
          <p className={`mt-4 text-xs ${mutedText}`}>
            <span className="font-semibold text-green-500">✓ {overview?.completed_projects || 0}</span> Completed works
          </p>
        </div>

        {/* SANCTIONED AMOUNT */}
        <div className={`rounded-xl border p-6 shadow-xs ${cardClasses}`}>
          <div className="flex items-start justify-between">
            <div>
              <p className={`text-xs font-bold uppercase tracking-wider ${mutedText}`}>
                SANCTIONED ALLOCATION
              </p>
              <h2 className="mt-3 text-xl sm:text-2xl md:text-3xl font-bold font-mono">
                ₹{formatCrore(sanctionedAmount)} <span className="text-sm sm:text-base font-sans text-gray-500 font-normal">Cr</span>
              </h2>
            </div>
            <div className="rounded-xl bg-amber-500/10 p-3 text-2xl">
              💰
            </div>
          </div>
          <p className={`mt-4 text-xs ${mutedText}`}>
            Across <span className="font-semibold">{overview?.total_states || stateData.length}</span> States & UTs
          </p>
        </div>

        {/* TOTAL EXPENDITURE */}
        <div className={`rounded-xl border p-6 shadow-xs ${cardClasses}`}>
          <div className="flex items-start justify-between">
            <div>
              <p className={`text-xs font-bold uppercase tracking-wider ${mutedText}`}>
                CUMULATIVE EXPENDITURE
              </p>
              <h2 className="mt-3 text-xl sm:text-2xl md:text-3xl font-bold font-mono">
                ₹{formatCrore(expenditure)} <span className="text-sm sm:text-base font-sans text-gray-500 font-normal">Cr</span>
              </h2>
            </div>
            <div className="rounded-xl bg-purple-500/10 p-3 text-2xl">
              💳
            </div>
          </div>
          <p className={`mt-4 text-xs ${mutedText}`}>
            <span className="font-semibold text-blue-500">{utilization}%</span> Fund utilization
          </p>
        </div>

        {/* HIGH RISK WORKS */}
        <div className={`rounded-xl border border-l-4 border-l-red-500 p-6 shadow-xs cursor-pointer transition hover:shadow-md ${cardClasses}`} onClick={() => onDrillDown && onDrillDown("Risk Center", { risk_level: "High" })}>
          <div className="flex items-start justify-between">
            <div>
              <p className={`text-xs font-bold uppercase tracking-wider ${mutedText}`}>
                HIGH-RISK ANOMALIES
              </p>
              <h2 className="mt-3 text-2xl sm:text-3xl font-bold font-mono text-red-500">
                {highRiskWorks.toLocaleString("en-IN")}
              </h2>
            </div>
            <div className="rounded-xl bg-red-500/10 p-3 text-2xl">
              ⚠️
            </div>
          </div>
          <p className={`mt-4 text-xs ${mutedText}`}>
            Flagged by <span className="font-semibold text-red-500">AI Anomaly Model</span>
          </p>
        </div>
      </div>

      {/* STATE INTENSITY & REGIONAL ANALYSIS */}
      <div className="mt-7 grid grid-cols-1 gap-6 xl:grid-cols-12">
        {/* REGIONAL BREAKDOWN */}
        <div className={`rounded-xl border p-6 shadow-xs xl:col-span-8 ${cardClasses}`}>
          <div className="mb-6 flex items-center justify-between border-b border-gray-100 pb-4 dark:border-gray-700/60">
            <div>
              <h2 className="text-xl font-bold">Top States by Work Allocation</h2>
              <p className={`mt-1 text-xs ${mutedText}`}>
                Live project distribution, fund allocation, and physical completion rates.
              </p>
            </div>
            <span className="rounded-lg bg-gray-100 px-3 py-1 font-mono text-xs font-bold text-gray-700 dark:bg-gray-800 dark:text-gray-200">
              {stateData.length} States Monitored
            </span>
          </div>

          <div className="space-y-4">
            {topStates.map((st, idx) => {
              const pct = (st.total_projects / maxProjectsInState) * 100
              return (
                <div key={st.state} className="rounded-lg p-2 transition hover:bg-gray-50 dark:hover:bg-gray-800/50 cursor-pointer" onClick={() => onDrillDown && onDrillDown("Projects", { state: st.state })}>
                  <div className="mb-1.5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 text-xs">
                    <span className="font-bold text-gray-900 dark:text-white">
                      #{idx + 1} {st.state}
                    </span>
                    <div className="flex items-center gap-3 sm:gap-4 font-mono flex-wrap">
                      <span>₹{formatCrore(st.total_sanctioned_amount)} Cr</span>
                      <span className="font-bold text-blue-600 dark:text-blue-400">
                        {st.total_projects.toLocaleString("en-IN")} works
                      </span>
                      <span className="text-green-600 dark:text-green-400">
                        {st.utilization_percentage}% spent
                      </span>
                    </div>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                    <div
                      className="h-full rounded-full bg-blue-600 transition-all duration-500 dark:bg-blue-500"
                      style={{ width: `${Math.max(5, pct)}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* QUICK METRICS & SYSTEM STATUS */}
        <div className="flex flex-col gap-6 xl:col-span-4">
          <div className={`rounded-xl border p-6 shadow-xs ${cardClasses}`}>
            <h3 className="mb-4 text-base font-bold">Execution Health</h3>
            <div className="space-y-4 font-mono text-xs">
              <div className="flex items-center justify-between border-b border-gray-100 pb-2.5 dark:border-gray-700/60">
                <span className={mutedText}>Completed Works:</span>
                <span className="font-bold text-green-600 dark:text-green-400">
                  {completedWorks.toLocaleString("en-IN")}
                </span>
              </div>
              <div className="flex items-center justify-between border-b border-gray-100 pb-2.5 dark:border-gray-700/60">
                <span className={mutedText}>Ongoing Works:</span>
                <span className="font-bold text-blue-600 dark:text-blue-400">
                  {(overview?.ongoing_projects || 0).toLocaleString("en-IN")}
                </span>
              </div>
              <div className="flex items-center justify-between border-b border-gray-100 pb-2.5 dark:border-gray-700/60">
                <span className={mutedText}>Avg Physical Completion:</span>
                <span className="font-bold text-purple-600 dark:text-purple-400">
                  {overview?.average_completion_percentage || 0}%
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className={mutedText}>Total MPs Registered:</span>
                <span className="font-bold text-gray-900 dark:text-white">
                  {overview?.total_mps || 0}
                </span>
              </div>
            </div>
          </div>

          {/* BACKEND STATUS BADGE */}
          <div className={`rounded-xl border p-5 shadow-xs ${cardClasses}`}>
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  Backend Link Status
                </h4>
                <p className="mt-1 text-sm font-semibold">
                  {backendConnected ? "Connected & Synchronized" : "Disconnected"}
                </p>
              </div>
              <span className={`h-3.5 w-3.5 rounded-full ${backendConnected ? "bg-green-500 shadow-sm shadow-green-500/50" : "bg-red-500"}`} />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Overview
