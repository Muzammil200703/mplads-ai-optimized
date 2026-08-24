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
}) {
  const navigation = [
    "Overview",
    "Projects",
    "Risk Center",
    "Audit Priority",
    "State Intelligence",
    "Reports",
    "Data Quality",
  ]

  return (
    <header
      className="fixed left-0 right-0 top-0 z-40 h-[64px] lg:h-[78px] border-b border-[#c5c6ce] bg-[#f9f9ff] text-[#151c27] dark:border-[#374151] dark:bg-[#111827] dark:text-[#f3f4f6] transition-colors duration-300"
    >

      <div
        className={`
flex h-full items-center gap-2 sm:gap-5 px-3 sm:px-5 transition-all duration-300 ${
          isMobile ? "pl-3" : collapsed ? "pl-16" : "pl-60"
        }
        `}
      >

        {/* MENU BUTTON */}
        <button
          onClick={onMenuClick}
          className="
            flex h-9 w-9 shrink-0 items-center
            justify-center rounded
            text-[#44474d]
            transition
            hover:bg-[#e2e8f8]
            dark:text-[#d1d5db]
            dark:hover:bg-[#1f2937]
          "
          aria-label="Toggle sidebar"
        >
          <span className="text-2xl leading-none">
            ☰
          </span>
        </button>

        {/* NAVIGATION */}
        <nav className="hidden items-center gap-5 xl:gap-7 xl:flex">

          {navigation.map((item) => {

            const active = currentPage === item

            return (
              <button
                key={item}
                onClick={() => onNavigate(item)}
                className={`
                  relative whitespace-nowrap
                  pb-2 text-sm font-medium
                  transition-colors duration-200

                  ${
                    active
                      ? `
                        font-bold
                        text-[#031632]
                        dark:text-white
                      `
                      : `
                        text-[#44474d]
                        hover:text-[#031632]
                        dark:text-[#d1d5db]
                        dark:hover:text-white
                      `
                  }
                `}
              >
                {item}

                {active && (
                  <span
                    className="
                      absolute bottom-0 left-0
                      h-0.5 w-full
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
            placeholder={isMobile ? "Search..." : "Search by ID, name, state, or district..."}
            value={searchQuery}
            onChange={(e) => onSearchChange && onSearchChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && searchQuery && searchQuery.trim()) {
                e.preventDefault()
                onSearchSubmit && onSearchSubmit(searchQuery.trim())
              }
            }}
            className="
              h-10 w-full rounded
              border border-[#c5c6ce]
              bg-white
              pl-9 pr-3
              text-sm text-[#151c27]
              outline-none
              placeholder:text-[#75777e]
              focus:border-[#031632]
              focus:ring-1 focus:ring-[#031632]

              dark:border-[#374151]
              dark:bg-[#1f2937]
              dark:text-[#f3f4f6]
              dark:placeholder:text-[#9ca3af]
              dark:focus:border-[#8293b5]
              dark:focus:ring-[#8293b5]
            "
          />

        </div>

        {/* FISCAL YEAR */}
        <div
          className="
            hidden items-center gap-2
            whitespace-nowrap
            xl:flex
          "
        >

          <span
            className="
              text-xs font-medium
              text-[#44474d]
              dark:text-[#9ca3af]
            "
          >
            FY
          </span>

          <button
            className="
              flex items-center gap-1
              text-sm font-bold
              text-[#031632]
              dark:text-white
            "
          >
            2023-24
            <span className="text-xs">⌄</span>
          </button>

        </div>

        {/* SEARCH BUTTON */}
        <button
          onClick={() => {
            if (searchQuery && searchQuery.trim()) {
              onSearchSubmit && onSearchSubmit(searchQuery.trim())
            }
          }}
          className="flex h-10 shrink-0 items-center gap-2 whitespace-nowrap rounded bg-[#031632] px-3 sm:px-4 text-xs font-bold text-white transition hover:bg-[#1a2b48] dark:bg-blue-600 dark:hover:bg-blue-700"
          title="Search"
        >
          🔍
          <span className="hidden xl:inline">Search</span>
        </button>

        {/* DARK MODE */}
        <button
          onClick={onThemeToggle}
          className="
            flex h-9 w-9 shrink-0
            items-center justify-center
            rounded-full
            text-lg
            transition

            hover:bg-[#e2e8f8]

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

        {/* NOTIFICATION */}
        <button
          className="hidden sm:flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-lg transition hover:bg-[#e2e8f8] dark:hover:bg-[#1f2937]"
          aria-label="Notifications"
        >
          🔔
        </button>

        {/* PROFILE */}
        <button
          className="
            flex h-9 w-9 shrink-0
            items-center justify-center
            rounded-full
            text-lg
            transition

            hover:bg-[#e2e8f8]

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
