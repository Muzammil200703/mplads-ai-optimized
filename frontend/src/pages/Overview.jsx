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

function Overview({ darkMode, onDrillDown, fy }) {
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
          getDashboardOverview(fy ? { fy } : {}),
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
  }, [fy])

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
        <div className="mb-7 rounded-xl border border-blue-200 bg-gradient-to-r from-blue-50 via-white to-blue-50/50 p-5 shadow-sm dark:border-blue-900/60 dark:from-[#1e293b] dark:via-[#1f2937] dark:to-[#172033]">
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
      <div className="grid grid-cols-1 gap-4 sm:gap-5 md:grid-cols-2 xl:grid-cols-4">
        {/* TOTAL WORKS */}
        <div
          className={`rounded-xl border p-5 sm:p-6 shadow-sm cursor-pointer transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 ${cardClasses}`}
          onClick={() => onDrillDown && onDrillDown("Projects")}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className={`text-[11px] font-bold uppercase tracking-wider ${mutedText}`}>
                Total Monitored Works
              </p>
              <h2 className="mt-2.5 text-2xl sm:text-3xl font-bold font-mono tracking-tight">
                {totalWorks.toLocaleString("en-IN")}
              </h2>
            </div>
            <div className="flex-shrink-0 flex items-center justify-center h-11 w-11 rounded-xl bg-blue-500/10 text-xl">
              🏗️
            </div>
          </div>
          <div className="mt-4 pt-3 border-t border-gray-100 dark:border-gray-700/50">
            <p className={`text-xs ${mutedText}`}>
              <span className="font-bold text-green-600 dark:text-green-400">✓ {(overview?.completed_projects || 0).toLocaleString("en-IN")}</span>{" "}
              Completed works
            </p>
          </div>
        </div>

        {/* SANCTIONED AMOUNT */}
        <div className={`rounded-xl border p-5 sm:p-6 shadow-sm transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 ${cardClasses}`}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className={`text-[11px] font-bold uppercase tracking-wider ${mutedText}`}>
                Sanctioned Allocation
              </p>
              <h2 className="mt-2.5 text-2xl sm:text-3xl font-bold font-mono tracking-tight">
                ₹{formatCrore(sanctionedAmount)} <span className="text-sm sm:text-base font-sans text-gray-400 font-normal">Cr</span>
              </h2>
            </div>
            <div className="flex-shrink-0 flex items-center justify-center h-11 w-11 rounded-xl bg-amber-500/10 text-xl">
              💰
            </div>
          </div>
          <div className="mt-4 pt-3 border-t border-gray-100 dark:border-gray-700/50">
            <p className={`text-xs ${mutedText}`}>
              Across <span className="font-bold text-gray-800 dark:text-gray-200">{overview?.total_states || stateData.length}</span> States & UTs
            </p>
          </div>
        </div>

        {/* TOTAL EXPENDITURE */}
        <div className={`rounded-xl border p-5 sm:p-6 shadow-sm transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 ${cardClasses}`}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className={`text-[11px] font-bold uppercase tracking-wider ${mutedText}`}>
                Cumulative Expenditure
              </p>
              <h2 className="mt-2.5 text-2xl sm:text-3xl font-bold font-mono tracking-tight">
                ₹{formatCrore(expenditure)} <span className="text-sm sm:text-base font-sans text-gray-400 font-normal">Cr</span>
              </h2>
            </div>
            <div className="flex-shrink-0 flex items-center justify-center h-11 w-11 rounded-xl bg-purple-500/10 text-xl">
              💳
            </div>
          </div>
          <div className="mt-4 pt-3 border-t border-gray-100 dark:border-gray-700/50">
            <p className={`text-xs ${mutedText}`}>
              <span className="font-bold text-blue-600 dark:text-blue-400">{utilization}%</span> Fund utilization
            </p>
          </div>
        </div>

        {/* HIGH RISK WORKS */}
        <div
          className={`rounded-xl border-2 border-l-4 border-l-red-500 border-t-red-200 border-r-red-200 border-b-red-200 dark:border-l-red-500 dark:border-t-red-900/50 dark:border-r-red-900/50 dark:border-b-red-900/50 p-5 sm:p-6 shadow-sm cursor-pointer transition-all duration-200 hover:shadow-lg hover:-translate-y-0.5 ${cardClasses}`}
          onClick={() => onDrillDown && onDrillDown("Risk Center", { risk_level: "High" })}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-bold uppercase tracking-wider text-red-400 dark:text-red-400">
                High-Risk Anomalies
              </p>
              <h2 className="mt-2.5 text-2xl sm:text-3xl font-bold font-mono text-red-500 dark:text-red-400 tracking-tight">
                {highRiskWorks.toLocaleString("en-IN")}
              </h2>
            </div>
            <div className="flex-shrink-0 flex items-center justify-center h-11 w-11 rounded-xl bg-red-500/10 text-xl">
              ⚠️
            </div>
          </div>
          <div className="mt-4 pt-3 border-t border-red-100 dark:border-red-900/50">
            <p className="text-xs text-red-400 dark:text-red-400">
              Flagged by <span className="font-bold">AI Anomaly Model</span>
            </p>
          </div>
        </div>
      </div>

      {/* STATE INTENSITY & REGIONAL ANALYSIS */}
      <div className="mt-6 grid grid-cols-1 gap-4 sm:gap-5 xl:grid-cols-12">
        {/* REGIONAL BREAKDOWN */}
        <div className={`rounded-xl border p-5 sm:p-6 shadow-sm xl:col-span-8 ${cardClasses}`}>
          <div className="mb-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-gray-100 pb-3 dark:border-gray-700/60">
            <div>
              <h2 className="text-base sm:text-lg font-bold">Top States by Work Allocation</h2>
              <p className={`mt-0.5 text-xs ${mutedText}`}>
                Live project distribution, fund allocation, and physical completion rates.
              </p>
            </div>
            <span className="flex-shrink-0 rounded-lg bg-gray-100 px-2.5 py-1 font-mono text-[11px] font-bold text-gray-600 dark:bg-gray-800 dark:text-gray-300">
              {stateData.length} States
            </span>
          </div>

          <div className="space-y-3">
            {topStates.map((st, idx) => {
              const pct = (st.total_projects / maxProjectsInState) * 100
              return (
                <div
                  key={st.state}
                  className="rounded-lg px-2 py-2.5 transition-all duration-150 hover:bg-gray-50 dark:hover:bg-gray-800/50 cursor-pointer"
                  onClick={() => onDrillDown && onDrillDown("Projects", { state: st.state })}
                >
                  <div className="mb-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="flex-shrink-0 inline-flex items-center justify-center h-5 w-5 rounded-full bg-gray-100 dark:bg-gray-700 text-[10px] font-bold text-gray-500 dark:text-gray-400">
                        {idx + 1}
                      </span>
                      <span className="font-bold text-gray-900 dark:text-white">
                        {st.state}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 sm:gap-3 font-mono text-[11px] flex-wrap pl-7 sm:pl-0">
                      <span className="text-gray-600 dark:text-gray-400">₹{formatCrore(st.total_sanctioned_amount)} Cr</span>
                      <span className="font-bold text-blue-600 dark:text-blue-400">
                        {st.total_projects.toLocaleString("en-IN")} works
                      </span>
                      <span className="text-green-600 dark:text-green-400">
                        {st.utilization_percentage}%
                      </span>
                    </div>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700/60">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-blue-500 to-blue-600 transition-all duration-500 dark:from-blue-400 dark:to-blue-500"
                      style={{ width: `${Math.max(4, pct)}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* QUICK METRICS & SYSTEM STATUS */}
        <div className="flex flex-col gap-4 sm:gap-5 xl:col-span-4">
          <div className={`rounded-xl border p-5 sm:p-6 shadow-sm ${cardClasses}`}>
            <h3 className="mb-4 text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">Execution Health</h3>
            <div className="space-y-0">
              {[
                { label: "Completed Works", value: completedWorks.toLocaleString("en-IN"), color: "text-green-600 dark:text-green-400" },
                { label: "Ongoing Works", value: (overview?.ongoing_projects || 0).toLocaleString("en-IN"), color: "text-blue-600 dark:text-blue-400" },
                { label: "Avg Physical Completion", value: `${overview?.average_completion_percentage || 0}%`, color: "text-purple-600 dark:text-purple-400" },
                { label: "Total MPs Registered", value: (overview?.total_mps || 0).toLocaleString("en-IN"), color: "text-gray-900 dark:text-white" },
              ].map((item, i) => (
                <div key={i} className="flex items-center justify-between py-2.5 border-b border-gray-50 dark:border-gray-700/40 last:border-0 last:pb-0">
                  <span className="text-gray-500 dark:text-gray-400 text-[11px] uppercase tracking-wide font-sans">{item.label}</span>
                  <span className={`font-mono font-bold text-xs ${item.color}`}>{item.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* BACKEND STATUS BADGE */}
          <div className={`rounded-xl border p-4 sm:p-5 shadow-sm ${cardClasses}`}>
            <div className="flex items-center gap-3">
              <span className={`flex-shrink-0 h-3 w-3 rounded-full ${backendConnected ? "bg-green-500 shadow-sm shadow-green-500/50 animate-pulse" : "bg-red-500"}`} />
              <div className="min-w-0 flex-1">
                <h4 className="text-[10px] font-bold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                  Backend Link
                </h4>
                <p className="mt-0.5 text-xs font-semibold truncate">
                  {backendConnected ? "Connected & Synchronized" : "Disconnected"}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Overview
