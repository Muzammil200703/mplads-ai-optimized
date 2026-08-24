import { useEffect, useState, useCallback, useRef } from "react"
import {
  getProjects,
  searchProjects,
  getStates,
  getDistricts,
  getProjectDetail,
} from "../services/api"
import ProjectDetail from "../components/ProjectDetail"

function formatMoney(value) {
  const number = Number(value || 0)
  if (number >= 10000000) {
    return `₹${(number / 10000000).toFixed(2)} Cr`
  }
  if (number >= 100000) {
    return `₹${(number / 100000).toFixed(2)} L`
  }
  return `₹${number.toLocaleString("en-IN")}`
}

function getRiskScoreBadge(project) {
  const sanctioned = Number(project.sanctioned_amount || 0)
  const expenditure = Number(project.expenditure || 0)
  const completion = Number(project.completion_percentage || 0)

  let score = 0
  if (sanctioned > 0) {
    const ratio = expenditure / sanctioned
    if (expenditure > sanctioned) score += 40
    else if (ratio >= 0.8 && completion < 50) score += 35
  }
  if (expenditure > 0 && completion === 0) score += 30
  if (sanctioned >= 1000000 && completion < 25) score += 20
  score = Math.min(100, score)

  if (score >= 60) {
    return {
      score,
      label: "High",
      badge: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/70 dark:text-red-300",
      icon: "⚠",
    }
  }
  if (score >= 30) {
    return {
      score,
      label: "Medium",
      badge: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/70 dark:text-amber-300",
      icon: "i",
    }
  }
  return {
    score,
    label: "Low",
    badge: "border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-950/70 dark:text-green-300",
    icon: "✓",
  }
}

function Projects({ globalSearchQuery, onClearSearch, drillDownParams, onClearDrillDown }) {
  const [projects, setProjects] = useState([])
  const [totalCount, setTotalCount] = useState(0)
  const [states, setStates] = useState([])
  const [districts, setDistricts] = useState([])

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  const [keyword, setKeyword] = useState("")
  const [state, setState] = useState("")
  const [district, setDistrict] = useState("")
  const [status, setStatus] = useState("")
  const [sortBy, setSortBy] = useState("")
  const [sortDir, setSortDir] = useState("desc")
  const [currentPage, setCurrentPage] = useState(1)
  const [selectedProjectId, setSelectedProjectId] = useState(null)
  const [compareIds, setCompareIds] = useState([])
  const [showComparison, setShowComparison] = useState(false)
  const [globalSearchApplied, setGlobalSearchApplied] = useState(false)

  const rowsPerPage = 15

  // Use a ref to track the previous globalSearchQuery to detect changes
  const prevGlobalQueryRef = useRef(null)
  useEffect(() => {
    if (globalSearchQuery && globalSearchQuery.trim() && globalSearchQuery !== prevGlobalQueryRef.current) {
      prevGlobalQueryRef.current = globalSearchQuery
      setKeyword(globalSearchQuery.trim())
      setCurrentPage(1)
      setGlobalSearchApplied(true)
      if (onClearSearch) onClearSearch()
    }
  }, [globalSearchQuery, onClearSearch])

  // Handle drill-down params from Overview
  useEffect(() => {
    if (drillDownParams) {
      if (drillDownParams.state) setState(drillDownParams.state)
      if (drillDownParams.district) setDistrict(drillDownParams.district)
      if (drillDownParams.status) setStatus(drillDownParams.status)
      if (drillDownParams.keyword) setKeyword(drillDownParams.keyword)
      setCurrentPage(1)
      if (onClearDrillDown) onClearDrillDown()
    }
  }, [drillDownParams, onClearDrillDown])

  useEffect(() => {
    async function loadStatesList() {
      try {
        const data = await getStates()
        if (Array.isArray(data)) setStates(data)
      } catch (err) {
        console.error("Failed to load states:", err)
      }
    }
    loadStatesList()
  }, [])

  useEffect(() => {
    async function loadDistrictsList() {
      if (!state) {
        setDistricts([])
        setDistrict("")
        return
      }
      try {
        const data = await getDistricts(state)
        if (Array.isArray(data)) setDistricts(data)
      } catch (err) {
        console.error("Failed to load districts:", err)
      }
    }
    loadDistrictsList()
  }, [state])

  const fetchProjectsData = useCallback(async () => {
    try {
      setLoading(true)
      setError("")

      const skip = (currentPage - 1) * rowsPerPage
      let response

      if (keyword.trim()) {
        response = await searchProjects({
          q: keyword.trim(),
          state: state || undefined,
          district: district || undefined,
          status: status || undefined,
          sort_by: sortBy || undefined,
          sort_dir: sortBy ? sortDir : undefined,
          skip,
          limit: rowsPerPage,
        })
        if (response && response.results) {
          setProjects(response.results)
          setTotalCount(response.total || response.results.length)
        }
      } else {
        const [projList, searchCount] = await Promise.all([
          getProjects({
            state: state || undefined,
            district: district || undefined,
            status: status || undefined,
            sort_by: sortBy || undefined,
            sort_dir: sortBy ? sortDir : undefined,
            skip,
            limit: rowsPerPage,
          }),
          searchProjects({
            state: state || undefined,
            district: district || undefined,
            status: status || undefined,
            limit: 1,
          }),
        ])
        setProjects(Array.isArray(projList) ? projList : [])
        setTotalCount(searchCount?.total || (Array.isArray(projList) ? projList.length : 0))
      }
    } catch (err) {
      console.error("Projects error:", err)
      setError("Failed to load projects from backend. Check connection.")
    } finally {
      setLoading(false)
    }
  }, [keyword, state, district, status, currentPage, sortBy, sortDir])

  useEffect(() => {
    fetchProjectsData()
  }, [fetchProjectsData])

  const handleOpenDetail = (proj) => {
    setSelectedProjectId(proj.id)
  }

  const handleToggleCompare = (e, projId) => {
    e.stopPropagation()
    setCompareIds((prev) => {
      if (prev.includes(projId)) return prev.filter((id) => id !== projId)
      if (prev.length >= 3) return prev
      return [...prev, projId]
    })
  }

  const totalPages = Math.max(1, Math.ceil(totalCount / rowsPerPage))

  const handleApplySearch = (e) => {
    e.preventDefault()
    setCurrentPage(1)
    fetchProjectsData()
  }

  const handleResetFilters = () => {
    setKeyword("")
    setState("")
    setDistrict("")
    setStatus("")
    setSortBy("")
    setSortDir("desc")
    setCurrentPage(1)
    setGlobalSearchApplied(false)
  }

  return (
    <div className="min-h-screen bg-[#f9f9ff] p-4 sm:p-6 text-[#151c27] transition-colors duration-200 dark:bg-[#111827] dark:text-gray-100">
      <div className="mx-auto max-w-[1440px] space-y-4 sm:space-y-6">

        {/* GLOBAL SEARCH CONTEXT BANNER */}
        {globalSearchApplied && keyword && (
          <div className="flex items-center justify-between rounded-xl border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-950/40">
            <div className="flex items-center gap-3">
              <span className="text-lg">🔍</span>
              <div>
                <p className="text-sm font-bold text-blue-900 dark:text-blue-200">
                  Search results for: <span className="font-mono">{keyword}</span>
                </p>
                <p className="text-xs text-blue-700 dark:text-blue-300">
                  Found {totalCount.toLocaleString("en-IN")} matching project{totalCount !== 1 ? "s" : ""}
                </p>
              </div>
            </div>
            <button
              onClick={() => {
                setKeyword("")
                setGlobalSearchApplied(false)
                setCurrentPage(1)
              }}
              className="rounded-lg border border-blue-300 bg-white px-3 py-1.5 text-xs font-bold text-blue-700 transition hover:bg-blue-100 dark:border-blue-700 dark:bg-blue-900/60 dark:text-blue-200 dark:hover:bg-blue-800"
            >
              Clear Search
            </button>
          </div>
        )}

        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
          <div>
            <h2 className="text-2xl font-bold text-[#031632] dark:text-white">
              Projects Explorer
            </h2>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Live MPLADS projects database with real-time AI risk evaluation.
            </p>
          </div>

          <div className="rounded-lg border border-blue-200 bg-[#e7eefe] px-3.5 py-1.5 font-mono text-xs font-bold text-blue-900 shadow-2xs dark:border-blue-800 dark:bg-blue-950/70 dark:text-blue-200">
            {totalCount.toLocaleString("en-IN")} Total Projects Found
          </div>
        </div>

        <form onSubmit={handleApplySearch} className="rounded-xl border border-gray-200 bg-white p-5 shadow-xs transition-colors dark:border-gray-700/80 dark:bg-[#1f2937]">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-gray-700 dark:text-gray-200">
                Search Work / Type
              </label>
              <input
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="Search by keywords..."
                className="mt-1.5 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-2xs outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-[#111827] dark:text-white"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-gray-700 dark:text-gray-200">
                State
              </label>
              <select
                value={state}
                onChange={(e) => {
                  setState(e.target.value)
                  setCurrentPage(1)
                }}
                className="mt-1.5 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-2xs outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-[#111827] dark:text-white"
              >
                <option value="">All States</option>
                {states.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-gray-700 dark:text-gray-200">
                District
              </label>
              <select
                value={district}
                disabled={!state}
                onChange={(e) => {
                  setDistrict(e.target.value)
                  setCurrentPage(1)
                }}
                className="mt-1.5 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-2xs outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 disabled:opacity-50 dark:border-gray-600 dark:bg-[#111827] dark:text-white"
              >
                <option value="">{state ? "All Districts" : "Select State First"}</option>
                {districts.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-gray-700 dark:text-gray-200">
                Execution Status
              </label>
              <select
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value)
                  setCurrentPage(1)
                }}
                className="mt-1.5 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-2xs outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-[#111827] dark:text-white"
              >
                <option value="">All Statuses</option>
                <option value="Completed">Completed</option>
                <option value="Ongoing">Ongoing</option>
                <option value="Recommended">Recommended</option>
              </select>
            </div>
          </div>

          {/* SORT ROW */}
          <div className="mt-4 flex flex-wrap items-center gap-1.5 sm:gap-3 border-t border-gray-100 pt-3 dark:border-gray-700/60">
            <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Sort:</span>
            {[
              { value: "", label: "Default" },
              { value: "id", label: "Project ID" },
              { value: "project_name", label: "Name" },
              { value: "sanctioned_amount", label: "Sanctioned" },
              { value: "expenditure", label: "Expenditure" },
              { value: "completion_percentage", label: "Progress" },
              { value: "state", label: "State" },
            ].map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => {
                  if (sortBy === opt.value) {
                    setSortDir((d) => d === "asc" ? "desc" : "asc")
                  } else {
                    setSortBy(opt.value)
                    setSortDir(opt.value === "id" || opt.value === "project_name" || opt.value === "state" ? "asc" : "desc")
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
            {sortBy && (
              <button
                type="button"
                onClick={() => { setSortBy(""); setCurrentPage(1) }}
                className="rounded-lg border border-gray-200 px-2 py-1.5 text-[10px] font-bold text-gray-400 hover:text-gray-700 dark:border-gray-600 dark:hover:text-gray-200"
              >
                ✕ Clear
              </button>
            )}
          </div>

          <div className="mt-3 flex items-center justify-between">
            <div className="flex gap-2">
              <button
                type="submit"
                className="rounded-lg bg-[#031632] px-4 sm:px-5 py-2 text-xs font-bold uppercase tracking-wider text-white shadow-2xs transition hover:bg-[#1a2b48] dark:bg-blue-600 dark:hover:bg-blue-700"
              >
                Search
              </button>
              <button
                type="button"
                onClick={handleResetFilters}
                className="rounded-lg border border-gray-300 bg-white px-3 sm:px-4 py-2 text-xs font-bold uppercase tracking-wider text-gray-700 shadow-2xs transition hover:bg-gray-50 dark:border-gray-600 dark:bg-[#111827] dark:text-gray-200 dark:hover:bg-gray-800"
              >
                Reset
              </button>
            </div>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Page {currentPage} of {totalPages}
            </span>
          </div>
        </form>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs font-semibold text-red-700 dark:border-red-800/60 dark:bg-red-950/40 dark:text-red-300">
            ⚠ {error}
          </div>
        )}

        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xs transition-colors dark:border-gray-700/80 dark:bg-[#1f2937]">
          {loading ? (
            <div className="p-16 text-center text-gray-500 dark:text-gray-400">
              <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-600 border-r-transparent" />
              <p className="mt-3 text-sm font-medium">Fetching records from backend database...</p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                {/* DESKTOP TABLE */}
                <div className="hidden lg:block overflow-x-auto">
                <table className="w-full min-w-[900px]">
                  <thead>
                    <tr className="border-b border-gray-200 bg-gray-50 text-left text-xs font-bold uppercase tracking-wider text-gray-700 dark:border-gray-700 dark:bg-[#172033] dark:text-gray-300">
                      <th className="p-4 w-8"></th>
                      <th className="p-4">ID</th>
                      <th className="p-4">Work Name & Category</th>
                      <th className="p-4">Location</th>
                      <th className="p-4 text-right">Sanctioned</th>
                      <th className="p-4 text-right">Expenditure</th>
                      <th className="p-4 text-center">Status</th>
                      <th className="p-4 text-center">AI Risk Flag</th>
                      <th className="p-4 text-center">Details</th>
                    </tr>
                  </thead>

                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700/60">
                    {projects.map((proj) => {
                      const riskBadge = getRiskScoreBadge(proj)
                      return (
                        <tr
                          key={proj.id}
                          onClick={() => handleOpenDetail(proj)}
                          className="cursor-pointer transition hover:bg-blue-50/40 dark:hover:bg-[#253247]"
                        >
                          <td className="p-4">
                            <input
                              type="checkbox"
                              checked={compareIds.includes(proj.id)}
                              onChange={(e) => handleToggleCompare(e, proj.id)}
                              onClick={(e) => e.stopPropagation()}
                              className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                            />
                          </td>
                          <td className="p-4 font-mono text-xs font-bold text-gray-500 dark:text-gray-400">
                            #{proj.id}
                          </td>
                          <td className="max-w-[320px] p-4">
                            <p className="truncate font-semibold text-gray-900 dark:text-white" title={proj.project_name}>
                              {proj.project_name || "Unnamed Project"}
                            </p>
                            <p className="truncate text-xs text-gray-500 dark:text-gray-400">
                              {proj.project_type || "General"}
                            </p>
                          </td>
                          <td className="p-4 text-xs">
                            <p className="font-semibold text-gray-900 dark:text-gray-200">
                              {proj.district || proj.state || "N/A"}
                            </p>
                            <p className="text-gray-500 dark:text-gray-400">{proj.state}</p>
                          </td>
                          <td className="p-4 text-right font-mono text-xs font-semibold text-gray-900 dark:text-gray-200">
                            {formatMoney(proj.sanctioned_amount)}
                          </td>
                          <td className="p-4 text-right font-mono text-xs font-semibold text-gray-900 dark:text-gray-200">
                            {formatMoney(proj.expenditure)}
                          </td>
                          <td className="p-4 text-center">
                            <span className="rounded-md border border-gray-200 bg-gray-100 px-2 py-0.5 text-xs font-medium dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200">
                              {proj.status || "Ongoing"}
                            </span>
                          </td>
                          <td className="p-4 text-center">
                            <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-bold ${riskBadge.badge}`}>
                              {riskBadge.icon} {riskBadge.label}
                            </span>
                          </td>
                          <td className="p-4 text-center">
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                handleOpenDetail(proj)
                              }}
                              className="rounded p-1 text-gray-600 hover:bg-gray-200 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-white"
                            >
                              👁
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                </div>

                {/* MOBILE CARD VIEW */}
                <div className="lg:hidden divide-y divide-gray-200 dark:divide-gray-700/60">
                  {projects.map((proj) => {
                    const riskBadge = getRiskScoreBadge(proj)
                    return (
                      <div
                        key={proj.id}
                        onClick={() => handleOpenDetail(proj)}
                        className="p-4 cursor-pointer transition hover:bg-blue-50/40 dark:hover:bg-[#253247]"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-mono text-[10px] font-bold text-gray-400">#{proj.id}</span>
                              <span className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-bold ${riskBadge.badge}`}>
                                {riskBadge.icon} {riskBadge.label}
                              </span>
                              <span className="rounded-md border border-gray-200 bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200">
                                {proj.status || "Ongoing"}
                              </span>
                            </div>
                            <p className="mt-1 truncate font-semibold text-sm text-gray-900 dark:text-white" title={proj.project_name}>
                              {proj.project_name || "Unnamed Project"}
                            </p>
                            <p className="text-[11px] text-gray-500 dark:text-gray-400">
                              {proj.district || ""}{proj.district && proj.state ? ", " : ""}{proj.state || "N/A"} • {proj.project_type || "General"}
                            </p>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <input
                              type="checkbox"
                              checked={compareIds.includes(proj.id)}
                              onChange={(e) => handleToggleCompare(e, proj.id)}
                              onClick={(e) => e.stopPropagation()}
                              className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                            />
                          </div>
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                          <div className="flex justify-between">
                            <span className="text-gray-500 dark:text-gray-400">Sanctioned</span>
                            <span className="font-mono font-semibold text-gray-900 dark:text-gray-200">{formatMoney(proj.sanctioned_amount)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-500 dark:text-gray-400">Spent</span>
                            <span className="font-mono font-semibold text-gray-900 dark:text-gray-200">{formatMoney(proj.expenditure)}</span>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>

                {projects.length === 0 && (
                  <div className="p-12 text-center text-xs text-gray-500 dark:text-gray-400">
                    No projects matched the search filters.
                  </div>
                )}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 sm:gap-4 border-t border-gray-200 bg-gray-50 p-3 sm:p-4 dark:border-gray-700 dark:bg-[#172033]">
                <div className="flex items-center gap-3">
                  <span className="text-xs text-gray-600 dark:text-gray-400">
                  Showing <strong>{totalCount === 0 ? 0 : (currentPage - 1) * rowsPerPage + 1}</strong> to{" "}
                  <strong>{Math.min(currentPage * rowsPerPage, totalCount)}</strong> of <strong>{totalCount.toLocaleString("en-IN")}</strong> records
                  </span>
                  {compareIds.length >= 2 && (
                    <button
                      onClick={() => setShowComparison(true)}
                      className="rounded-lg bg-blue-600 px-3 py-1.5 text-[10px] font-bold text-white transition hover:bg-blue-700"
                    >
                      Compare {compareIds.length} Projects
                    </button>
                  )}
                  {compareIds.length > 0 && (
                    <button
                      onClick={() => setCompareIds([])}
                      className="rounded-lg border border-gray-300 px-2 py-1 text-[10px] font-bold text-gray-500 hover:text-gray-700 dark:border-gray-600 dark:hover:text-gray-200"
                    >
                      Clear ({compareIds.length})
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    disabled={currentPage === 1}
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 shadow-2xs transition hover:bg-gray-50 disabled:opacity-40 dark:border-gray-600 dark:bg-[#1f2937] dark:text-gray-200 dark:hover:bg-gray-700"
                  >
                    ← Previous
                  </button>

                  <span className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 font-mono text-xs font-bold text-gray-700 dark:border-gray-600 dark:bg-[#1f2937] dark:text-gray-200">
                    {currentPage} / {totalPages}
                  </span>

                  <button
                    disabled={currentPage >= totalPages}
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 shadow-2xs transition hover:bg-gray-50 disabled:opacity-40 dark:border-gray-600 dark:bg-[#1f2937] dark:text-gray-200 dark:hover:bg-gray-700"
                  >
                    Next →
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Project Detail Panel */}
      {selectedProjectId && (
        <ProjectDetail projectId={selectedProjectId} onClose={() => setSelectedProjectId(null)} />
      )}

      {/* Comparison Modal */}
      {showComparison && compareIds.length >= 2 && (
        <ComparisonModal projectIds={compareIds} onClose={() => setShowComparison(false)} onRemove={(id) => setCompareIds((prev) => prev.filter((i) => i !== id))} />
      )}
    </div>
  )
}

/* Comparison Modal Component */
function ComparisonModal({ projectIds, onClose, onRemove }) {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all(projectIds.map((id) => getProjectDetail(id).catch(() => null)))
      .then((results) => setProjects(results.filter(Boolean).map((r) => ({ ...r.project, risk: r.risk }))))
      .finally(() => setLoading(false))
  }, [projectIds])

  function fmtMoney(v) {
    const n = Number(v || 0)
    if (n >= 10000000) return `₹${(n / 10000000).toFixed(2)} Cr`
    if (n >= 100000) return `₹${(n / 100000).toFixed(2)} L`
    return `₹${n.toLocaleString("en-IN")}`
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 sm:p-4 backdrop-blur-2xs" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="flex max-h-[90vh] sm:max-h-[85vh] w-full sm:max-w-4xl flex-col rounded-t-2xl sm:rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-[#1f2937]">
        <div className="flex items-start justify-between border-b border-gray-200 p-5 dark:border-gray-700">
          <div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Project Comparison</h3>
            <p className="text-xs text-gray-500">Comparing {projects.length} projects side by side</p>
          </div>
          <button onClick={onClose} className="rounded p-1 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700">✕</button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          {loading ? (
            <div className="p-8 text-center">
              <div className="inline-block h-6 w-6 animate-spin rounded-full border-4 border-solid border-blue-600 border-r-transparent" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="p-3 text-[10px] font-bold uppercase text-gray-400">Metric</th>
                    {projects.map((p) => (
                      <th key={p.id} className="p-3">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-gray-400">#{p.id}</span>
                          <button onClick={() => onRemove(p.id)} className="text-gray-400 hover:text-red-500">✕</button>
                        </div>
                        <p className="mt-0.5 font-semibold text-gray-900 dark:text-white" title={p.project_name}>{(p.project_name || "Unnamed").substring(0, 40)}</p>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700/60">
                  {[
                    { label: "State", key: "state" },
                    { label: "District", key: "district" },
                    { label: "Category", key: "project_type" },
                    { label: "Status", key: "status" },
                    { label: "Sanctioned", key: "sanctioned_amount", money: true },
                    { label: "Expenditure", key: "expenditure", money: true },
                    { label: "Utilization", fn: (p) => `${(p.sanctioned_amount > 0 ? (p.expenditure / p.sanctioned_amount * 100) : 0).toFixed(1)}%` },
                    { label: "Physical Progress", key: "completion_percentage", pct: true },
                    { label: "Risk Score", fn: (p) => p.risk ? `${p.risk.risk_score}/100` : "N/A" },
                    { label: "Risk Level", fn: (p) => p.risk?.risk_level || "None" },
                    { label: "ML Anomaly", fn: (p) => p.risk?.ml_anomaly ? "Yes" : "No" },
                  ].map((row) => (
                    <tr key={row.label}>
                      <td className="p-3 font-bold text-gray-500">{row.label}</td>
                      {projects.map((p) => {
                        let val = row.fn ? row.fn(p) : (row.money ? fmtMoney(p[row.key]) : row.pct ? `${p[row.key] || 0}%` : p[row.key] || "N/A")
                        // Highlight differences
                        const vals = projects.map((pp) => row.fn ? row.fn(pp) : (row.money ? fmtMoney(pp[row.key]) : row.pct ? `${pp[row.key] || 0}%` : pp[row.key] || "N/A"))
                        const allSame = vals.every((v) => v === vals[0])
                        return (
                          <td key={p.id} className={`p-3 font-mono ${!allSame ? "font-bold text-blue-700 dark:text-blue-300" : "text-gray-600 dark:text-gray-300"}`}>{val}</td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <div className="border-t border-gray-200 p-4 text-right dark:border-gray-700">
          <button onClick={onClose} className="rounded-lg bg-[#031632] px-5 py-2 text-xs font-bold text-white dark:bg-blue-600">Close</button>
        </div>
      </div>
    </div>
  )
}

export default Projects
