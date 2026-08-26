import { getFYs } from "../services/api"
import { useEffect, useState } from "react"

function TopBar({
  collapsed,
  onMenuClick,
  currentPage,
  onNavigate,
  darkMode,
  onThemeToggle,
  searchQuery,
  onSearchChange,
  onSearchSubmit,
  isMobile,
  selectedFY,
  onFYChange,
}) {
  const [availableFYs, setAvailableFYs] = useState([])

  useEffect(() => {
    getFYs().then((data) => {
      // Ensure data is an array of objects with fy and count properties
      if (Array.isArray(data) && data.length > 0 && data[0] && typeof data[0].fy === "string") {
        setAvailableFYs(data)
      } else {
        // Fallback if response format is unexpected
        setAvailableFYs([
          { fy: "2023-24", count: 8562 },
          { fy: "2024-25", count: 19203 },
          { fy: "2025-26", count: 50274 },
          { fy: "2026-27", count: 5192 },
        ])
      }
    }).catch(() => {
      // Fallback: show known FYs from the dataset when backend is offline
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
      className="fixed left-0 right-0 top-0 z-[70] h-[64px] lg:h-[72px] border-b border-[#c5c6ce] bg-[#f9f9ff] text-[#151c27] dark:border-[#374151] dark:bg-[#111827] dark:text-[#f3f4f6] transition-colors duration-300 overflow-hidden"
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
          <span className="text-xl leading-none font-bold">
            ☰
          </span>
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
                      ? `
                        bg-[#f0f3ff]
                        font-semibold
                        text-[#031632]
                        dark:bg-[#1f2937]
                        dark:text-white
                      `
                      : `
                        text-[#44474d]
                        hover:bg-[#eef1f8]
                        hover:text-[#031632]
                        dark:text-[#d1d5db]
                        dark:hover:bg-[#1f2937]
                        dark:hover:text-white
                      `
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

        {/* SEARCH */}
        <div className="relative min-w-0 flex-1">

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
            type="text"
            placeholder={isMobile ? "Search..." : "Search projects, states, MPs..."}
            value={searchQuery}
            onChange={(e) => onSearchChange && onSearchChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && searchQuery && searchQuery.trim()) {
                e.preventDefault()
                onSearchSubmit && onSearchSubmit(searchQuery.trim())
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
              focus:border-[#031632]
              focus:ring-1 focus:ring-[#031632]

              dark:border-[#374151]
              dark:bg-[#1f2937]
              dark:text-[#f3f4f6]
              dark:placeholder:text-[#6b7280]
              dark:focus:border-[#8293b5]
              dark:focus:ring-[#8293b5]
            "
          />

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
              text-[#75777e]
              dark:text-[#6b7280]
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
            rounded-lg
            text-lg
            transition-all duration-150
            hover:bg-[#eef1f8]
            dark:hover:bg-[#1f2937]
          "
          aria-label="Toggle dark mode"
          title={
            darkMode
              ? "Switch to light mode"
              : "Switch to dark mode"
          }
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
            hover:bg-[#eef1f8]
            dark:hover:bg-[#1f2937]
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
