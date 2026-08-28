const API_URL = import.meta.env.VITE_API_URL !== undefined 
  ? import.meta.env.VITE_API_URL 
  : (import.meta.env.PROD ? "" : "https://mplads-ai-optimized.onrender.com")

// ═══════════════ CLIENT-SIDE API CACHE ═══════════════
// TTL-based cache to avoid refetching filter/static data on every page mount
const _apiCache = new Map()
function cacheGet(key, ttlMs = 60000) {
  const entry = _apiCache.get(key)
  if (entry && (Date.now() - entry.ts) < ttlMs) return entry.data
  _apiCache.delete(key)
  return undefined
}
function cacheSet(key, data) {
  _apiCache.set(key, { data, ts: Date.now() })
}
function cacheInvalidate(prefix) {
  for (const key of _apiCache.keys()) {
    if (key.startsWith(prefix)) _apiCache.delete(key)
  }
}

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

  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
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
  const cached = cacheGet("states", 300000) // 5 min cache
  if (cached !== undefined) return cached
  const data = await request("/filters/states")
  if (data) cacheSet("states", data)
  return data
}

export async function getConstituencies(state) {
  if (!state) return []
  const cacheKey = `cons_${state}`
  const cached = cacheGet(cacheKey, 300000) // 5 min cache
  if (cached !== undefined) return cached
  try {
    const data = await request(`/filters/constituencies?state=${encodeURIComponent(state)}`)
    if (data) cacheSet(cacheKey, data)
    return data
  } catch {
    try {
      const data = await request(`/filters/districts?state=${encodeURIComponent(state)}`)
      if (data) cacheSet(cacheKey, data)
      return data
    } catch {
      try {
        const data = await request(`/search/projects?state=${encodeURIComponent(state)}&skip=0&limit=500`)
        const set = new Set()
        if (data && Array.isArray(data.results)) {
          data.results.forEach((p) => { if (p.constituency) set.add(p.constituency) })
        }
        const result = Array.from(set).sort()
        cacheSet(cacheKey, result)
        return result
      } catch {
        return []
      }
    }
  }
}

export async function getFYs() {
  const cached = cacheGet("fys", 300000) // 5 min cache
  if (cached !== undefined) return cached
  try {
    const data = await request("/filters/fys")
    if (data) cacheSet("fys", data)
    return data
  } catch {
    const fallback = [
      { fy: "2023-24", count: 8562 },
      { fy: "2024-25", count: 19203 },
      { fy: "2025-26", count: 50274 },
      { fy: "2026-27", count: 5192 },
    ]
    cacheSet("fys", fallback)
    return fallback
  }
}

// Keep backward-compatible alias
export const getDistricts = getConstituencies

// Allow pages to invalidate cache when data changes
export function invalidateAPICache(prefix) {
  cacheInvalidate(prefix || "")
}

export async function getCategories() {
  const cached = cacheGet("categories", 300000)
  if (cached !== undefined) return cached
  const data = await request("/filters/categories")
  if (data) cacheSet("categories", data)
  return data
}

export async function getDashboardOverview(params = {}) {
  return request(`/dashboard/overview${buildQuery(params)}`)
}

export async function getDashboardStates(params = {}) {
  // Cache state dashboard data for 2 minutes (expensive aggregation)
  const cacheKey = `dash_states_${buildQuery(params)}`
  const cached = cacheGet(cacheKey, 120000)
  if (cached !== undefined) return cached
  const data = await request(`/dashboard/states${buildQuery(params)}`)
  if (data) cacheSet(cacheKey, data)
  return data
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
  const cacheKey = `anom_summary_${buildQuery(params)}`
  const cached = cacheGet(cacheKey, 120000) // 2 min cache
  if (cached !== undefined) return cached
  const data = await request(`/dashboard/anomalies-summary${buildQuery(params)}`)
  if (data) cacheSet(cacheKey, data)
  return data
}

export async function refreshAnomaliesSummary() {
  return request("/dashboard/anomalies-summary/refresh", { method: "POST" })
}

export async function getProjects(params = {}) {
  return request(`/projects${buildQuery(params)}`)
}

export async function searchProjects(params = {}) {
  const { signal, ...queryParams } = params
  return request(`/search/projects${buildQuery(queryParams)}`, signal ? { signal } : {})
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

export async function getAINarrativeInsights(params = {}) {
  return request(`/ai/narrative-insights${buildQuery(params)}`)
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
  const cacheKey = `state_intel_${buildQuery(params)}`
  const cached = cacheGet(cacheKey, 120000) // 2 min cache
  if (cached !== undefined) return cached
  const data = await request(`/dashboard/state-intelligence${buildQuery(params)}`)
  if (data) cacheSet(cacheKey, data)
  return data
}

export async function getAuditPriority(params = {}) {
  return request(`/audit-priority${buildQuery(params)}`)
}

export async function getAuditPrioritySummary(params = {}) {
  return request(`/audit-priority/summary${buildQuery(params)}`)
}

export async function getSimilarProjects(projectId, limit = 5) {
  return request(`/projects/${projectId}/similar?limit=${limit}`)
}

export async function getAnomalyAnalytics(params = {}) {
  const cacheKey = `anomaly_analytics_${buildQuery(params)}`
  const cached = cacheGet(cacheKey, 120000) // 2 min cache for expensive analytics
  if (cached !== undefined) return cached
  const data = await request(`/anomalies/analytics${buildQuery(params)}`)
  if (data) cacheSet(cacheKey, data)
  return data
}

export async function getScatterData(params = {}) {
  return request(`/anomalies/scatter-data${buildQuery(params)}`)
}

export async function getOverview() {
  return getDashboardOverview()
}

// Feature 1: AI Risk Explanation
export async function getRiskExplanation(projectId) {
  return request(`/ai/risk-explanation/${projectId}`)
}

// Feature 3: Anomaly Explanation
export async function getAnomalyExplanation(projectId) {
  return request(`/ai/anomaly-explanation/${projectId}`)
}

// Feature 4: Benchmarking
export async function getBenchmarking(params = {}) {
  return request(`/ai/benchmarking${buildQuery(params)}`)
}

// Export cache invalidation for use after data mutations
export { cacheInvalidate }
