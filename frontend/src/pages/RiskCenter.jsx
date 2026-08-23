import { useEffect, useState, useCallback } from "react"
import { getAnomalies, getAnomaliesSummary, getStates, getDistricts, getProjectDetail, getAnomalyAnalytics } from "../services/api"

function formatMoney(value) {
  const number = Number(value || 0)
  if (number >= 10000000) return `₹${(number / 10000000).toFixed(2)} Cr`
  if (number >= 100000) return `₹${(number / 100000).toFixed(2)} L`
  return `₹${number.toLocaleString("en-IN")}`
}

function RiskCenter({ drillDownParams, onClearDrillDown }) {
  const [summary, setSummary] = useState({ total_projects_checked: 0, high_risk: 0, medium_risk: 0, low_risk: 0, total_anomalies: 0 })
  const [anomalies, setAnomalies] = useState([])
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  // Filters
  const [states, setStates] = useState([])
  const [districts, setDistricts] = useState([])
  const [filterState, setFilterState] = useState("")
  const [filterDistrict, setFilterDistrict] = useState("")
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

  // Load districts when state changes
  useEffect(() => {
    if (!filterState) { setDistricts([]); setFilterDistrict(""); return }
    getDistricts(filterState).then((d) => { if (Array.isArray(d)) setDistricts(d) }).catch(() => {})
  }, [filterState])

  const [analytics, setAnalytics] = useState(null)

  // Load summary and analytics (once)
  useEffect(() => {
    getAnomaliesSummary().then((s) => { if (s) setSummary(s) }).catch(() => {})
    getAnomalyAnalytics().then((a) => { if (a) setAnalytics(a) }).catch(() => {})
  }, [])

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
      if (filterDistrict) params.district = filterDistrict
      if (filterSeverity) params.risk_level = filterSeverity
      if (searchQuery.trim()) params.q = searchQuery.trim()
      if (sortBy) {
        params.sort_by = sortBy
        params.sort_dir = sortDir
      }

      const data = await getAnomalies(params)
      setAnomalies(data?.anomalies || [])
      setTotalCount(data?.total_anomalies || 0)
    } catch (err) {
      console.error("Risk center error:", err)
      setError("Unable to load anomaly data. Check backend connection.")
    } finally {
      setLoading(false)
    }
  }, [filterState, filterDistrict, filterSeverity, searchQuery, currentPage, sortBy, sortDir])

  useEffect(() => { fetchAnomalies() }, [fetchAnomalies])

  // Reset filters
  const handleReset = () => {
    setFilterState("")
    setFilterDistrict("")
    setSortBy("risk_score")
    setSortDir("desc")
    setFilterSeverity("")
    setSearchQuery("")
    setCurrentPage(1)
  }

  // Open detail panel for an anomaly
  const handleOpenDetail = async (anomaly) => {
    setSelectedAnomaly(anomaly)
    setDetailRisk(null)
    setLoadingDetail(true)
    try {
      const detail = await getProjectDetail(anomaly.project_id)
      if (detail) {
        setDetailRisk(detail.risk)
      }
    } catch (err) {
      console.error("Detail error:", err)
    } finally {
      setLoadingDetail(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(totalCount / rowsPerPage))

  return (
    <div className="min-h-screen bg-[#f9f9ff] p-6 text-[#151c27] transition-colors duration-200 dark:bg-[#111827] dark:text-[#f3f4f6]">
      <div className="mx-auto max-w-[1440px] space-y-6">

        {/* HEADER */}
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div>
            <h2 className="text-2xl font-bold text-[#031632] dark:text-white">
              AI Anomaly Detection Center
            </h2>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Server-side anomaly analysis across <strong>{summary.total_projects_checked.toLocaleString("en-IN")}</strong> MPLADS works.
            </p>
          </div>
        </div>

        {/* SUMMARY CARDS */}
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {[
            { label: "Total Checked", value: summary.total_projects_checked, color: "blue" },
            { label: "High Risk", value: summary.high_risk, color: "red" },
            { label: "Medium Risk", value: summary.medium_risk, color: "amber" },
            { label: "Total Anomalies", value: summary.total_anomalies, color: "purple" },
          ].map((card) => (
            <div key={card.label} className="rounded-xl border border-gray-200 bg-white p-4 shadow-xs dark:border-gray-700 dark:bg-[#1f2937]">
              <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{card.label}</p>
              <p className={`mt-1 font-mono text-2xl font-bold text-${card.color}-600 dark:text-${card.color}-400`}>
                {card.value.toLocaleString("en-IN")}
              </p>
            </div>
          ))}
        </div>

        {/* ANOMALY DISTRIBUTION ANALYTICS */}
        {analytics && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {/* Anomaly Types */}
            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-xs dark:border-gray-700 dark:bg-[#1f2937]">
              <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-gray-400">Anomaly Type Distribution</h3>
              <div className="space-y-2">
                {analytics.anomaly_types.slice(0, 6).map((at) => (
                  <div key={at.type} className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">{at.type}</span>
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                        <div className="h-full rounded-full bg-blue-600" style={{ width: `${Math.min(100, at.percentage * 2)}%` }} />
                      </div>
                      <span className="font-mono text-[10px] font-bold text-gray-500 w-12 text-right">{at.count.toLocaleString()} ({at.percentage}%)</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            {/* State Distribution */}
            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-xs dark:border-gray-700 dark:bg-[#1f2937]">
              <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-gray-400">Top States by Anomaly Count</h3>
              <div className="space-y-2">
                {analytics.state_distribution.slice(0, 6).map((sd, idx) => (
                  <div key={sd.state} className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">#{idx + 1} {sd.state}</span>
                    <span className="font-mono text-xs font-bold text-red-600 dark:text-red-400">{sd.count.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ERROR */}
        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-medium text-red-700 dark:border-red-800/60 dark:bg-red-950/40 dark:text-red-300">
            ⚠ {error}
          </div>
        )}

        {/* FILTERS */}
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-xs dark:border-gray-700 dark:bg-[#1f2937]">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-5">
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Search
              </label>
              <input
                value={searchQuery}
                onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1) }}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); setCurrentPage(1); fetchAnomalies() } }}
                placeholder="Project name or ID..."
                className="mt-1.5 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-2xs outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-[#111827] dark:text-white"
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Severity
              </label>
              <select
                value={filterSeverity}
                onChange={(e) => { setFilterSeverity(e.target.value); setCurrentPage(1) }}
                className="mt-1.5 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-2xs outline-none transition focus:border-blue-500 dark:border-gray-600 dark:bg-[#111827] dark:text-white"
              >
                <option value="">All Severity</option>
                <option value="High">High Risk</option>
                <option value="Medium">Medium Risk</option>
                <option value="Low">Low Risk</option>
                <option value="None">No Risk</option>
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                State
              </label>
              <select
                value={filterState}
                onChange={(e) => { setFilterState(e.target.value); setCurrentPage(1) }}
                className="mt-1.5 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-2xs outline-none transition focus:border-blue-500 dark:border-gray-600 dark:bg-[#111827] dark:text-white"
              >
                <option value="">All States</option>
                {states.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                District
              </label>
              <select
                value={filterDistrict}
                disabled={!filterState}
                onChange={(e) => { setFilterDistrict(e.target.value); setCurrentPage(1) }}
                className="mt-1.5 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-2xs outline-none transition focus:border-blue-500 disabled:opacity-50 dark:border-gray-600 dark:bg-[#111827] dark:text-white"
              >
                <option value="">{filterState ? "All Districts" : "Select State"}</option>
                {districts.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <div className="flex items-end">
              <button
                onClick={handleReset}
                className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2 text-xs font-bold text-gray-700 transition hover:bg-gray-50 dark:border-gray-600 dark:bg-[#111827] dark:text-gray-200"
              >
                Reset Filters
              </button>
            </div>
          </div>
        </div>

        {/* SORT ROW */}
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Sort by:</span>
          {[
            { value: "risk_score", label: "Risk Score" },
            { value: "sanctioned_amount", label: "Sanctioned" },
            { value: "expenditure", label: "Expenditure" },
            { value: "completion_percentage", label: "Progress" },
            { value: "project_name", label: "Name" },
            { value: "id", label: "Project ID" },
          ].map((opt) => (
            <button
              key={opt.value}
              onClick={() => {
                if (sortBy === opt.value) {
                  setSortDir((d) => d === "asc" ? "desc" : "asc")
                } else {
                  setSortBy(opt.value)
                  setSortDir(opt.value === "project_name" || opt.value === "id" ? "asc" : "desc")
                }
                setCurrentPage(1)
              }}
              className={`rounded-lg px-3 py-1.5 text-[11px] font-bold transition ${
                sortBy === opt.value
                  ? "bg-[#031632] text-white dark:bg-blue-600"
                  : "border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:bg-[#1f2937] dark:text-gray-300"
              }`}
            >
              {opt.label}
              {sortBy === opt.value && (
                <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>
              )}
            </button>
          ))}
        </div>

        {/* ANOMALY TABLE */}
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xs dark:border-gray-700 dark:bg-[#1f2937]">
          {loading ? (
            <div className="p-16 text-center">
              <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-600 border-r-transparent" />
              <p className="mt-3 text-sm font-medium">Running anomaly diagnostics...</p>
            </div>
          ) : anomalies.length === 0 ? (
            <div className="p-16 text-center text-sm text-gray-500">
              No anomalies match the current filters.
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[900px]">
                  <thead>
                    <tr className="border-b border-gray-200 bg-gray-50 text-left text-xs font-bold uppercase tracking-wider text-gray-700 dark:border-gray-700 dark:bg-[#172033] dark:text-gray-300">
                      <th className="p-4">Project</th>
                      <th className="p-4">State / District</th>
                      <th className="p-4 text-right">Sanctioned</th>
                      <th className="p-4 text-right">Expenditure</th>
                      <th className="p-4 text-center">Progress</th>
                      <th className="p-4 text-center">Risk Level</th>
                      <th className="p-4 text-center">Score</th>
                      <th className="p-4 text-center">ML</th>
                      <th className="p-4 text-center">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700/60">
                    {anomalies.map((a) => (
                      <tr key={a.project_id} className="cursor-pointer transition hover:bg-blue-50/40 dark:hover:bg-[#253247]" onClick={() => handleOpenDetail(a)}>
                        <td className="p-4">
                          <span className="font-mono text-xs font-bold text-gray-400">#{a.project_id}</span>
                          <p className="max-w-[250px] truncate text-sm font-semibold text-gray-900 dark:text-white" title={a.project_name}>
                            {a.project_name || "Unnamed"}
                          </p>
                          <p className="text-xs text-gray-500">{a.project_type || "General"}</p>
                        </td>
                        <td className="p-4 text-xs">
                          <p className="font-semibold">{a.state || "N/A"}</p>
                          <p className="text-gray-500">{a.district || "N/A"}</p>
                        </td>
                        <td className="p-4 text-right font-mono text-xs">{formatMoney(a.sanctioned_amount)}</td>
                        <td className="p-4 text-right font-mono text-xs">{formatMoney(a.expenditure)}</td>
                        <td className="p-4 text-center font-mono text-xs font-bold">{a.completion_percentage}%</td>
                        <td className="p-4 text-center">
                          <span className={`rounded px-2 py-0.5 text-xs font-bold ${
                            a.risk_level === "High" ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
                            : a.risk_level === "Medium" ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                            : a.risk_level === "Low" ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-300"
                            : "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300"
                          }`}>
                            {a.risk_level}
                          </span>
                        </td>
                        <td className="p-4 text-center font-mono text-sm font-bold">{a.risk_score}</td>
                        <td className="p-4 text-center">
                          {a.ml_anomaly ? (
                            <span className="rounded bg-purple-100 px-1.5 py-0.5 text-[10px] font-bold text-purple-700 dark:bg-purple-950 dark:text-purple-300">ML</span>
                          ) : (
                            <span className="text-gray-300">—</span>
                          )}
                        </td>
                        <td className="p-4 text-center">
                          <button
                            onClick={(e) => { e.stopPropagation(); handleOpenDetail(a) }}
                            className="rounded p-1 text-gray-600 hover:bg-gray-200 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-700"
                          >
                            👁
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-4 border-t border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-[#172033]">
                <span className="text-xs text-gray-600 dark:text-gray-400">
                  Showing {totalCount === 0 ? 0 : (currentPage - 1) * rowsPerPage + 1} to{" "}
                  {Math.min(currentPage * rowsPerPage, totalCount)} of{" "}
                  <strong>{totalCount.toLocaleString("en-IN")}</strong> anomaly records
                </span>
                <div className="flex items-center gap-2">
                  <button
                    disabled={currentPage === 1}
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 disabled:opacity-40 dark:border-gray-600 dark:bg-[#1f2937] dark:text-gray-200"
                  >
                    ← Prev
                  </button>
                  <span className="font-mono text-xs font-bold">{currentPage} / {totalPages}</span>
                  <button
                    disabled={currentPage >= totalPages}
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 disabled:opacity-40 dark:border-gray-600 dark:bg-[#1f2937] dark:text-gray-200"
                  >
                    Next →
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* DETAIL MODAL */}
      {selectedAnomaly && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-2xs" onClick={() => setSelectedAnomaly(null)}>
          <div onClick={(e) => e.stopPropagation()} className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-[#1f2937]">
            <div className="flex items-start justify-between border-b border-gray-200 p-5 dark:border-gray-700">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-bold text-gray-400">#{selectedAnomaly.project_id}</span>
                  <span className={`rounded px-2 py-0.5 text-xs font-bold ${
                    selectedAnomaly.risk_level === "High" ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
                    : selectedAnomaly.risk_level === "Medium" ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                    : "bg-gray-100 text-gray-600 dark:bg-gray-700"
                  }`}>
                    {selectedAnomaly.risk_level} Risk — Score {selectedAnomaly.risk_score}/100
                  </span>
                  {selectedAnomaly.ml_anomaly && (
                    <span className="rounded bg-purple-100 px-1.5 py-0.5 text-[10px] font-bold text-purple-700 dark:bg-purple-950 dark:text-purple-300">ML Anomaly</span>
                  )}
                </div>
                <h3 className="mt-2 text-lg font-bold text-gray-900 dark:text-white">{selectedAnomaly.project_name}</h3>
                <p className="text-xs text-gray-500">📍 {selectedAnomaly.district || "N/A"}, {selectedAnomaly.state || "N/A"} — {selectedAnomaly.constituency || "N/A"}</p>
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
                  {/* Financial Comparison */}
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

                  {/* Why Flagged */}
                  {selectedAnomaly.reasons && selectedAnomaly.reasons.length > 0 && (
                    <div className="rounded-xl border border-red-200 bg-red-50/50 p-4 dark:border-red-900/40 dark:bg-red-950/20">
                      <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-red-600 dark:text-red-400">
                        Why This Record Was Flagged
                      </h4>
                      <div className="space-y-2">
                        {selectedAnomaly.reasons.map((reason, i) => (
                          <div key={i} className="flex items-start gap-2">
                            <span className="mt-0.5 text-xs text-red-500">⚠</span>
                            <div>
                              <p className="text-xs font-semibold text-red-700 dark:text-red-400">{reason}</p>
                              <p className="mt-0.5 text-[10px] text-gray-500 dark:text-gray-400">
                                {reason.includes("exceeds sanctioned") && `Expenditure exceeds the approved sanctioned amount — audit review required.`}
                                {reason.includes("High expenditure") && `Expenditure-to-sanction ratio is high while physical completion is disproportionately low.`}
                                {reason.includes("0% physical completion") && `Funds have been disbursed but no physical progress is recorded — potential stalled or fictitious work.`}
                                {reason.includes("completed but physical progress") && `Status contradicts the actual physical completion metric.`}
                                {reason.includes("High-value project") && `Large sanctioned value with minimal on-ground progress.`}
                                {reason.includes("High completion recorded") && `Physical progress recorded without corresponding financial expenditure — possible data error.`}
                                {reason.includes("Very low fund") && `Major discrepancy between financial utilization and physical progress.`}
                                {reason.includes("ML") && `Multi-variable statistical deviation detected across financial and progress dimensions by the Isolation Forest model.`}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Full detail from backend */}
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

            <div className="border-t border-gray-200 p-4 flex justify-between dark:border-gray-700">
              <button onClick={() => setSelectedAnomaly(null)} className="rounded-lg border border-gray-300 px-4 py-2 text-xs font-bold text-gray-700 dark:border-gray-600 dark:text-gray-200">
                Close
              </button>
              <button
                onClick={() => {
                  window.dispatchEvent(new CustomEvent("navigate-to-project", { detail: { query: String(selectedAnomaly.project_id) } }))
                  setSelectedAnomaly(null)
                }}
                className="rounded-lg bg-[#031632] px-4 py-2 text-xs font-bold text-white dark:bg-blue-600"
              >
                View Full Project →
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default RiskCenter
