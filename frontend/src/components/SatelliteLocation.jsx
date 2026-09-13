import { useEffect, useMemo, useState } from "react"
import { getProjectGeolocation } from "../services/api"

/* ═══════════════════════════════════════════════════════════════════════
   Satellite Location Intelligence — BETA
   ─────────────────────────────────────────────────────────────────────
   Resolves an ESTIMATED project location from fields that already exist
   (work description, district, constituency, state) and, when confident,
   offers a satellite/map view as supporting visual evidence.

   Evidence categories are never mixed:
     SOURCE DATA      — actual MPLADS values shown as-is
     GEOCODED         — coordinates from OpenStreetMap Nominatim (estimate)
     SATELLITE        — external imagery, visual reference only
     SYSTEM INFERENCE — confidence labels / usefulness guidance

   No coordinates are ever invented: unresolved locations show a fallback,
   not a pin. Geocoding happens only on demand and is cached by the backend.
   ═══════════════════════════════════════════════════════════════════════ */

const BETA_TOOLTIP =
  "Beta feature using project location information and external map/satellite imagery. Location accuracy varies by available project details. Satellite imagery is supporting evidence only."

const CONFIDENCE_STYLES = {
  High: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300",
  Medium: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  Low: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300",
  Unresolved: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
}

const CONFIDENCE_ICONS = { High: "📍", Medium: "📍", Low: "⚠️", Unresolved: "⚠️" }

/* ── Slippy map (dependency-free): Esri World Imagery + OSM tiles ────── */
function latLonToTile(lat, lon, z) {
  const n = 2 ** z
  const x = ((lon + 180) / 360) * n
  const latRad = (lat * Math.PI) / 180
  const y = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n
  return { x, y }
}
function tileToLatLon(x, y, z) {
  const n = 2 ** z
  const lon = (x / n) * 360 - 180
  const lat = (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / n))) * 180) / Math.PI
  return { lat, lon }
}

const TILE_LAYERS = {
  satellite: {
    label: "Satellite",
    url: (z, x, y) => `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`,
    attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
    maxZoom: 19,
  },
  map: {
    label: "Map",
    url: (z, x, y) => `https://tile.openstreetmap.org/${z}/${x}/${y}.png`,
    attribution: "© OpenStreetMap contributors",
    maxZoom: 19,
  },
}

function SatelliteMap({ geo, onClose }) {
  const { match, extraction, confidence, confidence_reason: reason } = geo
  const [zoom, setZoom] = useState(16)
  const [layer, setLayer] = useState("satellite")
  const [center, setCenter] = useState(() => ({ lat: match.lat, lon: match.lon }))
  const [size, setSize] = useState({ w: window.innerWidth - 40, h: window.innerHeight - 140 })
  const [dragStart, setDragStart] = useState(null)

  useEffect(() => {
    const onResize = () => setSize({ w: window.innerWidth - 40, h: window.innerHeight - 140 })
    window.addEventListener("resize", onResize)
    const onKey = (e) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", onKey)
    return () => { window.removeEventListener("resize", onResize); window.removeEventListener("keydown", onKey) }
  }, [onClose])

  const tiles = useMemo(() => {
    const tl = TILE_LAYERS[layer]
    const { w, h } = size
    const c = latLonToTile(center.lat, center.lon, zoom)
    const tileCountX = Math.ceil(w / 256) + 1
    const tileCountY = Math.ceil(h / 256) + 1
    const startX = Math.floor(c.x - tileCountX / 2)
    const startY = Math.floor(c.y - tileCountY / 2)
    const list = []
    for (let ty = startY; ty <= startY + tileCountY; ty++) {
      for (let tx = startX; tx <= startX + tileCountX; tx++) {
        if (ty < 0 || ty >= 2 ** zoom) continue
        const wrappedX = ((tx % (2 ** zoom)) + 2 ** zoom) % (2 ** zoom)
        const px = (tx - c.x) * 256 + w / 2
        const py = (ty - c.y) * 256 + h / 2
        list.push({ key: `${layer}-${zoom}-${tx}-${ty}`, url: tl.url(zoom, wrappedX, ty), px, py })
      }
    }
    return list
  }, [center, zoom, layer, size])

  const markerPx = useMemo(() => {
    const c = latLonToTile(center.lat, center.lon, zoom)
    const m = latLonToTile(match.lat, match.lon, zoom)
    return { left: (m.x - c.x) * 256 + size.w / 2, top: (m.y - c.y) * 256 + size.h / 2 }
  }, [center, zoom, size, match])

  const onPointerDown = (e) => setDragStart({ x: e.clientX, y: e.clientY, lat: center.lat, lon: center.lon })
  const onPointerMove = (e) => {
    if (!dragStart) return
    const dx = e.clientX - dragStart.x, dy = e.clientY - dragStart.y
    const c = latLonToTile(dragStart.lat, dragStart.lon, zoom)
    const next = tileToLatLon(c.x - dx / 256, c.y - dy / 256, zoom)
    setCenter(next)
  }
  const onPointerUp = () => setDragStart(null)

  const zoomBy = (d) => setZoom((z) => Math.min(19, Math.max(3, z + d)))

  const confStyle = CONFIDENCE_STYLES[confidence] || CONFIDENCE_STYLES.Unresolved

  return (
    <div className="fixed inset-0 z-[90] flex flex-col bg-black/80 backdrop-blur-2xs" onClick={onClose}>
      <div
        className="flex h-full w-full flex-col overflow-hidden rounded-none sm:m-auto sm:max-h-[92vh] sm:max-w-5xl sm:rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-[#111827]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header — never scrolls */}
        <div className="flex flex-none items-start justify-between gap-3 border-b border-gray-200 p-4 dark:border-gray-700">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-[#031632] dark:text-white">🛰️ Satellite View</h3>
              <span className="rounded-full border border-amber-200 bg-amber-100 px-[5px] py-px text-[9px] font-bold leading-none text-amber-800 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-300" title={BETA_TOOLTIP}>BETA</span>
            </div>
            <p className="mt-0.5 truncate text-xs text-gray-500 dark:text-gray-400" title={extraction?.components?.place || ""}>
              #{geo.project_id} — {extraction?.components?.place || extraction?.components?.constituency || "Estimated location"}
            </p>
          </div>
          <div className="flex flex-none items-center gap-2">
            <span className={`rounded-full px-2 py-0.5 text-[0.625rem] font-bold ${confStyle}`}>{CONFIDENCE_ICONS[confidence] || "📍"} Confidence: {confidence}</span>
            <button onClick={onClose} className="rounded-lg px-2 py-1 text-xl text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700" aria-label="Back to project">✕</button>
          </div>
        </div>

        {/* Map viewport */}
        <div
          className={`relative flex-1 overflow-hidden bg-gray-200 dark:bg-gray-800 ${dragStart ? "cursor-grabbing" : "cursor-grab"}`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerUp}
          style={{ touchAction: "none" }}
        >
          {tiles.map((t) => (
            <img
              key={t.key}
              src={t.url}
              alt=""
              loading="eager"
              draggable={false}
              className="pointer-events-none absolute h-[256px] w-[256px] select-none"
              style={{ left: t.px, top: t.py }}
            />
          ))}
          {/* Project marker */}
          <div className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full" style={{ left: markerPx.left, top: markerPx.top }}>
            <div className="flex flex-col items-center">
              <div className="rounded-full border-2 border-white bg-[#bb0011] px-2 py-0.5 text-[0.625rem] font-bold text-white shadow-md">#{geo.project_id}</div>
              <div className="h-3 w-px bg-[#bb0011]" />
              <div className="h-2.5 w-2.5 rounded-full border-2 border-white bg-[#bb0011] shadow" />
            </div>
          </div>
          {/* Zoom controls */}
          <div className="absolute right-3 top-3 z-20 flex flex-col overflow-hidden rounded-lg border border-gray-300 bg-white shadow dark:border-gray-600 dark:bg-[#1f2937]">
            <button onClick={() => zoomBy(1)} className="h-8 w-8 text-lg font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-700" aria-label="Zoom in">+</button>
            <button onClick={() => zoomBy(-1)} className="h-8 w-8 border-t border-gray-200 text-lg font-bold text-gray-700 hover:bg-gray-100 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700" aria-label="Zoom out">−</button>
          </div>
          {/* Layer toggle */}
          <div className="absolute left-3 top-3 z-20 flex overflow-hidden rounded-lg border border-gray-300 bg-white text-xs font-semibold shadow dark:border-gray-600 dark:bg-[#1f2937]">
            {Object.entries(TILE_LAYERS).map(([key, tl]) => (
              <button
                key={key}
                onClick={() => setLayer(key)}
                className={`px-3 py-1.5 ${layer === key ? "bg-[#031632] text-white dark:bg-blue-600" : "text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-700"}`}
              >
                {tl.label}
              </button>
            ))}
          </div>
          {/* Attribution (required by tile providers) */}
          <div className="absolute bottom-0 left-0 z-20 max-w-full truncate bg-black/50 px-2 py-0.5 text-[0.5625rem] text-white">
            {TILE_LAYERS[layer].attribution} · Estimated location — not a surveyed site boundary
          </div>
        </div>

        {/* Footer — context + disclaimers, never scrolls away */}
        <div className="flex-none border-t border-gray-200 p-3 dark:border-gray-700">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.6875rem] text-gray-500 dark:text-gray-400">
            <span className="font-semibold text-gray-700 dark:text-gray-300">{match.display_name}</span>
            <span className="font-mono">{Number(match.lat).toFixed(5)}, {Number(match.lon).toFixed(5)}</span>
            {reason && <span className="italic">{reason}</span>}
          </div>
          <p className="mt-1.5 text-[0.625rem] leading-relaxed text-gray-500 dark:text-gray-400">
            Satellite imagery is provided as visual reference only. It does not independently verify project completion.
            Field verification remains necessary for confirmation.
          </p>
        </div>
      </div>
    </div>
  )
}

/* ── Compact panel embedded in project detail / risk views ───────────── */
export default function SatelliteLocationPanel({ project }) {
  const [geo, setGeo] = useState(null)
  const [state, setState] = useState("idle") // idle | loading | ready | error
  const [showMap, setShowMap] = useState(false)

  const resolve = () => {
    if (!project?.id) return
    setState("loading")
    getProjectGeolocation(project.id)
      .then((data) => {
        setGeo(data)
        setState("ready")
      })
      .catch((err) => {
        console.error("[SatelliteLocation] resolve failed:", err)
        setState("error")
      })
  }

  // Resolve only when the panel becomes visible — never on page load.
  useEffect(() => {
    if (state === "idle" && project?.id) resolve()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id])

  const usefulness = geo?.usefulness
  const limited = usefulness?.usefulness === "limited"
  const resolved = geo?.status === "resolved" && geo?.match
  const conf = geo?.confidence || "Unresolved"
  const confStyle = CONFIDENCE_STYLES[conf] || CONFIDENCE_STYLES.Unresolved

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-[#111827]">
      {/* Section header + BETA badge */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400">🛰️ Satellite Location Intelligence</h4>
          <span className="rounded-full border border-amber-200 bg-amber-100 px-[5px] py-px text-[9px] font-bold leading-none text-amber-800 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-300" title={BETA_TOOLTIP}>BETA</span>
        </div>
        {state === "ready" && (
          <button onClick={resolve} className="text-[0.625rem] font-semibold text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" title="Re-resolve location">↻ Retry</button>
        )}
      </div>
      <p className="mt-0.5 text-[0.625rem] italic text-gray-400" title={BETA_TOOLTIP}>{BETA_TOOLTIP}</p>

      {/* LOADING */}
      {state === "loading" && (
        <div className="mt-3 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
          <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-solid border-blue-600 border-r-transparent" />
          Resolving project location…
        </div>
      )}

      {/* ERROR */}
      {state === "error" && (
        <div className="mt-3">
          <p className="text-xs font-medium text-red-600 dark:text-red-400">Unable to resolve location.</p>
          <button onClick={resolve} className="mt-2 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-bold text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-[#1f2937] dark:text-gray-200">Retry</button>
        </div>
      )}

      {/* READY */}
      {state === "ready" && geo && (
        <div className="mt-3 space-y-3">
          {/* Estimated location (GEOCODED category) */}
          <div>
            <p className="text-[0.625rem] font-bold uppercase tracking-wider text-gray-400">📍 Estimated Location</p>
            {resolved ? (
              <p className="mt-0.5 text-xs font-medium text-gray-800 dark:text-gray-200" title={geo.match.display_name}>
                {geo.match.display_name}
                <span className="ml-2 font-mono text-[0.625rem] text-gray-400">{Number(geo.match.lat).toFixed(4)}, {Number(geo.match.lon).toFixed(4)}</span>
              </p>
            ) : (
              <p className="mt-0.5 text-xs text-gray-600 dark:text-gray-400">
                {geo.confidence_reason || "Location could not be reliably resolved."}
              </p>
            )}
            {/* SOURCE DATA — the raw fields this estimate came from */}
            <p className="mt-1 text-[0.625rem] text-gray-400">
              From recorded fields: {geo.extraction?.components?.place || "no specific place in work description"}
              {geo.extraction?.components?.district ? `, ${geo.extraction.components.district}` : ""}
              {geo.extraction?.components?.constituency ? `, ${geo.extraction.components.constituency}` : ""}
              {geo.extraction?.components?.state ? `, ${geo.extraction.components.state}` : ""}
            </p>
          </div>

          {/* Confidence */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[0.625rem] font-bold uppercase tracking-wider text-gray-400">🎯 Location Confidence</span>
            <span className={`rounded-full px-2 py-0.5 text-[0.625rem] font-bold ${confStyle}`}>
              {CONFIDENCE_ICONS[conf]} {conf}
            </span>
            {geo.confidence_reason && <span className="text-[0.625rem] italic text-gray-500 dark:text-gray-400">{geo.confidence_reason}</span>}
          </div>

          {/* Usefulness guidance (SYSTEM INFERENCE) */}
          {usefulness && (
            <p className="text-[0.625rem] text-gray-500 dark:text-gray-400">
              <span className="font-semibold">Project-type suitability:</span> {usefulness.note}
            </p>
          )}

          {/* View Satellite — only for genuinely resolved locations */}
          {resolved ? (
            limited ? (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-2.5 dark:border-gray-700 dark:bg-[#1f2937]">
                <p className="text-xs text-gray-600 dark:text-gray-400">Satellite verification has limited applicability for this project type.</p>
                <button onClick={() => setShowMap(true)} className="mt-2 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-bold text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-[#1f2937] dark:text-gray-200">
                  🛰️ View Satellite (reference only)
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowMap(true)}
                className="rounded-lg bg-[#031632] px-4 py-2 text-xs font-bold text-white transition hover:bg-[#0a2547] dark:bg-blue-600 dark:hover:bg-blue-500"
              >
                🛰️ View Satellite
              </button>
            )
          ) : (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-2.5 dark:border-amber-900/60 dark:bg-amber-950/30">
              <p className="text-xs font-semibold text-amber-700 dark:text-amber-300">Satellite view unavailable for this project.</p>
              <p className="mt-0.5 text-[0.625rem] text-amber-600 dark:text-amber-400">Insufficient location information to confidently resolve the project.</p>
            </div>
          )}

          <p className="text-[0.625rem] leading-relaxed text-gray-400 dark:text-gray-500">
            Use satellite imagery as supporting evidence only. Field verification remains necessary for confirmation.
          </p>
        </div>
      )}

      {showMap && resolved && <SatelliteMap geo={geo} onClose={() => setShowMap(false)} />}
    </div>
  )
}

/* ── Compact list chip: "🛰️ Satellite evidence available" ─────────────── */
export function SatelliteEvidenceChip({ onClick }) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick?.() }}
      title="Opens the estimated location on satellite imagery — supporting evidence only (BETA)."
      className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[0.5625rem] font-bold text-blue-700 transition hover:bg-blue-100 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300 dark:hover:bg-blue-900/40"
    >
      🛰️ Satellite evidence available
    </button>
  )
}
