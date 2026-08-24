import { useEffect, useState, useMemo } from "react"
import { getStateIntelligence } from "../services/api"

function formatMoney(value) {
  const number = Number(value || 0)
  if (number >= 10000000) return `₹${(number / 10000000).toFixed(2)} Cr`
  if (number >= 100000) return `₹${(number / 100000).toFixed(2)} L`
  return `₹${number.toLocaleString("en-IN")}`
}

function StateIntelligence({ onNavigateToProjects }) {
  const [states, setStates] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [sortBy, setSortBy] = useState("total_projects")
  const [sortDir, setSortDir] = useState("desc")
  const [searchTerm, setSearchTerm] = useState("")

  useEffect(() => {
    async function load() {
      try {
        setLoading(true)
        const data = await getStateIntelligence()
        if (Array.isArray(data)) setStates(data)
      } catch (err) {
        console.error("State intelligence error:", err)
        setError("Failed to load state intelligence data.")
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const filteredStates = useMemo(() => {
    let result = [...states]
    if (searchTerm.trim()) {
      const q = searchTerm.trim().toLowerCase()
      result = result.filter((s) => s.state.toLowerCase().includes(q))
    }
    result.sort((a, b) => {
      const aVal = a[sortBy] || 0
      const bVal = b[sortBy] || 0
      if (typeof aVal === "string") {
        return sortDir === "asc" ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal)
      }
      return sortDir === "asc" ? aVal - bVal : bVal - aVal
    })
    return result
  }, [states, sortBy, sortDir, searchTerm])

  const handleSort = (col) => {
    if (sortBy === col) {
      setSortDir((d) => d === "asc" ? "desc" : "asc")
    } else {
      setSortBy(col)
      setSortDir(col === "state" ? "asc" : "desc")
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[#f9f9ff] p-6 dark:bg-[#111827]">
        <h1 className="text-2xl font-bold text-[#031632] dark:text-white">State Intelligence</h1>
        <div className="mt-6 rounded-xl border border-gray-200 bg-white p-16 text-center dark:border-gray-700 dark:bg-[#1f2937]">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-600 border-r-transparent" />
          <p className="mt-3 text-sm font-medium">Loading state intelligence...</p>
        </div>
      </div>
    )
  }

  const columns = [
    { key: "state", label: "State / UT", sortable: true },
    { key: "total_projects", label: "Works", sortable: true },
    { key: "completed_projects", label: "Completed", sortable: true },
    { key: "ongoing_projects", label: "Ongoing", sortable: true },
    { key: "total_sanctioned_amount", label: "Sanctioned", sortable: true, money: true },
    { key: "total_expenditure", label: "Expenditure", sortable: true, money: true },
    { key: "utilization_percentage", label: "Utilization", sortable: true, pct: true },
    { key: "average_completion_percentage", label: "Avg Progress", sortable: true, pct: true },
    { key: "high_risk_projects", label: "High Risk", sortable: true, alert: true },
    { key: "ml_anomaly_projects", label: "ML Anomalies", sortable: true, ml: true },
  ]

  return (
    <div className="min-h-screen bg-[#f9f9ff] p-4 sm:p-6 text-[#151c27] transition-colors duration-200 dark:bg-[#111827] dark:text-[#f3f4f6]">
      <div className="mx-auto max-w-[1440px] space-y-4 sm:space-y-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
          <div>
            <h2 className="text-2xl font-bold text-[#031632] dark:text-white">State Intelligence</h2>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Comprehensive analytics across <strong>{states.length}</strong> states and union territories.
            </p>
          </div>
          <input
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search state..."
            className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm text-gray-900 shadow-2xs outline-none transition focus:border-blue-500 sm:w-64 dark:border-gray-600 dark:bg-[#1f2937] dark:text-white"
          />
        </div>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-medium text-red-700 dark:border-red-800/60 dark:bg-red-950/40 dark:text-red-300">⚠ {error}</div>
        )}

        {/* Sort Controls */}
        <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
          <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Sort:</span>
          {[
            { value: "total_projects", label: "Works" },
            { value: "total_sanctioned_amount", label: "Sanctioned" },
            { value: "total_expenditure", label: "Expenditure" },
            { value: "utilization_percentage", label: "Utilization" },
            { value: "average_completion_percentage", label: "Avg Progress" },
            { value: "high_risk_projects", label: "High Risk" },
            { value: "state", label: "Name" },
          ].map((opt) => (
            <button
              key={opt.value}
              onClick={() => handleSort(opt.value)}
              className={`rounded-lg px-3 py-1.5 text-[11px] font-bold transition ${
                sortBy === opt.value
                  ? "bg-[#031632] text-white dark:bg-blue-600"
                  : "border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:bg-[#1f2937] dark:text-gray-300"
              }`}
            >
              {opt.label}
              {sortBy === opt.value && <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>}
            </button>
          ))}
        </div>

        {/* Table */}
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xs dark:border-gray-700 dark:bg-[#1f2937]">
          {/* DESKTOP TABLE */}
          <div className="hidden lg:block overflow-x-auto">
            <table className="w-full min-w-[1100px]">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 text-left text-xs font-bold uppercase tracking-wider text-gray-700 dark:border-gray-700 dark:bg-[#172033] dark:text-gray-300">
                  {columns.map((col) => (
                    <th
                      key={col.key}
                      className={`p-3 ${col.sortable ? "cursor-pointer select-none hover:text-blue-600" : ""} ${col.money || col.pct || col.alert || col.ml ? "text-right" : ""}`}
                      onClick={() => col.sortable && handleSort(col.key)}
                    >
                      {col.label}
                      {sortBy === col.key && <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700/60">
                {filteredStates.map((s) => (
                  <tr
                    key={s.state}
                    className="cursor-pointer transition hover:bg-blue-50/40 dark:hover:bg-[#253247]"
                    onClick={() => onNavigateToProjects && onNavigateToProjects(s.state)}
                  >
                    <td className="p-3 text-sm font-semibold">{s.state}</td>
                    <td className="p-3 text-right font-mono text-xs">{s.total_projects.toLocaleString("en-IN")}</td>
                    <td className="p-3 text-right font-mono text-xs text-green-600 dark:text-green-400">{s.completed_projects.toLocaleString("en-IN")}</td>
                    <td className="p-3 text-right font-mono text-xs text-blue-600 dark:text-blue-400">{s.ongoing_projects.toLocaleString("en-IN")}</td>
                    <td className="p-3 text-right font-mono text-xs">{formatMoney(s.total_sanctioned_amount)}</td>
                    <td className="p-3 text-right font-mono text-xs">{formatMoney(s.total_expenditure)}</td>
                    <td className="p-3 text-right font-mono text-xs font-bold">{s.utilization_percentage}%</td>
                    <td className="p-3 text-right font-mono text-xs">{s.average_completion_percentage}%</td>
                    <td className="p-3 text-right">
                      {s.high_risk_projects > 0 ? (
                        <span className="rounded bg-red-100 px-1.5 py-0.5 font-mono text-xs font-bold text-red-700 dark:bg-red-950 dark:text-red-300">{s.high_risk_projects}</span>
                      ) : <span className="text-gray-300">0</span>}
                    </td>
                    <td className="p-3 text-right">
                      {s.ml_anomaly_projects > 0 ? (
                        <span className="rounded bg-purple-100 px-1.5 py-0.5 font-mono text-xs font-bold text-purple-700 dark:bg-purple-950 dark:text-purple-300">{s.ml_anomaly_projects}</span>
                      ) : <span className="text-gray-300">0</span>}
                    </td>
                  </tr>
                )                )}
              </tbody>
            </table>
          </div>

          {/* MOBILE CARD VIEW */}
          <div className="lg:hidden divide-y divide-gray-200 dark:divide-gray-700/60">
            {filteredStates.map((s) => (
              <div
                key={s.state}
                className="p-4 cursor-pointer transition hover:bg-blue-50/40 dark:hover:bg-[#253247]"
                onClick={() => onNavigateToProjects && onNavigateToProjects(s.state)}
              >
                <div className="flex items-start justify-between">
                  <p className="font-semibold text-sm">{s.state}</p>
                  <div className="flex items-center gap-1.5">
                    {s.high_risk_projects > 0 && <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-bold text-red-700 dark:bg-red-950 dark:text-red-300">{s.high_risk_projects} High</span>}
                    {s.ml_anomaly_projects > 0 && <span className="rounded bg-purple-100 px-1.5 py-0.5 text-[10px] font-bold text-purple-700 dark:bg-purple-950 dark:text-purple-300">{s.ml_anomaly_projects} ML</span>}
                  </div>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  <div className="flex justify-between"><span className="text-gray-500">Works</span><span className="font-mono font-bold">{s.total_projects.toLocaleString("en-IN")}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">Completed</span><span className="font-mono font-bold text-green-600 dark:text-green-400">{s.completed_projects.toLocaleString("en-IN")}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">Sanctioned</span><span className="font-mono font-semibold">{formatMoney(s.total_sanctioned_amount)}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">Expenditure</span><span className="font-mono font-semibold">{formatMoney(s.total_expenditure)}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">Utilization</span><span className="font-mono font-bold">{s.utilization_percentage}%</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">Avg Progress</span><span className="font-mono">{s.average_completion_percentage}%</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {filteredStates.length === 0 && !loading && (
          <div className="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-[#1f2937]">
            <p className="text-sm text-gray-500">No states match the search term.</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default StateIntelligence
