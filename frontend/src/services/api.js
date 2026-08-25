const API_URL = import.meta.env.VITE_API_URL !== undefined 
  ? import.meta.env.VITE_API_URL 
  : (import.meta.env.PROD ? "" : "https://mplads-ai-optimized.onrender.com")

async function request(endpoint, options = {}) {
  const url = `${API_URL}${endpoint}`
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  })

  if (!response.ok) {
    let errorDetail = `API request failed: ${response.status}`
    try {
      const errJson = await response.json()
      if (errJson && errJson.detail) {
        errorDetail = typeof errJson.detail === "string" 
          ? errJson.detail 
          : JSON.stringify(errJson.detail)
      }
    } catch { /* ignore JSON parse errors */ }
    throw new Error(errorDetail)
  }

  return response.json()
}

function buildQuery(params = {}) {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([key, val]) => {
    if (val !== undefined && val !== null && val !== "" && val !== "all") {
      q.append(key, val)
    }
  })
  const qs = q.toString()
  return qs ? `?${qs}` : ""
}

export async function healthCheck() {
  return request("/health")
}

export async function getStates() {
  return request("/filters/states")
}

export async function getConstituencies(state) {
  if (!state) return []
  return request(`/filters/constituencies?state=${encodeURIComponent(state)}`)
}

export async function getFYs() {
  return request("/filters/fys")
}

// Keep backward-compatible alias
export const getDistricts = getConstituencies

export async function getCategories() {
  return request("/filters/categories")
}

export async function getDashboardOverview(params = {}) {
  return request(`/dashboard/overview${buildQuery(params)}`)
}

export async function getDashboardStates(params = {}) {
  return request(`/dashboard/states${buildQuery(params)}`)
}

export async function getDashboardMPs(params = {}) {
  return request(`/dashboard/mps${buildQuery(params)}`)
}

export async function getDashboardConstituencies(params = {}) {
  return request(`/dashboard/constituencies${buildQuery(params)}`)
}

export async function getDashboardFinancials() {
  return request("/dashboard/financials")
}

export async function getDashboardProjectTypes() {
  return request("/dashboard/project-types")
}

export async function getAnomaliesSummary(params = {}) {
  return request(`/dashboard/anomalies-summary${buildQuery(params)}`)
}

export async function refreshAnomaliesSummary() {
  return request("/dashboard/anomalies-summary/refresh", { method: "POST" })
}

export async function getProjects(params = {}) {
  return request(`/projects${buildQuery(params)}`)
}

export async function searchProjects(params = {}) {
  return request(`/search/projects${buildQuery(params)}`)
}

export async function getProjectDetail(projectId) {
  return request(`/projects/${projectId}`)
}

export async function getAnomalies(params = {}) {
  return request(`/anomalies${buildQuery(params)}`)
}

export async function getProjectRisk(projectId) {
  return request(`/ai/risk/${projectId}`)
}

export async function getRiskyProjects(limit = 10) {
  return request(`/ai/risky-projects?limit=${limit}`)
}

export async function getAIInsights() {
  return request("/ai/insights")
}

export async function getAINarrativeInsights() {
  return request("/ai/narrative-insights")
}

export async function getStateInsights(state) {
  if (!state) return null
  return request(`/ai/state-insights/${encodeURIComponent(state)}`)
}

export async function getMPSummary(params = {}) {
  return request(`/mp-summary${buildQuery(params)}`)
}

export async function getRecommendedWorks(params = {}) {
  return request(`/recommended-works${buildQuery(params)}`)
}

export async function getExpenditures(params = {}) {
  return request(`/expenditures${buildQuery(params)}`)
}

export async function getCompletedWorks(params = {}) {
  return request(`/completed-works${buildQuery(params)}`)
}

export async function getStateIntelligence(params = {}) {
  return request(`/dashboard/state-intelligence${buildQuery(params)}`)
}

export async function getAuditPriority(params = {}) {
  return request(`/audit-priority${buildQuery(params)}`)
}

export async function getSimilarProjects(projectId, limit = 5) {
  return request(`/projects/${projectId}/similar?limit=${limit}`)
}

export async function getAnomalyAnalytics(params = {}) {
  return request(`/anomalies/analytics${buildQuery(params)}`)
}

export async function getScatterData(params = {}) {
  return request(`/anomalies/scatter-data${buildQuery(params)}`)
}

export async function getDataQualityRecords(params = {}) {
  return request(`/data-quality/records${buildQuery(params)}`)
}

export async function getOverview() {
  return getDashboardOverview()
}
