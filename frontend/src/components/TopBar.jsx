import { getFYs } from "../services/api"
import { useEffect, useState, useRef, useCallback } from "react"

// ─── Search History (localStorage) ──────────────────────────────────
const HISTORY_KEY = "mplads_recent_searches"
const MAX_HISTORY = 10

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveHistory(history) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history))
  } catch {
    // ignore
  }
}

function addToHistory(query) {
  const trimmed = query.trim()
  if (!trimmed) return loadHistory()
  const history = loadHistory().filter((h) => h !== trimmed)
  history.unshift(trimmed)
  const sliced = history.slice(0, MAX_HISTORY)
  saveHistory(sliced)
  return sliced
}

function clearHistory() {
  try {
    localStorage.removeItem(HISTORY_KEY)
  } catch {
    // ignore
  }
  return []
}

// ─── TopBar Component ──────────────────────────────────────────────
function TopBar({
  collapsed,
  onMenuClick,
  currentPage,
  onNavigate,
  darkMode,
  onThemeToggle,
  searchQuery,
  onSearchChange,
  onNavigateToResult,
  isMobile,
  selectedFY,
  onFYChange,
}) {
  const [availableFYs, setAvailableFYs] = useState([])
  const [history, setHistory] = useState(loadHistory)
  const [showHistory, setShowHistory] = useState(false)
  const [historyCleared, setHistoryCleared] = useState(false)
  const inputRef = useRef(null)
  const historyRef = useRef(null)

  const handleSearchChange = (e) => {
    onSearchChange(e.target.value)
    // Hide history when user starts typing
    if (e.target.value.length > 0) setShowHistory(false)
  }

  const handleSearchSubmit = useCallback(() => {
    if (searchQuery && searchQuery.trim()) {
      const updated = addToHistory(searchQuery.trim())
      setHistory(updated)
      setShowHistory(false)
      onNavigateToResult("Projects", { keyword: searchQuery.trim() })
    }
  }, [searchQuery, onNavigateToResult])

  const handleHistoryClick = useCallback(
    (term) => {
      onSearchChange(term)
      // Move to top of history
      const updated = addToHistory(term)
      setHistory(updated)
      setShowHistory(false)
      onNavigateToResult("Projects", { keyword: term })
    },
    [onSearchChange, onNavigateToResult]
  )

  const handleClearHistory = useCallback((e) => {
    e.stopPropagation()
    const updated = clearHistory()
    setHistory(updated)
    setHistoryCleared(true)
    // Brief flash then reset so the "cleared" message disappears
    setTimeout(() => setHistoryCleared(false), 1200)
  }, [])

  const handleFocus = useCallback(() => {
    // Show history when focused and input is empty
    const h = loadHistory()
    setHistory(h)
    if ((!searchQuery || !searchQuery.trim()) && h.length > 0) {
      setShowHistory(true)
    }
  }, [searchQuery])

  const handleBlur = useCallback((e) => {
    // Delay hiding so click on history item registers first
    setTimeout(() => {
      if (!historyRef.current?.contains(document.activeElement)) {
        setShowHistory(false)
      }
    }, 150)
  }, [])

  // Close dropdown on outside click
  useEffect(() => {
    if (!showHistory) return
    const handler = (e) => {
      if (
        historyRef.current &&
        !historyRef.current.contains(e.target) &&
        e.target !== inputRef.current
      ) {
        setShowHistory(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [showHistory])

  useEffect(() => {
    getFYs()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0 && data[0] && typeof data[0].fy === "string") {
          setAvailableFYs(data)
        } else {
          setAvailableFYs([
            { fy: "2023-24", count: 8562 },
            { fy: "2024-25", count: 19203 },
            { fy: "2025-26", count: 50274 },
            { fy: "2026-27", count: 5192 },
          ])
        }
      })
      .catch(() => {
        setAvailableFYs([
          { fy: "2023-24", count: 8562 },
          { fy: "2024-25", count: 19203 },
          { fy: "2025-26", count: 50274 },
          { fy: "2026-27", count: 5192 },
        ])
      })
  }, [])

  const navigation = [
    "Overview",
    "Projects",
    "Risk Center",
    "Audit Priority",
    "State Intelligence",
    "Reports",
  ]

  return (
    <header
      className="fixed left-0 right-0 top-0 z-[70] h-[64px] lg:h-[72px] border-b border-[#c5c6ce] bg-[#f9f9ff] text-[#151c27] dark:border-[#374151] dark:bg-[#111827] dark:text-[#f3f4f6] transition-colors duration-300"
    >
      <div
        className={`
flex h-full items-center gap-1.5 px-2 sm:gap-3 sm:px-4 lg:gap-4 lg:px-5 transition-all duration-300 ${
          isMobile ? "pl-2" : collapsed ? "pl-16" : "pl-60"
        }
        `}
      >
        {/* MENU BUTTON */}
        <button
          onClick={onMenuClick}
          className="
            flex h-10 w-10 shrink-0 items-center
            justify-center rounded-lg
            border border-[#c5c6ce]
            bg-[#f0f3ff]
            text-[#031632]
            transition-all duration-200
            hover:bg-[#e2e8f8]
            hover:border-[#031632]
            hover:shadow-sm
            active:scale-95
            dark:border-[#374151]
            dark:bg-[#1f2937]
            dark:text-[#f3f4f6]
            dark:hover:bg-[#374151]
            dark:hover:border-[#8293b5]
          "
          aria-label="Toggle sidebar"
          title="Toggle sidebar (Ctrl+B)"
        >
          <span className="text-xl leading-none font-bold">☰</span>
        </button>

        {/* NAVIGATION */}
        <nav className="hidden items-center gap-1 lg:gap-1.5 lg:flex">
          {navigation.map((item) => {
            const active = currentPage === item
            return (
              <button
                key={item}
                onClick={() => onNavigate(item)}
                className={`
                  relative whitespace-nowrap
                  rounded-md px-2.5 py-1.5
                  text-[13px] font-medium
                  transition-all duration-150
                  ${
                    active
                      ? `bg-[#f0f3ff] font-semibold text-[#031632] dark:bg-[#1f2937] dark:text-white`
                      : `text-[#44474d] hover:bg-[#eef1f8] hover:text-[#031632] dark:text-[#d1d5db] dark:hover:bg-[#1f2937] dark:hover:text-white`
                  }
                `}
              >
                {item}
                {active && (
                  <span
                    className="
                      absolute bottom-0 left-2 right-2
                      h-[2px] rounded-full
                      bg-[#bb0011]
                    "
                  />
                )}
              </button>
            )
          })}
        </nav>

        {/* SEARCH + HISTORY DROPDOWN */}
        <div className="relative min-w-0 flex-1" ref={historyRef}>
          <span
            className="
              pointer-events-none absolute left-3
              top-1/2 -translate-y-1/2
              text-sm text-[#75777e]
              dark:text-[#9ca3af]
            "
          >
            🔍
          </span>

          <input
            ref={inputRef}
            type="text"
            placeholder={isMobile ? "Search..." : "Search projects, states, constituency, MP..."}
            value={searchQuery}
            onChange={handleSearchChange}
            onFocus={handleFocus}
            onBlur={handleBlur}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault()
                handleSearchSubmit()
              }
              if (e.key === "Escape") {
                setShowHistory(false)
                inputRef.current?.blur()
              }
            }}
            className="
              h-10 w-full rounded-lg
              border border-[#c5c6ce]
              bg-white
              pl-9 pr-3
              text-sm text-[#151c27]
              outline-none
              placeholder:text-[#9ca3af]
              focus:border-[#031632] focus:ring-1 focus:ring-[#031632]
              dark:border-[#374151] dark:bg-[#1f2937] dark:text-[#f3f4f6]
              dark:placeholder:text-[#6b7280]
              dark:focus:border-[#8293b5] dark:focus:ring-[#8293b5]
            "
          />

          {/* ── Recent Searches Dropdown ── */}
          {showHistory && (
            <div
              className="
                absolute left-0 right-0 top-full z-[80] mt-1
                overflow-hidden rounded-xl
                border border-[#e2e5ec]
                bg-white
                shadow-lg
                dark:border-[#374151] dark:bg-[#1f2937]
              "
            >
              {historyCleared ? (
                <div className="px-4 py-3 text-xs text-[#9ca3af] dark:text-[#6b7280]">
                  History cleared
                </div>
              ) : history.length === 0 ? (
                <div className="px-4 py-3 text-xs text-[#9ca3af] dark:text-[#6b7280]">
                  No recent searches
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between border-b border-[#f0f1f3] px-4 py-2 dark:border-[#374151]">
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-[#9ca3af] dark:text-[#6b7280]">
                      Recent Searches
                    </span>
                    <button
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={handleClearHistory}
                      className="
                        text-[11px] font-medium text-[#bb0011]
                        transition-colors hover:text-[#930010]
                        dark:text-[#f87171] dark:hover:text-[#fca5a5]
                      "
                    >
                      Clear History
                    </button>
                  </div>
                  <ul className="max-h-[280px] overflow-y-auto py-1">
                    {history.map((term, i) => (
                      <li key={`${term}-${i}`}>
                        <button
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={() => handleHistoryClick(term)}
                          className="
                            flex w-full items-center gap-3
                            px-4 py-2.5
                            text-left text-sm text-[#374151]
                            transition-colors
                            hover:bg-[#f5f7fa]
                            dark:text-[#d1d5db]
                            dark:hover:bg-[#374151]
                          "
                        >
                          <span className="shrink-0 text-[#9ca3af] dark:text-[#6b7280]">
                            🕒
                          </span>
                          <span className="truncate">{term}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </div>

        {/* FISCAL YEAR */}
        <div
          className="
            hidden items-center gap-1.5
            whitespace-nowrap
            lg:flex
          "
        >
          <span
            className="
              text-[11px] font-semibold uppercase tracking-wide
              text-[#75777e] dark:text-[#6b7280]
            "
          >
            FY
          </span>
          <select
            value={selectedFY || ""}
            onChange={(e) => onFYChange && onFYChange(e.target.value)}
            className="
              h-10 rounded-lg
              border border-[#c5c6ce] bg-white
              px-3 text-sm font-medium text-[#031632]
              outline-none
              focus:border-[#031632] focus:ring-1 focus:ring-[#031632]
              dark:border-[#374151] dark:bg-[#1f2937] dark:text-[#f3f4f6]
              dark:focus:border-[#8293b5] dark:focus:ring-[#8293b5]
            "
          >
            <option value="">All FY</option>
            {availableFYs.map((item) => (
              <option key={item.fy} value={item.fy}>
                {item.fy} ({item.count.toLocaleString("en-IN")})
              </option>
            ))}
          </select>
        </div>

        {/* DARK MODE */}
        <button
          onClick={onThemeToggle}
          className="
            flex h-10 w-10 shrink-0
            items-center justify-center
            rounded-lg text-lg
            transition-all duration-150
            hover:bg-[#eef1f8] dark:hover:bg-[#1f2937]
          "
          aria-label="Toggle dark mode"
          title={darkMode ? "Switch to light mode" : "Switch to dark mode"}
        >
          {darkMode ? "☀️" : "🌙"}
        </button>

        {/* PROFILE */}
        <button
          className="
            flex h-10 w-10 shrink-0
            items-center justify-center
            rounded-lg text-lg
            transition-all duration-150
            hover:bg-[#eef1f8] dark:hover:bg-[#1f2937]
          "
          aria-label="Profile"
        >
          👤
        </button>
      </div>
    </header>
  )
}

export default TopBar
