import { useEffect, useState } from "react"
import { getDataQualityRecords } from "../services/api"

const API_URL = import.meta.env.VITE_API_URL !== undefined
  ? import.meta.env.VITE_API_URL
  : (import.meta.env.PROD ? "" : "http://127.0.0.1:8000")

function formatMoney(value) {
  const number = Number(value || 0)
  if (number >= 10000000) return `₹${(number / 10000000).toFixed(2)} Cr`
  if (number >= 100000) return `₹${(number / 100000).toFixed(2)} L`
  return `₹${number.toLocaleString("en-IN")}`
}

function DataQuality() {
  const [dataQuality, setDataQuality] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [selectedIssue, setSelectedIssue] = useState(null)
  const [issueRecords, setIssueRecords] = useState([])
  const [issueTotal, setIssueTotal] = useState(0)
  const [issueFlagReason, setIssueFlagReason] = useState("")
  const [loadingRecords, setLoadingRecords] = useState(false)

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true)
        setError("")
        const r = await fetch(`${API_URL}/data-quality`)
        if (!r.ok) throw new Error("Failed to load data quality")
        const data = await r.json()
        setDataQuality(data)
      } catch (err) {
        console.error("Data quality error:", err)
        setError("Failed to load data quality analysis. Make sure the backend is running.")
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  const handleViewRecords = async (issue) => {
    setSelectedIssue(issue)
    setIssueRecords([])
    setIssueTotal(0)
    setIssueFlagReason("")
    setLoadingRecords(true)
    try {
      const data = await getDataQualityRecords({ field: issue.field, limit: 50 })
      setIssueRecords(data?.records || [])
      setIssueTotal(data?.total || 0)
      setIssueFlagReason(data?.flag_reason || "")
    } catch (err) {
      console.error("Failed to load records:", err)
      setIssueRecords([])
    } finally {
      setLoadingRecords(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[#f9f9ff] p-4 sm:p-6 dark:bg-[#111827]">
        <h1 className="text-2xl font-bold text-[#031632] dark:text-white">Data Quality Monitor</h1>
        <div className="mt-6 rounded-xl border border-gray-200 bg-white p-16 text-center dark:border-gray-700 dark:bg-[#1f2937]">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-600 border-r-transparent" />
          <p className="mt-3 text-sm font-medium">Analyzing 83,000+ MPLADS records for data quality issues...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#f9f9ff] p-4 sm:p-6 dark:bg-[#111827]">
        <h1 className="text-2xl font-bold text-[#031632] dark:text-white">Data Quality Monitor</h1>
        <div className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-medium text-red-700 dark:border-red-800/60 dark:bg-red-950/40 dark:text-red-300">
          ⚠ {error}
        </div>
      </div>
    )
  }

  const issues = dataQuality?.issues || []
  const categories = [...new Set(issues.map((i) => i.category))]

  return (
    <div className="min-h-screen bg-[#f9f9ff] p-4 sm:p-6 text-[#151c27] transition-colors duration-200 dark:bg-[#111827] dark:text-[#f3f4f6]">
      <div className="mx-auto max-w-[1440px] space-y-4 sm:space-y-6">

        {/* HEADER */}
        <div>
          <h2 className="text-2xl font-bold text-[#031632] dark:text-white">
            Data Quality Monitor
          </h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Automated analysis of <strong>{dataQuality?.total_records_checked?.toLocaleString("en-IN") || 0}</strong> MPLADS records for data integrity issues.
          </p>
        </div>

        {/* SUMMARY CARDS */}
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-[#1f2937]">
            <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Records Checked</p>
            <p className="mt-1 font-mono text-2xl font-bold text-blue-600">
              {dataQuality?.total_records_checked?.toLocaleString("en-IN") || 0}
            </p>
          </div>
          <div className="rounded-xl border border-amber-200 bg-white p-4 shadow-sm dark:border-amber-900/40 dark:bg-[#1f2937]">
            <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Records with Issues</p>
            <p className="mt-1 font-mono text-2xl font-bold text-amber-600">
              {dataQuality?.records_with_issues?.toLocaleString("en-IN") || 0}
            </p>
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-[#1f2937]">
            <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Issue Categories</p>
            <p className="mt-1 font-mono text-2xl font-bold text-purple-600">
              {dataQuality?.issue_categories || 0}
            </p>
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-[#1f2937]">
            <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">% Affected</p>
            <p className="mt-1 font-mono text-2xl font-bold text-red-600">
              {dataQuality?.percentage_affected || 0}%
            </p>
          </div>
        </div>

        {/* DISTINGUISH FROM ANOMALIES */}
        <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4 dark:border-blue-900/40 dark:bg-blue-950/20">
          <div className="flex items-start gap-3">
            <span className="text-lg">ℹ</span>
            <div>
              <p className="text-xs font-bold text-blue-800 dark:text-blue-200">Understanding Data Quality vs Anomalies</p>
              <p className="mt-1 text-[11px] text-blue-600 dark:text-blue-300">
                <strong>Data Quality Issues</strong> identify missing, invalid, or inconsistent data fields (schema problems).
                <strong> Financial/Risk Anomalies</strong> flag suspicious expenditure/progress patterns in otherwise valid data.
                <strong> AI/ML Anomalies</strong> are statistical outliers detected by the Isolation Forest model across multiple dimensions.
              </p>
            </div>
          </div>
        </div>

        {/* ISSUES BY CATEGORY */}
        {categories.map((category) => (
          <div key={category}>
            <h3 className="mb-3 text-sm font-bold text-[#031632] dark:text-white">
              {category === "Missing Data" && "📋 Missing Data Fields"}
              {category === "Invalid Financial" && "💰 Invalid Financial Values"}
              {category === "Invalid Progress" && "📊 Invalid Progress Values"}
              {category === "Inconsistency" && "⚠ Inconsistencies"}
              {category === "Duplicate Data" && "🔄 Duplicate Data"}
              {!["Missing Data", "Invalid Financial", "Invalid Progress", "Inconsistency", "Duplicate Data"].includes(category) && `🔍 ${category}`}
            </h3>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {issues.filter((i) => i.category === category).map((issue, idx) => (
                <div
                  key={idx}
                  onClick={() => handleViewRecords(issue)}
                  className="relative cursor-pointer overflow-hidden rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md dark:border-gray-700 dark:bg-[#1f2937]"
                >
                  <div className={`absolute left-0 top-0 h-full w-1.5 ${
                    issue.severity === "Critical" ? "bg-red-500" : "bg-amber-500"
                  }`} />
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-xs font-bold text-gray-900 dark:text-white">{issue.field}</p>
                      <p className="mt-1 text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">{issue.description}</p>
                    </div>
                    <span className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                      issue.severity === "Critical"
                        ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
                        : "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                    }`}>
                      {issue.severity}
                    </span>
                  </div>
                  <div className="mt-3 flex items-center justify-between border-t border-gray-100 pt-2 dark:border-gray-700/60">
                    <div>
                      <span className="font-mono text-lg font-bold text-gray-900 dark:text-white">
                        {issue.count.toLocaleString("en-IN")}
                      </span>
                      <span className="ml-1 text-[10px] text-gray-400">records ({issue.percentage}%)</span>
                    </div>
                    <span className="text-[10px] font-semibold text-blue-600 hover:underline dark:text-blue-400">
                      Inspect →
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}

        {issues.length === 0 && !loading && (
          <div className="rounded-xl border border-green-200 bg-green-50 p-8 text-center dark:border-green-900/40 dark:bg-green-950/20">
            <span className="text-3xl">✓</span>
            <h3 className="mt-3 text-sm font-bold text-green-700 dark:text-green-400">No Data Quality Issues Detected</h3>
            <p className="mt-1 text-xs text-green-600 dark:text-green-500">
              All {dataQuality?.total_records_checked?.toLocaleString("en-IN")} records pass quality checks.
            </p>
          </div>
        )}
      </div>

      {/* INSPECT MODAL */}
      {selectedIssue && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 sm:p-4 backdrop-blur-2xs" onClick={() => setSelectedIssue(null)}>
          <div onClick={(e) => e.stopPropagation()} className="flex max-h-[90vh] sm:max-h-[80vh] w-full sm:max-w-3xl flex-col rounded-t-2xl sm:rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-[#1f2937]">
            <div className="flex items-start justify-between border-b border-gray-200 p-5 dark:border-gray-700">
              <div>
                <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                  {selectedIssue.field}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400">{selectedIssue.description}</p>
                <p className="mt-1 font-mono text-xs text-gray-400">
                  {selectedIssue.count.toLocaleString("en-IN")} affected records ({selectedIssue.percentage}%)
                </p>
              </div>
              <button onClick={() => setSelectedIssue(null)} className="rounded p-1 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700">✕</button>
            </div>

            <div className="flex-1 overflow-y-auto p-5">
              {loadingRecords ? (
                <div className="p-8 text-center">
                  <div className="inline-block h-6 w-6 animate-spin rounded-full border-4 border-solid border-blue-600 border-r-transparent" />
                  <p className="mt-2 text-xs text-gray-500">Loading affected records...</p>
                </div>
              ) : issueRecords.length > 0 ? (
                <div className="space-y-3">
                  <div className="flex items-center justify-between rounded-lg bg-blue-50 p-3 dark:bg-blue-950/30">
                    <div>
                      <p className="text-xs font-bold text-blue-800 dark:text-blue-200">
                        {issueTotal.toLocaleString("en-IN")} affected projects
                      </p>
                      {issueFlagReason && (
                        <p className="mt-0.5 text-[11px] text-blue-600 dark:text-blue-300">
                          Flag reason: {issueFlagReason}
                        </p>
                      )}
                    </div>
                    <span className="text-[10px] text-blue-500">
                      Showing {issueRecords.length} of {issueTotal.toLocaleString("en-IN")}
                    </span>
                  </div>

                  {issueRecords.map((rec) => (
                    <div key={rec.id} className="rounded-lg border border-gray-200 bg-gray-50/50 p-3 dark:border-gray-700 dark:bg-[#111827]">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs font-bold text-gray-400">#{rec.id}</span>
                            {rec.status && (
                              <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${
                                rec.status.toLowerCase() === "completed"
                                  ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300"
                                  : rec.status.toLowerCase() === "ongoing"
                                  ? "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                                  : "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300"
                              }`}>{rec.status}</span>
                            )}
                          </div>
                          <p className="mt-1 truncate text-sm font-semibold text-gray-900 dark:text-white" title={rec.project_name}>{rec.project_name || "Unnamed"}</p>
                          <p className="text-[11px] text-gray-500">{rec.state || "N/A"} — {rec.constituency || "N/A"}</p>
                          {issueFlagReason && (
                            <div className="mt-1.5 rounded bg-amber-50 px-2 py-1 dark:bg-amber-950/30">
                              <p className="text-[10px] font-semibold text-amber-700 dark:text-amber-300">⚠ {issueFlagReason}</p>
                            </div>
                          )}
                        </div>
                        <div className="flex-shrink-0 text-right font-mono text-xs">
                          <p className="text-gray-500">Sanctioned</p>
                          <p className="font-bold text-gray-900 dark:text-white">{formatMoney(rec.sanctioned_amount)}</p>
                          <p className="mt-1 text-gray-500">Spent</p>
                          <p className={`font-bold ${rec.expenditure > 0 && rec.completion_percentage === 0 ? "text-red-600 dark:text-red-400" : "text-gray-900 dark:text-white"}`}>{formatMoney(rec.expenditure)}</p>
                          <p className="mt-1 text-gray-500">Progress</p>
                          <p className={`font-bold ${
                            rec.completion_percentage < 0 || rec.completion_percentage > 100
                              ? "text-red-600 dark:text-red-400"
                              : rec.completion_percentage === 0 && rec.expenditure > 0
                              ? "text-amber-600 dark:text-amber-400"
                              : "text-gray-900 dark:text-white"
                          }`}>{rec.completion_percentage}%</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-8 text-center text-xs text-gray-500">
                  No records found for this issue type.
                </div>
              )}
            </div>

            <div className="border-t border-gray-200 p-4 text-right dark:border-gray-700">
              <button onClick={() => setSelectedIssue(null)} className="rounded-lg bg-[#031632] px-5 py-2 text-xs font-bold text-white dark:bg-blue-600">Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default DataQuality
