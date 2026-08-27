import { useEffect, useState, useCallback, memo } from "react"
import { getAuditPriority, getStates, getConstituencies, getProjectDetail } from "../services/api"
import { formatMoney, formatNumber } from "../utils/format"

const AuditPriority = memo(function AuditPriority({ fy }) {
  const [priorities, setPriorities] = useState([])
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
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

  const [selectedProject, setSelectedProject] = useState(null)
  const [detailRisk, setDetailRisk] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  useEffect(() => {
    getStates().then((s) => { if (Array.isArray(s)) setStates(s) }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!filterState) { setConstituencies([]); setFilterConstituency(""); return }
    getConstituencies(filterState).then((d) => { if (Array.isArray(d)) setConstituencies(d) }).catch(() => {})
  }, [filterState])

  const fetchData = useCallback(async () => {
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

      const data = await getAuditPriority(params)
      setPriorities(data?.priorities || [])
      setTotalCount(data?.total || 0)
    } catch (err) {
      console.error("Audit priority error:", err)
      setError("Failed to load audit priority data.")
    } finally {
      setLoading(false)
    }
  }, [filterState, filterConstituency, fy, filterSeverity, searchQuery, currentPage, sortBy, sortDir])

  useEffect(() => { fetchData() }, [fetchData])

  const handleReset = () => {
    setFilterState(""); setFilterConstituency(""); setFilterSeverity("")
    setSearchQuery(""); setSortBy("risk_score"); setSortDir("desc")
    setCurrentPage(1)
  }

  const handleOpenDetail = async (item) => {
    setSelectedProject(item)
    setDetailRisk(null)
    setLoadingDetail(true)
    try {
      const detail = await getProjectDetail(item.project_id)
      if (detail?.risk) setDetailRisk(detail.risk)
    } catch (err) {
      console.error("Detail error:", err)
    } finally {
      setLoadingDetail(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(totalCount / rowsPerPage))

  return (
    <div className="min-h-screen bg-[#f9f9ff] p-4 sm:p-6 text-[#151c27] transition-colors duration-200 dark:bg-[#111827] dark:text-[#f3f4f6]">
      <div className="mx-auto max-w-[1440px] space-y-4 sm:space-y-6">
        <div>
          <h2 className="text-2xl font-bold text-[#031632] dark:text-white">Audit Priority Queue</h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Projects ranked by risk score for audit prioritization. Rule-based priority derived from existing anomaly signals.
          </p>
          <div className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1 text-[10px] font-bold text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300">
            ⚡ AUDIT PRIORITY — Rule-based ranking from risk/anomaly signals
          </div>
        </div>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-medium text-red-700 dark:border-red-800/60 dark:bg-red-950/40 dark:text-red-300">⚠ {error}</div>
        )}

        {/* Filters */}
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-[#1f2937]">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-6">
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">Search</label>
              <input value={searchQuery} onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1) }}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); fetchData() } }}
                placeholder="Project name or ID..."
                className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-500 dark:border-gray-600 dark:bg-[#111827] dark:text-white" />
            </div>
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">Severity</label>
              <select value={filterSeverity} onChange={(e) => { setFilterSeverity(e.target.value); setCurrentPage(1) }}
                className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-2xs outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-[#111827] dark:text-white">
                <option value="">All Severity</option>
                <option value="High">High Risk</option>
                <option value="Medium">Medium Risk</option>
                <option value="Low">Low Risk</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">State</label>
              <select value={filterState} onChange={(e) => { setFilterState(e.target.value); setCurrentPage(1) }}
                className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-2xs outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-[#111827] dark:text-white">
                <option value="">All States</option>
                {states.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">Constituency</label>
              <select value={filterConstituency} disabled={!filterState}
                onChange={(e) => { setFilterConstituency(e.target.value); setCurrentPage(1) }}
                className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 disabled:opacity-50 dark:border-gray-600 dark:bg-[#111827] dark:text-white">
                <option value="">{filterState ? "All Constituencies" : "Select State"}</option>
                {constituencies.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="flex items-end">
              <button onClick={handleReset} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-[#111827] dark:text-gray-200">Reset</button>
            </div>
          </div>
          {/* Sort */}
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-3 dark:border-gray-700/60">
            <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Sort:</span>
            {[
              { value: "risk_score", label: "Risk Score" },
              { value: "sanctioned_amount", label: "Sanctioned" },
              { value: "expenditure", label: "Expenditure" },
              { value: "completion_percentage", label: "Progress" },
              { value: "id", label: "ID" },
            ].map((opt) => (
              <button key={opt.value} onClick={() => {
                if (sortBy === opt.value) setSortDir((d) => d === "asc" ? "desc" : "asc")
                else { setSortBy(opt.value); setSortDir(opt.value === "id" ? "asc" : "desc") }
                setCurrentPage(1)
              }}
                className={`rounded-lg px-2.5 py-1 text-[10px] font-bold transition ${sortBy === opt.value ? "bg-[#031632] text-white dark:bg-blue-600" : "border border-gray-200 bg-white text-gray-500 dark:border-gray-600 dark:bg-[#1f2937] dark:text-gray-400"}`}>
                {opt.label}{sortBy === opt.value && <span className="ml-0.5">{sortDir === "asc" ? "↑" : "↓"}</span>}
              </button>
            ))}
          </div>
        </div>

        {/* Table */}
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-[#1f2937]">
          {loading ? (
            <div className="p-16 text-center">
              <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-600 border-r-transparent" />
              <p className="mt-3 text-sm font-medium">Loading audit priorities...</p>
            </div>
          ) : priorities.length === 0 ? (
            <div className="p-16 text-center text-sm text-gray-500">No audit priorities match the current filters.</div>
          ) : (
            <>
              {/* DESKTOP TABLE */}
              <div className="hidden lg:block overflow-x-auto">
                <table className="w-full min-w-[1000px]">
                  <thead>
                    <tr className="border-b border-gray-200 bg-gray-50 text-left text-xs font-bold uppercase tracking-wider text-gray-700 dark:border-gray-700 dark:bg-[#172033] dark:text-gray-300">
                      <th className="p-3 text-center">#</th>
                      <th className="p-3">Project</th>
                      <th className="p-3">State / Constituency</th>
                      <th className="p-3 text-right">Sanctioned</th>
                      <th className="p-3 text-right">Expenditure</th>
                      <th className="p-3 text-center">Progress</th>
                      <th className="p-3 text-center">Risk</th>
                      <th className="p-3 text-center">Score</th>
                      <th className="p-3">Primary Anomaly</th>
                      <th className="p-3 text-center">View</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700/60">
                    {priorities.map((p) => (
                      <tr key={p.project_id} className="cursor-pointer transition hover:bg-blue-50/40 dark:hover:bg-[#253247]" onClick={() => handleOpenDetail(p)}>
                        <td className="p-3 text-center font-mono text-xs font-bold text-gray-400">{p.priority_rank}</td>
                        <td className="p-3">
                          <span className="font-mono text-[10px] font-bold text-gray-400">#{p.project_id}</span>
                          <p className="max-w-[200px] truncate text-sm font-semibold" title={p.project_name}>{p.project_name || "Unnamed"}</p>
                        </td>
                        <td className="p-3 text-xs">
                          <p className="font-semibold">{p.state || "N/A"}</p>
                          <p className="text-gray-500">{p.constituency || "N/A"}</p>
                        </td>
                        <td className="p-3 text-right font-mono text-xs">{formatMoney(p.sanctioned_amount)}</td>
                        <td className="p-3 text-right font-mono text-xs">{formatMoney(p.expenditure)}</td>
                        <td className="p-3 text-center font-mono text-xs font-bold">{p.completion_percentage}%</td>
                        <td className="p-3 text-center">
                          <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                            p.risk_level === "High" ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
                            : p.risk_level === "Medium" ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                            : "bg-gray-100 text-gray-600 dark:bg-gray-700"
                          }`}>{p.risk_level}</span>
                        </td>
                        <td className="p-3 text-center font-mono text-sm font-bold">{p.risk_score}</td>
                        <td className="p-3 text-xs font-semibold text-red-600 dark:text-red-400">{p.primary_anomaly}</td>
                        <td className="p-3 text-center">
                          <button onClick={(e) => { e.stopPropagation(); handleOpenDetail(p) }}
                            className="rounded p-1 text-gray-600 hover:bg-gray-200 dark:text-gray-400 dark:hover:bg-gray-700">👁</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* MOBILE CARD VIEW */}
              <div className="lg:hidden divide-y divide-gray-200 dark:divide-gray-700/60">
                {priorities.map((p) => (
                  <div key={p.project_id} className="p-4 cursor-pointer transition hover:bg-blue-50/40 dark:hover:bg-[#253247]" onClick={() => handleOpenDetail(p)}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="text-[10px] font-bold text-gray-400">#{p.priority_rank}</span>
                          <span className="font-mono text-[10px] font-bold text-gray-400">#{p.project_id}</span>
                          <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${p.risk_level === "High" ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" : p.risk_level === "Medium" ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" : "bg-gray-100 text-gray-600 dark:bg-gray-700"}`}>{p.risk_level}</span>
                        </div>
                        <p className="mt-1 truncate font-semibold text-sm" title={p.project_name}>{p.project_name || "Unnamed"}</p>
                        <p className="text-[11px] text-gray-500">{p.state || "N/A"}{p.constituency ? `, ${p.constituency}` : ""}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="font-mono text-sm font-bold">{p.risk_score}</p>
                        <p className="text-[10px] text-red-600 dark:text-red-400 font-semibold">{p.primary_anomaly}</p>
                      </div>
                    </div>
                    <div className="mt-2 grid grid-cols-3 gap-x-3 gap-y-1 text-xs">
                      <div className="flex justify-between"><span className="text-gray-500">Sanctioned</span><span className="font-mono font-semibold">{formatMoney(p.sanctioned_amount)}</span></div>
                      <div className="flex justify-between"><span className="text-gray-500">Spent</span><span className="font-mono font-semibold">{formatMoney(p.expenditure)}</span></div>
                      <div className="flex justify-between"><span className="text-gray-500">Progress</span><span className="font-mono font-semibold">{p.completion_percentage}%</span></div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 sm:gap-4 border-t border-gray-200 bg-gray-50 p-3 sm:p-4 dark:border-gray-700 dark:bg-[#172033]">
                <span className="text-xs text-gray-600 dark:text-gray-400">
                  Showing {totalCount === 0 ? 0 : (currentPage - 1) * rowsPerPage + 1} to {Math.min(currentPage * rowsPerPage, totalCount)} of <strong>{totalCount.toLocaleString("en-IN")}</strong>
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

      {/* Detail Modal */}
      {selectedProject && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-2xs" onClick={() => setSelectedProject(null)}>
          <div onClick={(e) => e.stopPropagation()} className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-[#1f2937]">
            <div className="flex items-start justify-between border-b border-gray-200 p-5 dark:border-gray-700">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-bold text-gray-400">#{selectedProject.project_id}</span>
                  <span className={`rounded px-2 py-0.5 text-xs font-bold ${
                    selectedProject.risk_level === "High" ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
                    : selectedProject.risk_level === "Medium" ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                    : "bg-gray-100 text-gray-600 dark:bg-gray-700"
                  }`}>Priority #{selectedProject.priority_rank} — Score {selectedProject.risk_score}/100</span>
                </div>
                <h3 className="mt-2 text-lg font-bold text-gray-900 dark:text-white">{selectedProject.project_name}</h3>
                <p className="text-xs text-gray-500">📍 {selectedProject.state || "N/A"} — {selectedProject.constituency || "N/A"}</p>
              </div>
              <button onClick={() => setSelectedProject(null)} className="rounded p-1 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700">✕</button>
            </div>
            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {/* Financial */}
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-[#111827]">
                <div className="grid grid-cols-3 gap-4">
                  <div><p className="text-[10px] font-bold uppercase text-gray-400">Sanctioned</p><p className="font-mono text-sm font-bold">{formatMoney(selectedProject.sanctioned_amount)}</p></div>
                  <div><p className="text-[10px] font-bold uppercase text-gray-400">Expenditure</p><p className="font-mono text-sm font-bold">{formatMoney(selectedProject.expenditure)}</p></div>
                  <div><p className="text-[10px] font-bold uppercase text-gray-400">Progress</p><p className="font-mono text-sm font-bold">{selectedProject.completion_percentage}%</p></div>
                </div>
              </div>
              {/* Anomaly Explanation */}
              {selectedProject.reasons && selectedProject.reasons.length > 0 && (
                <div className="rounded-xl border border-red-200 bg-red-50/50 p-4 dark:border-red-900/40 dark:bg-red-950/20">
                  <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-red-600 dark:text-red-400">Why This Project Was Flagged</h4>
                  <div className="space-y-2">
                    {selectedProject.reasons.map((reason, i) => (
                      <div key={i} className="flex items-start gap-2">
                        <span className="mt-0.5 text-xs text-red-500">⚠</span>
                        <div>
                          <p className="text-xs font-semibold text-red-700 dark:text-red-400">{reason}</p>
                          <p className="mt-0.5 text-[10px] text-gray-500 dark:text-gray-400">
                            {reason.includes("exceeds sanctioned") && `Expenditure (₹${formatMoney(selectedProject.expenditure)}) exceeds sanctioned amount (₹${formatMoney(selectedProject.sanctioned_amount)}). Variance: ₹${formatMoney(Math.max(0, selectedProject.expenditure - selectedProject.sanctioned_amount))}.`}
                            {reason.includes("High expenditure") && `Fund utilization at ${((selectedProject.expenditure || 0) / (selectedProject.sanctioned_amount || 1) * 100).toFixed(0)}% while physical progress is only ${selectedProject.completion_percentage}%. This mismatch suggests funds may not be translating to visible work.`}
                            {reason.includes("0% physical") && `₹${formatMoney(selectedProject.expenditure)} has been disbursed but physical completion remains at 0%. This indicates work may not have commenced.`}
                            {reason.includes("completed but") && `Status is marked "Completed" but physical progress is only ${selectedProject.completion_percentage}%, which is below the 90% threshold.`}
                            {reason.includes("High-value project") && `Sanctioned amount of ₹${formatMoney(selectedProject.sanctioned_amount)} with only ${selectedProject.completion_percentage}% progress indicates severe execution delay.`}
                            {reason.includes("High completion") && `Progress at ${selectedProject.completion_percentage}% with zero expenditure. This may indicate a data recording error.`}
                            {reason.includes("Very low fund") && `Only ${((selectedProject.expenditure || 0) / (selectedProject.sanctioned_amount || 1) * 100).toFixed(0)}% of ₹${formatMoney(selectedProject.sanctioned_amount)} utilized with ${selectedProject.completion_percentage}% progress.`}
                            {reason.includes("ML") && `Multi-variable statistical deviation detected across expenditure, completion, and project value dimensions.`}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {/* Detailed Risk */}
              {loadingDetail ? (
                <div className="text-center py-4"><div className="inline-block h-5 w-5 animate-spin rounded-full border-4 border-solid border-blue-600 border-r-transparent" /></div>
              ) : detailRisk && (
                <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4 dark:border-blue-900/40 dark:bg-blue-950/20">
                  <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-blue-700 dark:text-blue-300">Detailed Risk Assessment</h4>
                  <div className="flex gap-4 font-mono text-xs">
                    <span>Score: <strong>{detailRisk.risk_score}/100</strong></span>
                    <span>Level: <strong>{detailRisk.risk_level}</strong></span>
                    {detailRisk.ml_anomaly && <span>ML: <strong className="text-purple-600">Anomaly Detected</strong></span>}
                  </div>
                </div>
              )}
            </div>
            <div className="border-t border-gray-200 p-4 text-right dark:border-gray-700">
              <button onClick={() => setSelectedProject(null)} className="rounded-lg border border-gray-300 px-4 py-2 text-xs font-bold text-gray-700 dark:border-gray-600 dark:text-gray-200">Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
})

export default AuditPriority
