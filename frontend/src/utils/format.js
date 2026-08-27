/**
 * Format a monetary value as Indian Rupees with appropriate scale (Cr/L)
 */
export function formatMoney(value) {
  const number = Number(value || 0)
  if (number >= 10000000) return `₹${(number / 10000000).toFixed(2)} Cr`
  if (number >= 100000) return `₹${(number / 100000).toFixed(2)} L`
  return `₹${number.toLocaleString("en-IN")}`
}

/**
 * Format a monetary value as Crores only
 */
export function formatCrore(amount) {
  const crore = Number(amount || 0) / 10000000
  return crore.toLocaleString("en-IN", { maximumFractionDigits: 2 })
}

/**
 * Format a number with Indian locale separators
 */
export function formatNumber(value) {
  return Number(value || 0).toLocaleString("en-IN")
}
