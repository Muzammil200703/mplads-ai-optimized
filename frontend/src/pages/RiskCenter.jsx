import { useEffect, useState, useCallback, memo } from "react"
import { getAnomalies, getAnomaliesSummary, getStates, getConstituencies, getProjectDetail, getAnomalyAnalytics } from "../services/api"
import { formatMoney, formatNumber } from "../utils/format"

/* ──────────── Donut Chart (pure CSS) ──────────── */
const DonutChart = memo(function DonutChart({ high, medium, low, none }) {
  const total = high + medium + low + none
  if (total === 0) return null
  const highPct = (high / total) * 100
  const medPct = (medium / total) * 100
  const lowPct = (low / total) * 100
  const nonePct = (none / total) * 100

  const grad = `conic-gradient(
    #ef4444 0% ${highPct}%,
    #f59e0b ${highPct}% ${highPct + medPct}%,
    #3b82f6 ${highPct + medPct}% ${highPct + medPct + lowPct}%,
    #6b7280 ${highPct + medPct + lowPct}% 100%
  )`

  const segments = [
    { label: "High Risk", count: high, pct: highPct, color: "bg-red-500" },
    { label: "Medium Risk", count: medium, pct: medPct, color: "bg-amber-500" },
    { label: "Low Risk", count: low, pct: lowPct, color: "bg-blue-500" },
    { label: "No Risk", count: none, pct: nonePct, color: "bg-gray-400" },
  ]

  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="relative flex-shrink-0">
        <div
          className="h-44 w-44 rounded-full sm:h-52 sm:w-52"
          style={{ background: grad }}
        />
        <div className="absolute inset-0 flex flex-col items-center justify-center rounded-full bg-white dark:bg-[#1f2937]" style={{ margin: "22%" }}>
          <span className="font-mono text-2xl font-bold text-gray-900 dark:text-white">{total.toLocaleString("en-IN")}</span>
          <span className="text-xs text-gray-500">Projects</span>
        </div>
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-2 sm:flex-col sm:gap-3">
        {segments.map((s) => (
          <div key={s.label} className="flex items-center gap-2.5">
            <span className={`h-3.5 w-3.5 flex-shrink-0 rounded-sm ${s.color}`} />
            <div className="flex items-baseline gap-2">
              <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">{s.label}</span>
              <span className="font-mono text-sm font-bold text-gray-500">{s.count.toLocaleString("en-IN")}</span>
              <span className="font-mono text-xs text-gray-400">({s.pct.toFixed(1)}%)</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
})

/* ──────────── Horizontal Bar Chart ──────────── */
/* ═══════════════ FY HORIZONTAL BAR CHART ═══════════════ */
const FYearChart = memo(function FYearChart({ items }) {
  if (!items || items.length === 0) return null
  const maxCount = Math.max(...items.map((f) => f.count || 0))
  return (
    <div className="flex w-full flex-col gap-5 py-2">
      {items.map((f) => {
        const pct = maxCount > 0 ? (f.count / maxCount) * 100 : 0
        return (
          <div key={f.fy} className="flex w-full flex-col gap-1.5">
            <div className="flex items-baseline justify-between">
              <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                {f.fy}
              </span>
              <span className="text-sm font-bold tabular-nums text-gray-900 dark:text-white">
                {(f.count || 0).toLocaleString("en-IN")}
              </span>
            </div>
            <div className="h-7 w-full overflow-hidden rounded-md bg-gray-100 dark:bg-gray-700/60">
              <div
                className="h-full rounded-md bg-emerald-500 transition-all duration-300"
                style={{ width: `${Math.max(2, pct)}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
})

const HBarChart = memo(function HBarChart({ items, maxCount, barColor = "bg-blue-500", onClickItem, compact }) {
  if (!items || items.length === 0) return null
  const peak = maxCount || Math.max(...items.map((i) => i.count))
  return (
    <div className={compact ? "flex w-full flex-col justify-center gap-4" : "space-y-3"}>
      {items.map((item) => {
        const width = peak > 0 ? (item.count / peak) * 100 : 0
        return (
          <div
            key={item.label}
            className={`group flex items-center gap-3 ${onClickItem ? "cursor-pointer" : ""}`}
            onClick={() => onClickItem && onClickItem(item)}
          >
            <span className="w-44 flex-shrink-0 truncate text-right text-sm font-semibold text-gray-700 dark:text-gray-300" title={item.label}>
              {item.label}
            </span>
            <div className="min-w-0 flex-1">
              <div className="h-8 overflow-hidden rounded bg-gray-100 dark:bg-gray-700/60">
                <div
                  className={`h-full rounded ${barColor} transition-all duration-300 group-hover:opacity-80`}
                  style={{ width: `${Math.max(2, width)}%` }}
                />
              </div>
            </div>
            <span className="w-24 flex-shrink-0 text-right font-mono text-sm font-bold text-gray-600 dark:text-gray-400">
              {item.count.toLocaleString("en-IN")}
            </span>
            {item.pct !== undefined && (
              <span className="w-12 flex-shrink-0 text-right font-mono text-xs text-gray-400">{item.pct}%</span>
            )}
          </div>
        )
      })}
    </div>
  )
})

/* ──────────── Data Update Notice (same as Projects.jsx) ──────────── */
const STALE_THRESHOLD = 1000000 // ₹10 lakh
function getStaleProgressFlag(project) {
  const sanctioned = Number(project.sanctioned_amount || 0)
  const expenditure = Number(project.expenditure || 0)
  const completion = Number(project.completion_percentage || 0)
  if (sanctioned >= STALE_THRESHOLD && completion === 0 && expenditure === 0) {
    return true
  }
  return false
}

/* ═══════════════ MAIN COMPONENT ═══════════════ */
const RiskCenter = memo(function RiskCenter({ drillDownParams, onClearDrillDown, fy }) {
  const [summary, setSummary] = useState({ total_projects_checked: 0, high_risk: 0, medium_risk: 0, low_risk: 0, total_anomalies: 0 })
  const [anomalies, setAnomalies] = useState([])
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  // Filters
  const [states, setStates] = useState([])
  const [constituencies, setConstituencies] = useState([])
  const [filterState, setFilterState] = useState("")
  const [filterConstituency, setFilterConstituency] = useState("")
  const [filterSeverity, setFilterSeverity] = useState("")
  const [searchQuery, setSearchQuery] = useState("")
  const [sortBy, setSortBy] = useState("risk_score")
  const [sortDir, setSortDir] = useState("desc")
  const [currentPage, setCurrentPage] = useState(1)
  const rowsPerPage = 20

  // Detail panel
  const [selectedAnomaly, setSelectedAnomaly] = useState(null)
  const [detailRisk, setDetailRisk] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  // Analytics
  const [analytics, setAnalytics] = useState(null)

  // Handle drill-down params
  useEffect(() => {
    if (drillDownParams) {
      if (drillDownParams.risk_level) setFilterSeverity(drillDownParams.risk_level)
      if (drillDownParams.state) setFilterState(drillDownParams.state)
      setCurrentPage(1)
      if (onClearDrillDown) onClearDrillDown()
    }
  }, [drillDownParams, onClearDrillDown])

  // Load states on mount
  useEffect(() => {
    getStates().then((s) => { if (Array.isArray(s)) setStates(s) }).catch(() => {})
  }, [])

  // Load constituencies when state changes
  useEffect(() => {
    if (!filterState) { setConstituencies([]); setFilterConstituency(""); return }
    getConstituencies(filterState).then((d) => { if (Array.isArray(d)) setConstituencies(d) }).catch(() => {})
  }, [filterState])

  // Load summary
  useEffect(() => {
    const params = {}
    if (fy) params.fy = fy
    getAnomaliesSummary(params).then((s) => { if (s) setSummary(s) }).catch(() => {})
  }, [fy])

  // Load analytics (filter-aware)
  useEffect(() => {
    const params = {}
    if (filterState) params.state = filterState
    if (filterConstituency) params.constituency = filterConstituency
    if (fy) params.fy = fy
    getAnomalyAnalytics(params).then((a) => { if (a) setAnalytics(a) }).catch(() => {})
  }, [filterState, filterConstituency, fy])

  // Fetch anomalies with server-side filters
  const fetchAnomalies = useCallback(async () => {
    try {
      setLoading(true)
      setError("")
      const params = {
        skip: (currentPage - 1) * rowsPerPage,
        limit: rowsPerPage,
      }
      if (filterState) params.state = filterState
      if (filterConstituency) params.constituency = filterConstituency
      if (fy) params.fy = fy
      if (filterSeverity) params.risk_level = filterSeverity
      if (searchQuery.trim()) params.q = searchQuery.trim()
      if (sortBy) { params.sort_by = sortBy; params.sort_dir = sortDir }

      const data = await getAnomalies(params)
      setAnomalies(data?.anomalies || [])
      setTotalCount(data?.total_anomalies || 0)
    } catch (err) {
      console.error("Risk center error:", err)
      setError("Unable to load anomaly data. Check backend connection.")
    } finally {
      setLoading(false)
    }
  }, [filterState, filterConstituency, fy, filterSeverity, searchQuery, currentPage, sortBy, sortDir])

  useEffect(() => { fetchAnomalies() }, [fetchAnomalies])

  // Reset filters
  const handleReset = () => {
    setFilterState(""); setFilterConstituency(""); setFilterSeverity("")
    setSortBy("risk_score"); setSortDir("desc"); setSearchQuery(""); setCurrentPage(1)
  }

  // Open detail panel
  const handleOpenDetail = async (anomaly) => {
    setSelectedAnomaly(anomaly)
    setDetailRisk(null)
    setLoadingDetail(true)
    try {
      const detail = await getProjectDetail(anomaly.project_id)
      if (detail) setDetailRisk(detail.risk)
    } catch (err) { console.error("Detail error:", err) }
    finally { setLoadingDetail(false) }
  }

  const totalPages = Math.max(1, Math.ceil(totalCount / rowsPerPage))
  const rd = analytics?.risk_distribution || { high: 0, medium: 0, low: 0, none: 0 }

  return (
    <div className="min-h-screen bg-[#f9f9ff] p-4 sm:p-6 text-[#151c27] transition-colors duration-200 dark:bg-[#111827] dark:text-[#f3f4f6]">
      <div className="mx-auto max-w-[1440px] space-y-4 sm:space-y-6">

        {/* HEADER */}
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div>
            <h2 className="text-2xl font-bold text-[#031632] dark:text-white">AI Anomaly Detection Center</h2>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Server-side anomaly analysis across <strong>{summary.total_projects_checked.toLocaleString("en-IN")}</strong> MPLADS works.
              {analytics?.ml_anomaly_count > 0 && <> <span className="text-purple-600 dark:text-purple-400 font-semibold">{analytics.ml_anomaly_count.toLocaleString("en-IN")} ML anomalies</span> detected.</>}
            </p>
          </div>
        </div>

        {/* KPI CARDS */}
        <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-4">
          {[
            { label: "Total Checked", value: summary.total_projects_checked, icon: "🔍", text: "text-blue-600 dark:text-blue-400" },
            { label: "High Risk", value: summary.high_risk, icon: "🔴", text: "text-red-600 dark:text-red-400" },
            { label: "Medium Risk", value: summary.medium_risk, icon: "🟡", text: "text-amber-600 dark:text-amber-400" },
            { label: "Total Anomalies", value: summary.total_anomalies, icon: "📊", text: "text-purple-600 dark:text-purple-400" },
          ].map((card) => (
            <div key={card.label} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-[#1f2937]">
              <div className="flex items-center justify-between">
                <p className="text-[11px] font-bold uppercase tracking-wider text-gray-400">{card.label}</p>
                <span className="text-lg">{card.icon}</span>
              </div>
              <p className={`mt-1 font-mono text-3xl font-bold ${card.text}`}>{card.value.toLocaleString("en-IN")}</p>
            </div>
          ))}
        </div>

        {/* CHARTS ROW 1: Donut + Anomaly Types */}
        {analytics && (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Risk Distribution Donut */}
            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-[#1f2937]">
              <h3 className="mb-4 text-sm font-bold uppercase tracking-wider text-gray-400">Risk Distribution</h3>
              <DonutChart high={rd.high} medium={rd.medium} low={rd.low} none={rd.none} />
            </div>

            {/* Anomaly Type Distribution */}
            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-[#1f2937]">
              <h3 className="mb-4 text-sm font-bold uppercase tracking-wider text-gray-400">Anomaly Type Distribution</h3>
              <HBarChart
                items={analytics.anomaly_types.map((at) => ({ label: at.type, count: at.count, pct: at.percentage }))}
                barColor="bg-blue-500"
              />
            </div>
          </div>
        )}

        {/* CHARTS ROW 2: Top States + FY Distribution */}
        {analytics && (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Top States */}
            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-[#1f2937]">
              <h3 className="mb-4 text-sm font-bold uppercase tracking-wider text-gray-400">Top States by Anomaly Count</h3>
              <HBarChart
                items={analytics.state_distribution.map((sd, idx) => ({ label: sd.state, count: sd.count, rank: idx + 1 }))}
                barColor="bg-red-500"
                onClickItem={(item) => { setFilterState(item.label); setCurrentPage(1) }}
              />
              {analytics.state_distribution.length > 0 && (
                <p className="mt-3 text-xs text-gray-400 italic">Click a state to filter the project list below.</p>
              )}
            </div>

            {/* FY Distribution — compact vertical bar chart */}
            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-[#1f2937]">
              <h3 className="mb-1 text-sm font-bold text-gray-600 dark:text-gray-300">Anomalies by Financial Year</h3>
              <p className="mb-4 text-[11px] text-gray-400 dark:text-gray-500">Number of flagged projects per FY period</p>
              {analytics.fy_distribution && analytics.fy_distribution.length > 0 ? (
                <FYearChart items={analytics.fy_distribution} />
              ) : (
                <p className="py-8 w-full text-center text-sm text-gray-400">No FY distribution data available.</p>
              )}
            </div>
          </div>
        )}

        {/* PROJECTS BY RISK LEVEL */}
        {analytics && (
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-[#1f2937]">
            <div className="mb-4">
              <h3 className="text-sm font-bold uppercase tracking-wider text-gray-400">Projects by Risk Level</h3>
              <p className="mt-0.5 text-xs text-gray-400">Distribution of monitored projects across AI-assessed risk levels.</p>
            </div>
            {(() => {
              const rd = analytics.risk_distribution || {}
              const total = (rd.high || 0) + (rd.medium || 0) + (rd.low || 0) + (rd.none || 0)
              if (total === 0) return <p className="py-8 text-center text-sm text-gray-400">No risk data available.</p>
              const categories = [
                { label: "High Risk", count: rd.high || 0, color: "bg-red-500", text: "text-red-600 dark:text-red-400", border: "border-red-200 dark:border-red-900/40" },
                { label: "Medium Risk", count: rd.medium || 0, color: "bg-amber-500", text: "text-amber-600 dark:text-amber-400", border: "border-amber-200 dark:border-amber-900/40" },
                { label: "Low Risk", count: rd.low || 0, color: "bg-blue-500", text: "text-blue-600 dark:text-blue-400", border: "border-blue-200 dark:border-blue-900/40" },
                { label: "No Risk", count: rd.none || 0, color: "bg-gray-400", text: "text-gray-600 dark:text-gray-400", border: "border-gray-200 dark:border-gray-700" },
              ].sort((a, b) => b.count - a.count)
              const maxCount = categories[0]?.count || 1
              return (
                <div className="space-y-4">
                  {categories.map((cat) => {
                    const pct = total > 0 ? (cat.count / total * 100).toFixed(1) : 0
                    const barWidth = maxCount > 0 ? (cat.count / maxCount) * 100 : 0
                    return (
                      <div key={cat.label} className="group">
                        <div className="mb-1.5 flex items-baseline justify-between">
                          <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">{cat.label}</span>
                          <div className="flex items-baseline gap-2">
                            <span className={`font-mono text-sm font-bold ${cat.text}`}>{cat.count.toLocaleString("en-IN")}</span>
                            <span className="font-mono text-xs text-gray-400">({pct}%)</span>
                          </div>
                        </div>
                        <div className="h-8 overflow-hidden rounded-md bg-gray-100 dark:bg-gray-700/60">
                          <div
                            className={`h-full rounded-md ${cat.color} transition-all duration-500 group-hover:opacity-80`}
                            style={{ width: `${Math.max(1, barWidth)}%` }}
                          />
                        </div>
                      </div>
                    )
                  })}
                  <div className="mt-2 flex items-center justify-between border-t border-gray-100 pt-2 dark:border-gray-700/60">
                    <span className="text-xs text-gray-500">Total projects assessed</span>
                    <span className="font-mono text-sm font-bold text-gray-900 dark:text-white">{total.toLocaleString("en-IN")}</span>
                  </div>
                </div>
              )
            })()}
          </div>
        )}

        {/* FILTERS */}
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-[#1f2937]">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-5">
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">Search</label>
              <input
                value={searchQuery}
                onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1) }}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); setCurrentPage(1); fetchAnomalies() } }}
                placeholder="Project name or ID..."
                className="mt-1.5 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-2xs outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-[#111827] dark:text-white"
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">Severity</label>
              <select value={filterSeverity} onChange={(e) => { setFilterSeverity(e.target.value); setCurrentPage(1) }}
                className="mt-1.5 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-2xs outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-[#111827] dark:text-white">
                <option value="">All Severity</option>
                <option value="High">High Risk</option>
                <option value="Medium">Medium Risk</option>
                <option value="Low">Low Risk</option>
                <option value="None">No Risk</option>
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">State</label>
              <select value={filterState} onChange={(e) => { setFilterState(e.target.value); setCurrentPage(1) }}
                className="mt-1.5 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-2xs outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-[#111827] dark:text-white">
                <option value="">All States</option>
                {states.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">Constituency</label>
              <select value={filterConstituency} disabled={!filterState}
                onChange={(e) => { setFilterConstituency(e.target.value); setCurrentPage(1) }}
                className="mt-1.5 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-2xs outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 disabled:opacity-50 dark:border-gray-600 dark:bg-[#111827] dark:text-white">
                <option value="">{filterState ? "All Constituencies" : "Select State"}</option>
                {constituencies.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="flex items-end">
              <button onClick={handleReset}
                className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2 text-xs font-bold text-gray-700 transition hover:bg-gray-50 dark:border-gray-600 dark:bg-[#111827] dark:text-gray-200">
                Reset Filters
              </button>
            </div>
          </div>
        </div>

        {/* ERROR */}
        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-medium text-red-700 dark:border-red-800/60 dark:bg-red-950/40 dark:text-red-300">⚠ {error}</div>
        )}

        {/* SORT ROW */}
        <div className="flex flex-wrap items-center gap-1.5 sm:gap-3">
          <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Sort:</span>
          {[
            { value: "risk_score", label: "Risk Score" },
            { value: "sanctioned_amount", label: "Sanctioned" },
            { value: "expenditure", label: "Expenditure" },
            { value: "completion_percentage", label: "Progress" },
            { value: "project_name", label: "Name" },
            { value: "id", label: "Project ID" },
          ].map((opt) => (
            <button key={opt.value}
              onClick={() => {
                if (sortBy === opt.value) setSortDir((d) => d === "asc" ? "desc" : "asc")
                else { setSortBy(opt.value); setSortDir(opt.value === "project_name" || opt.value === "id" ? "asc" : "desc") }
                setCurrentPage(1)
              }}
              className={`rounded-lg px-3 py-1.5 text-[11px] font-bold transition ${sortBy === opt.value ? "bg-[#031632] text-white dark:bg-blue-600" : "border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:bg-[#1f2937] dark:text-gray-300"}`}>
              {opt.label}{sortBy === opt.value && <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>}
            </button>
          ))}
        </div>

        {/* ANOMALY TABLE */}
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-[#1f2937]">
          {loading ? (
            <div className="p-16 text-center">
              <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-600 border-r-transparent" />
              <p className="mt-3 text-sm font-medium">Running anomaly diagnostics...</p>
            </div>
          ) : anomalies.length === 0 ? (
            <div className="p-16 text-center text-sm text-gray-500">No anomalies match the current filters.</div>
          ) : (
            <>
              {/* DESKTOP TABLE */}
              <div className="hidden lg:block overflow-x-auto">
                <table className="w-full min-w-[900px]">
                  <thead>
                    <tr className="border-b-2 border-gray-200 bg-gray-50 text-left text-[10px] font-bold uppercase tracking-widest text-gray-500 dark:border-gray-700 dark:bg-[#172033] dark:text-gray-400">
                      <th className="px-4 py-3">Project</th>
                      <th className="px-4 py-3">State / Constituency</th>
                      <th className="px-4 py-3 text-right">Sanctioned</th>
                      <th className="px-4 py-3 text-right">Expenditure</th>
                      <th className="px-4 py-3 text-center">Progress</th>
                      <th className="px-4 py-3 text-center">Risk Level</th>
                      <th className="px-4 py-3 text-center">Score</th>
                      <th className="px-4 py-3 text-center">ML</th>
                      <th className="px-4 py-3 text-center">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {anomalies.map((a) => (
                      <tr key={a.project_id} className="cursor-pointer border-b border-gray-100 transition hover:bg-blue-50/40 dark:border-gray-700/60 dark:hover:bg-[#253247]" onClick={() => handleOpenDetail(a)}>
                        <td className="px-4 py-2.5">
                          <span className="font-mono text-[10px] font-bold text-gray-400">#{a.project_id}</span>
                          <p className="max-w-[250px] truncate text-sm font-semibold text-gray-900 dark:text-white" title={a.project_name}>{a.project_name || "Unnamed"}</p>
                          <p className="text-[11px] text-gray-400">{a.project_type || "General"}</p>
                        </td>
                        <td className="px-4 py-2.5 text-xs">
                          <p className="font-semibold">{a.state || "N/A"}</p>
                          <p className="text-gray-500">{a.constituency || "N/A"}</p>
                        </td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums">{formatMoney(a.sanctioned_amount)}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums">{formatMoney(a.expenditure)}</td>
                        <td className="px-4 py-2.5 text-center font-mono text-xs font-bold">{a.completion_percentage}%</td>
                        <td className="px-4 py-2.5 text-center">
                          <div className="flex items-center justify-center gap-1">
                            <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${a.risk_level === "High" ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" : a.risk_level === "Medium" ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" : a.risk_level === "Low" ? "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300" : "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300"}`}>{a.risk_level}</span>
                            {getStaleProgressFlag(a) && (
                              <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-1 py-0.5 text-[9px] font-bold text-amber-600 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300" title="Data Update Notice: Reported progress or expenditure may not reflect the latest project status. A risk score indicates an anomaly based on available data and does not by itself confirm project delay or irregularity.">⚠</span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-2.5 text-center font-mono text-sm font-bold">{a.risk_score}</td>
                        <td className="px-4 py-2.5 text-center">{a.ml_anomaly ? <span className="rounded-full bg-purple-100 px-2 py-0.5 text-[10px] font-bold text-purple-700 dark:bg-purple-950 dark:text-purple-300">ML</span> : <span className="text-gray-300">—</span>}</td>
                        <td className="px-4 py-2.5 text-center"><button onClick={(e) => { e.stopPropagation(); handleOpenDetail(a) }} className="rounded p-1 text-gray-600 hover:bg-gray-200 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-700">👁</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* MOBILE CARD VIEW */}
              <div className="lg:hidden divide-y divide-gray-100 dark:divide-gray-700/60">
                {anomalies.map((a) => (
                  <div key={a.project_id} className="p-4 cursor-pointer transition hover:bg-blue-50/40 dark:hover:bg-[#253247]" onClick={() => handleOpenDetail(a)}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="font-mono text-[10px] font-bold text-gray-400">#{a.project_id}</span>
                          <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${a.risk_level === "High" ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" : a.risk_level === "Medium" ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" : "bg-gray-100 text-gray-600 dark:bg-gray-700"}`}>{a.risk_level}</span>
                          {getStaleProgressFlag(a) && (
                            <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-1 py-0.5 text-[9px] font-bold text-amber-600 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300" title="Data Update Notice: Reported progress or expenditure may not reflect the latest project status.">⚠</span>
                          )}
                          {a.ml_anomaly && <span className="rounded-full bg-purple-100 px-1.5 py-0.5 text-[10px] font-bold text-purple-700 dark:bg-purple-950 dark:text-purple-300">ML</span>}
                        </div>
                        <p className="mt-1 truncate font-semibold text-sm text-gray-900 dark:text-white" title={a.project_name}>{a.project_name || "Unnamed"}</p>
                        <p className="text-[11px] text-gray-500">{a.state || "N/A"}{a.constituency ? `, ${a.constituency}` : ""}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="font-mono text-sm font-bold">Score {a.risk_score}</p>
                      </div>
                    </div>
                    <div className="mt-2 grid grid-cols-3 gap-x-3 gap-y-1 text-xs">
                      <div className="flex justify-between"><span className="text-gray-500">Sanctioned</span><span className="font-mono font-semibold">{formatMoney(a.sanctioned_amount)}</span></div>
                      <div className="flex justify-between"><span className="text-gray-500">Spent</span><span className="font-mono font-semibold">{formatMoney(a.expenditure)}</span></div>
                      <div className="flex justify-between"><span className="text-gray-500">Progress</span><span className="font-mono font-semibold">{a.completion_percentage}%</span></div>
                    </div>
                  </div>
                ))}
              </div>

              {/* PAGINATION */}
              <div className="flex flex-wrap items-center justify-between gap-4 border-t border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-[#172033]">
                <span className="text-xs text-gray-600 dark:text-gray-400">
                  Showing {totalCount === 0 ? 0 : (currentPage - 1) * rowsPerPage + 1} to{" "}
                  {Math.min(currentPage * rowsPerPage, totalCount)} of{" "}
                  <strong>{totalCount.toLocaleString("en-IN")}</strong> anomaly records
                </span>
                <div className="flex items-center gap-2">
                  <button disabled={currentPage === 1} onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 disabled:opacity-40 dark:border-gray-600 dark:bg-[#1f2937] dark:text-gray-200">← Prev</button>
                  <span className="font-mono text-xs font-bold">{currentPage} / {totalPages}</span>
                  <button disabled={currentPage >= totalPages} onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 disabled:opacity-40 dark:border-gray-600 dark:bg-[#1f2937] dark:text-gray-200">Next →</button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* DETAIL MODAL */}
      {selectedAnomaly && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 sm:p-4 backdrop-blur-2xs" onClick={() => setSelectedAnomaly(null)}>
          <div onClick={(e) => e.stopPropagation()} className="flex max-h-[90vh] sm:max-h-[85vh] w-full sm:max-w-2xl flex-col rounded-t-2xl sm:rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-[#1f2937]">
            <div className="flex items-start justify-between border-b border-gray-200 p-5 dark:border-gray-700">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-xs font-bold text-gray-400">#{selectedAnomaly.project_id}</span>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${
                    selectedAnomaly.risk_level === "High" ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
                    : selectedAnomaly.risk_level === "Medium" ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                    : "bg-gray-100 text-gray-600 dark:bg-gray-700"
                  }`}>
                    {selectedAnomaly.risk_level} Risk — Score {selectedAnomaly.risk_score}/100
                  </span>
                  {selectedAnomaly.ml_anomaly && (
                    <span className="rounded-full bg-purple-100 px-1.5 py-0.5 text-[10px] font-bold text-purple-700 dark:bg-purple-950 dark:text-purple-300">ML Anomaly</span>
                  )}
                  {getStaleProgressFlag(selectedAnomaly) && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-600 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300">
                      <span>⚠</span>
                      <span>Data Update Notice</span>
                    </span>
                  )}
                </div>
                <h3 className="mt-2 text-lg font-bold text-gray-900 dark:text-white">{selectedAnomaly.project_name}</h3>
                <p className="text-xs text-gray-500">📍 {selectedAnomaly.state || "N/A"} — {selectedAnomaly.constituency || "N/A"}</p>
              </div>
              <button onClick={() => setSelectedAnomaly(null)} className="rounded p-1 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700">✕</button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {loadingDetail ? (
                <div className="p-8 text-center">
                  <div className="inline-block h-6 w-6 animate-spin rounded-full border-4 border-solid border-blue-600 border-r-transparent" />
                  <p className="mt-2 text-xs text-gray-500">Loading project details...</p>
                </div>
              ) : (
                <>
                  <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-[#111827]">
                    <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-gray-400">Financial Overview</h4>
                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <p className="text-[10px] font-bold uppercase text-gray-400">Sanctioned</p>
                        <p className="font-mono text-sm font-bold">{formatMoney(selectedAnomaly.sanctioned_amount)}</p>
                      </div>
                      <div>
                        <p className="text-[10px] font-bold uppercase text-gray-400">Expenditure</p>
                        <p className="font-mono text-sm font-bold">{formatMoney(selectedAnomaly.expenditure)}</p>
                      </div>
                      <div>
                        <p className="text-[10px] font-bold uppercase text-gray-400">Progress</p>
                        <p className="font-mono text-sm font-bold">{selectedAnomaly.completion_percentage}%</p>
                      </div>
                    </div>
                    {selectedAnomaly.sanctioned_amount > 0 && (
                      <div className="mt-3">
                        <div className="h-2 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                          <div className="h-full rounded-full bg-blue-600" style={{ width: `${Math.min(100, (selectedAnomaly.expenditure || 0) / selectedAnomaly.sanctioned_amount * 100)}%` }} />
                        </div>
                        <p className="mt-1 text-[10px] text-gray-500">
                          Utilization: {((selectedAnomaly.expenditure || 0) / selectedAnomaly.sanctioned_amount * 100).toFixed(1)}%
                        </p>
                      </div>
                    )}
                  </div>

                  {selectedAnomaly.reasons && selectedAnomaly.reasons.length > 0 && (
                    <div className="rounded-xl border border-red-200 bg-red-50/50 p-4 dark:border-red-900/40 dark:bg-red-950/20">
                      <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-red-600 dark:text-red-400">Why This Record Was Flagged</h4>
                      <div className="space-y-2">
                        {selectedAnomaly.reasons.map((reason, i) => (
                          <div key={i} className="flex items-start gap-2">
                            <span className="mt-0.5 text-xs text-red-500">⚠</span>
                            <div>
                              <p className="text-xs font-semibold text-red-700 dark:text-red-400">{reason}</p>
                              <p className="mt-0.5 text-[10px] text-gray-500 dark:text-gray-400">
                                {reason.includes("exceeds sanctioned") && "Expenditure exceeds the approved sanctioned amount — audit review required."}
                                {reason.includes("High expenditure") && "Expenditure-to-sanction ratio is high while physical completion is disproportionately low."}
                                {reason.includes("0% physical completion") && "Funds have been disbursed but no physical progress is recorded — potential stalled or fictitious work."}
                                {reason.includes("completed but physical progress") && "Status contradicts the actual physical completion metric."}
                                {reason.includes("High-value project") && "Large sanctioned value with minimal on-ground progress."}
                                {reason.includes("High completion recorded") && "Physical progress recorded without corresponding financial expenditure — possible data error."}
                                {reason.includes("Very low fund") && "Major discrepancy between financial utilization and physical progress."}
                                {reason.includes("ML") && "Multi-variable statistical deviation detected across financial and progress dimensions by the Isolation Forest model."}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {detailRisk && (
                    <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4 dark:border-blue-900/40 dark:bg-blue-950/20">
                      <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-blue-700 dark:text-blue-300">Detailed Risk Assessment</h4>
                      <div className="flex gap-4 font-mono text-xs">
                        <span>Risk Score: <strong>{detailRisk.risk_score}/100</strong></span>
                        <span>Level: <strong>{detailRisk.risk_level}</strong></span>
                        {detailRisk.ml_anomaly && <span>ML: <strong className="text-purple-600">Anomaly Detected</strong></span>}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

              {getStaleProgressFlag(selectedAnomaly) && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-800/60 dark:bg-amber-950/40">
                  <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-amber-700 dark:text-amber-300">⚠ Data Update Notice</h4>
                  <p className="text-xs text-amber-800 dark:text-amber-200">
                    Reported progress or expenditure may not reflect the latest project status. A high-risk score indicates an anomaly based on available data and does not by itself confirm project delay or irregularity.
                  </p>
                  <div className="mt-2 grid grid-cols-3 gap-2 text-[10px]">
                    <div><span className="font-bold text-amber-600 dark:text-amber-400">Sanctioned:</span> {formatMoney(selectedAnomaly.sanctioned_amount)}</div>
                    <div><span className="font-bold text-amber-600 dark:text-amber-400">Recorded Expenditure:</span> ₹0</div>
                    <div><span className="font-bold text-amber-600 dark:text-amber-400">Recorded Progress:</span> 0%</div>
                  </div>
                  <p className="mt-2 text-[10px] italic text-amber-600/70 dark:text-amber-400/70">This indicator does not confirm project delay or irregularity.</p>
                </div>
              )}

            <div className="border-t border-gray-200 p-4 flex justify-between dark:border-gray-700">
              <button onClick={() => setSelectedAnomaly(null)} className="rounded-lg border border-gray-300 px-4 py-2 text-xs font-bold text-gray-700 dark:border-gray-600 dark:text-gray-200">Close</button>
              <button
                onClick={() => {
                  window.dispatchEvent(new CustomEvent("navigate-to-project", { detail: { query: String(selectedAnomaly.project_id) } }))
                  setSelectedAnomaly(null)
                }}
                className="rounded-lg bg-[#031632] px-4 py-2 text-xs font-bold text-white dark:bg-blue-600">
                View Full Project →
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
})

export default RiskCenter
