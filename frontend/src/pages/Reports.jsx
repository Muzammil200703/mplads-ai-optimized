import { useEffect, useState } from "react"
import { getStates, getDistricts } from "../services/api"

const API_URL = import.meta.env.VITE_API_URL !== undefined
  ? import.meta.env.VITE_API_URL
  : (import.meta.env.PROD ? "" : "http://127.0.0.1:8000")

function Reports() {
  const [reportType, setReportType] = useState("Project Audit Report")
  const [format, setFormat] = useState("CSV Dataset (.csv)")
  const [states, setStates] = useState([])
  const [districts, setDistricts] = useState([])
  const [selectedState, setSelectedState] = useState("")
  const [selectedDistrict, setSelectedDistrict] = useState("")
  const [selectedRiskLevel, setSelectedRiskLevel] = useState("")
  const [sortBy, setSortBy] = useState("")
  const [sortDir, setSortDir] = useState("desc")
  const [exportCount, setExportCount] = useState(null)
  const [downloading, setDownloading] = useState(false)
  const [downloadNotice, setDownloadNotice] = useState("")
  const [error, setError] = useState("")

  useEffect(() => {
    getStates().then((s) => { if (Array.isArray(s)) setStates(s) }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!selectedState) { setDistricts([]); setSelectedDistrict(""); return }
    getDistricts(selectedState).then((d) => { if (Array.isArray(d)) setDistricts(d) }).catch(() => {})
  }, [selectedState])

  // Fetch count of records that would be exported
  useEffect(() => {
    async function fetchCount() {
      try {
        const params = new URLSearchParams()
        params.set("report_type", reportType)
        if (selectedState) params.set("state", selectedState)
        if (selectedDistrict) params.set("district", selectedDistrict)
        if (selectedRiskLevel) params.set("risk_level", selectedRiskLevel)

        const r = await fetch(`${API_URL}/export/report-count?${params.toString()}`)
        if (r.ok) {
          const data = await r.json()
          setExportCount(data.total_records)
        }
      } catch {
        setExportCount(null)
      }
    }
    fetchCount()
  }, [reportType, selectedState, selectedDistrict, selectedRiskLevel])

  const handleExport = async () => {
    try {
      setDownloading(true)
      setError("")
      setDownloadNotice("")

      const params = new URLSearchParams()
      params.set("report_type", reportType)
      if (selectedState) params.set("state", selectedState)
      if (selectedDistrict) params.set("district", selectedDistrict)
      if (selectedRiskLevel && reportType === "Anomaly Summary Report") params.set("risk_level", selectedRiskLevel)
      if (sortBy) {
        params.set("sort_by", sortBy)
        params.set("sort_dir", sortDir)
      }

      if (format.includes("CSV")) {
        const r = await fetch(`${API_URL}/export/report?${params.toString()}`)
        if (!r.ok) throw new Error("Export failed")
        const blob = await r.blob()
        const url = URL.createObjectURL(blob)
        const link = document.createElement("a")
        link.href = url
        const disposition = r.headers.get("content-disposition")
        const filenameMatch = disposition && disposition.match(/filename="?(.+?)"?$/)
        link.download = filenameMatch ? filenameMatch[1] : `MPLADS_Report_${new Date().toISOString().slice(0, 10)}.csv`
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        URL.revokeObjectURL(url)
        setDownloadNotice(`CSV exported with ${exportCount?.toLocaleString("en-IN") || "?"} records`)
      } else if (format.includes("JSON")) {
        const r = await fetch(`${API_URL}/export/report?${params.toString()}`)
        if (!r.ok) throw new Error("Export failed")
        const text = await r.text()
        // Convert CSV to JSON
        const lines = text.split("\n").filter(Boolean)
        const headers = lines[0].split(",")
        const rows = lines.slice(1).map((line) => {
          const values = line.split(",")
          const obj = {}
          headers.forEach((h, i) => { obj[h] = values[i] || "" })
          return obj
        })
        const blob = new Blob([JSON.stringify(rows, null, 2)], { type: "application/json" })
        const url = URL.createObjectURL(blob)
        const link = document.createElement("a")
        link.href = url
        link.download = `MPLADS_Report_${new Date().toISOString().slice(0, 10)}.json`
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        URL.revokeObjectURL(url)
        setDownloadNotice(`JSON exported with ${rows.length} records`)
      } else {
        window.print()
        setDownloadNotice("Print dialog opened.")
      }
      setTimeout(() => setDownloadNotice(""), 5000)
    } catch (err) {
      console.error("Export error:", err)
      setError("Export failed. Make sure the backend is running.")
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#f9f9ff] p-6 text-[#151c27] transition-colors duration-200 dark:bg-[#111827] dark:text-[#f3f4f6]">
      <div className="mx-auto max-w-[1440px] space-y-6">
        <div>
          <h2 className="text-2xl font-bold text-[#031632] dark:text-white">
            Audit Reports & Data Export
          </h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Generate and export official MPLADS audit reports from the full server-side dataset.
          </p>
        </div>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs font-semibold text-red-700 dark:bg-red-950/40 dark:text-red-300">
            ⚠ {error}
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Settings Panel */}
          <div className="space-y-4 lg:col-span-4">
            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-xs dark:border-gray-700 dark:bg-[#1f2937]">
              <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-gray-400">
                Report Settings
              </h3>
              <div className="space-y-3">
                <div>
                  <label className="text-xs font-semibold">Report Type</label>
                  <select value={reportType} onChange={(e) => setReportType(e.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-[#111827]">
                    <option>Project Audit Report</option>
                    <option>Anomaly Summary Report</option>
                    <option>Regional Risk Report</option>
                    <option>Financial Utilization Report</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs font-semibold">State Scope</label>
                  <select value={selectedState} onChange={(e) => setSelectedState(e.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-[#111827]">
                    <option value="">All States (Nationwide)</option>
                    {states.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>

                <div>
                  <label className="text-xs font-semibold">District Scope</label>
                  <select value={selectedDistrict} disabled={!selectedState} onChange={(e) => setSelectedDistrict(e.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm disabled:opacity-50 dark:border-gray-600 dark:bg-[#111827]">
                    <option value="">{selectedState ? "All Districts" : "Select State First"}</option>
                    {districts.map((d) => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>

                {reportType === "Anomaly Summary Report" && (
                  <div>
                    <label className="text-xs font-semibold">Risk Level</label>
                    <select value={selectedRiskLevel} onChange={(e) => setSelectedRiskLevel(e.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-[#111827]">
                      <option value="">All Risk Levels</option>
                      <option value="High">High Risk</option>
                      <option value="Medium">Medium Risk</option>
                      <option value="Low">Low Risk</option>
                    </select>
                  </div>
                )}

                <div>
                  <label className="text-xs font-semibold">Export Format</label>
                  <select value={format} onChange={(e) => setFormat(e.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-[#111827]">
                    <option>CSV Dataset (.csv)</option>
                    <option>JSON Report (.json)</option>
                    <option>Print / PDF View</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs font-semibold">Sort By</label>
                  <div className="mt-1 flex gap-2">
                    <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-[#111827]">
                      <option value="">Default Order</option>
                      <option value="id">Project ID</option>
                      <option value="project_name">Project Name</option>
                      <option value="sanctioned_amount">Sanctioned Amount</option>
                      <option value="expenditure">Expenditure</option>
                      <option value="completion_percentage">Progress</option>
                      <option value="state">State</option>
                    </select>
                    <button
                      onClick={() => setSortDir((d) => d === "asc" ? "desc" : "asc")}
                      disabled={!sortBy}
                      className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-bold disabled:opacity-40 dark:border-gray-600 dark:bg-[#111827]"
                    >
                      {sortDir === "asc" ? "↑ Asc" : "↓ Desc"}
                    </button>
                  </div>
                </div>

                {/* Export count preview */}
                {exportCount !== null && (
                  <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-center dark:border-blue-900/60 dark:bg-blue-950/30">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-blue-600 dark:text-blue-300">Full Dataset Export</p>
                    <p className="mt-1 font-mono text-lg font-bold text-blue-800 dark:text-blue-200">
                      {exportCount.toLocaleString("en-IN")} records
                    </p>
                    <p className="text-[10px] text-blue-500 dark:text-blue-400">
                      Server-side query — all matching records will be exported
                    </p>
                  </div>
                )}

                <button
                  onClick={handleExport}
                  disabled={downloading || exportCount === 0}
                  className="mt-4 w-full rounded-lg bg-[#031632] py-2.5 text-xs font-bold uppercase tracking-wider text-white shadow-xs transition hover:bg-[#1a2b48] disabled:opacity-50 dark:bg-blue-600 dark:hover:bg-blue-700"
                >
                  {downloading ? "Generating Report..." : `Download Report${exportCount !== null ? ` (${exportCount.toLocaleString("en-IN")} records)` : ""}`}
                </button>

                {downloadNotice && (
                  <p className="mt-2 text-center text-xs font-semibold text-green-600 dark:text-green-400">
                    ✓ {downloadNotice}
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Preview Panel */}
          <div className="lg:col-span-8">
            <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-xs dark:border-gray-700 dark:bg-[#1f2937]">
              <div className="mb-4 border-b border-gray-100 pb-3 text-center dark:border-gray-700">
                <h2 className="text-xl font-bold">{reportType}</h2>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Scope: {selectedState || "All States"}
                  {selectedDistrict ? ` > ${selectedDistrict}` : ""}
                  {reportType === "Anomaly Summary Report" && selectedRiskLevel ? ` | Risk: ${selectedRiskLevel}` : ""}
                  {" | "}
                  <span className="font-bold text-blue-600 dark:text-blue-400">
                    {exportCount !== null ? `${exportCount.toLocaleString("en-IN")} total records` : "Loading..."}
                  </span>
                </p>
              </div>

              <div className="space-y-4">
                <div className="rounded-lg border border-gray-200 bg-gray-50 p-5 text-center dark:border-gray-700 dark:bg-[#111827]">
                  <span className="text-3xl">📊</span>
                  <h3 className="mt-3 text-sm font-bold">Server-Side Report Generation</h3>
                  <p className="mt-2 max-w-md text-xs text-gray-500 dark:text-gray-400">
                    When you click <strong>Download Report</strong>, the backend queries the full MPLADS database
                    using your selected filters and generates the CSV/JSON file server-side.
                    This ensures you receive <strong>all matching records</strong>, not just the preview subset.
                  </p>
                  <div className="mt-4 grid grid-cols-3 gap-4 text-center">
                    <div>
                      <p className="text-[10px] font-bold uppercase text-gray-400">Report Type</p>
                      <p className="mt-1 text-xs font-semibold">{reportType}</p>
                    </div>
                    <div>
                      <p className="text-[10px] font-bold uppercase text-gray-400">Scope</p>
                      <p className="mt-1 text-xs font-semibold">{selectedState || "Nationwide"}</p>
                    </div>
                    <div>
                      <p className="text-[10px] font-bold uppercase text-gray-400">Format</p>
                      <p className="mt-1 text-xs font-semibold">{format}</p>
                    </div>
                  </div>
                </div>

                <div className="rounded-lg border border-green-200 bg-green-50 p-4 dark:border-green-900/40 dark:bg-green-950/20">
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 text-green-500">✓</span>
                    <div>
                      <p className="text-xs font-bold text-green-700 dark:text-green-400">Export includes all matching records</p>
                      <p className="mt-0.5 text-[10px] text-green-600 dark:text-green-500">
                        The server queries the database directly. Filters for state, district, risk level, and status
                        are applied at the SQL level for maximum efficiency.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Reports
