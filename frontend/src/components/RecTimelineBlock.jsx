import { formatDateHuman } from "../utils/format"

/* ── Recommendation & Timeline block ─────────────────────────────────
   Shared by Project Details and Risk Center detail — single rendering
   of the backend's rec facts (project_rec_info source of truth), so the
   same project always shows identical values everywhere.

   Semantics:
   • recommendation_date — actual MPLADS recommendation date from the
     recommended-works dataset; "unavailable" when the source record
     has none (never substituted with another date).
   • recommended_by      — MP name from that recommendation record;
     never inferred from agency/vendor/constituency fields.
   • approx_start_date   — earliest MP-verified recorded expenditure for
     THIS project only, always labelled "Approx." because a payment date
     is a proxy, not a confirmed physical start.
   • no expenditure      — "Project not yet started" with an explicit
     note that this reflects the absence of recorded expenditure.       */

export default function RecTimelineBlock({ rec, compact }) {
  const recDate = formatDateHuman(rec?.recommendation_date)
  const mp = (rec?.recommended_by || "").trim()
  const startDate = rec?.has_expenditure ? formatDateHuman(rec.approx_start_date) : null

  return (
    <div className={compact ? "space-y-1" : "space-y-1.5"}>
      {/* Recommended date */}
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[0.6875rem] text-gray-500 dark:text-gray-400">Recommended</span>
        {recDate ? (
          <span className="font-mono text-xs font-semibold">{recDate}</span>
        ) : (
          <span className="text-xs italic text-gray-400">Recommendation date unavailable</span>
        )}
      </div>

      {/* Recommended by (MP) */}
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[0.6875rem] text-gray-500 dark:text-gray-400">Recommended by</span>
        {mp ? (
          <span className="max-w-[220px] truncate text-right text-xs font-semibold" title={mp}>{mp}</span>
        ) : (
          <span className="text-xs italic text-gray-400">Recommending MP unavailable</span>
        )}
      </div>

      {/* Approximate start date */}
      <div className="flex items-baseline justify-between gap-3">
        <span
          className="cursor-help border-b border-dotted border-gray-300 text-[0.6875rem] text-gray-500 dark:border-gray-600 dark:text-gray-400"
          title="Approximate start date based on the earliest recorded expenditure. This may not represent the actual physical start of work."
        >
          Approx. project start
        </span>
        {startDate ? (
          <span className="font-mono text-xs font-semibold">{startDate}</span>
        ) : (
          <span className="text-xs font-semibold text-gray-500 dark:text-gray-400">
            Project not yet started
            <span
              className="ml-1 cursor-help border-b border-dotted border-gray-300 text-[0.625rem] font-normal italic text-gray-400 dark:border-gray-600"
              title="Based on the absence of recorded expenditure for this project. No recorded expenditure does not prove that physical work has not begun."
            >
              (no expenditure recorded)
            </span>
          </span>
        )}
      </div>
    </div>
  )
}
