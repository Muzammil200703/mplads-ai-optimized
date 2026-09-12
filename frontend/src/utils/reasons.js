/**
 * Risk reasons arrive in two shapes:
 *   - risk_scores.reasons      → comma-separated string (persisted result)
 *   - predict_risk().reasons   → array of strings (live calculation)
 *
 * This helper normalizes both so no triggered reason is silently dropped.
 */
export function parseReasons(raw) {
  if (!raw) return []
  if (Array.isArray(raw)) return raw.filter(Boolean)
  const text = String(raw).trim()
  if (!text) return []
  if (text.startsWith("[")) {
    try {
      const parsed = JSON.parse(text)
      if (Array.isArray(parsed)) return parsed.filter(Boolean)
    } catch {
      /* fall through to comma splitting */
    }
  }
  return text.split(",").map((part) => part.trim()).filter(Boolean)
}
