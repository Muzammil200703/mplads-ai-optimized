function Sidebar({
  collapsed,
  currentPage,
  onNavigate,
  isMobile,
  isOpen,
  onClose,
}) {
  const navigation = [
    { name: "Overview", page: "Overview", icon: "▦" },
    { name: "Projects", page: "Projects", icon: "▤" },
    { name: "Risk Center", page: "Risk Center", icon: "⚠" },
    { name: "Reports", page: "Reports", icon: "▣" },
    { name: "State Intelligence", page: "State Intelligence", icon: "map-pin" },
    { name: "Audit Priority", page: "Audit Priority", icon: "🎯" },
    { name: "Compare Projects", page: "Compare Projects", icon: "⚖" },
  ]

  // Mobile drawer
  if (isMobile) {
    return (
      <>
        <aside
          className={`
            fixed left-0 top-0 z-[60] flex h-screen w-64 flex-col
            border-r border-[#c5c6ce]
            bg-[#f9f9ff] text-[#151c27]
            dark:border-[#374151] dark:bg-[#111827] dark:text-[#f3f4f6]
            transition-transform duration-300 ease-in-out
            px-4
            ${isOpen ? "translate-x-0" : "-translate-x-full"}
          `}
        >
          <div className="mb-6 flex min-w-0 items-center gap-3 pt-1">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-[#1a2b48] text-lg leading-none text-white dark:bg-[#243b5a]">
              🏛
            </div>
            <div className="min-w-0 overflow-hidden">
              <h1 className="whitespace-nowrap text-lg font-bold text-[#031632] dark:text-[#f3f4f6]">MPLADS Insight</h1>
              <p className="whitespace-nowrap text-xs text-[#44474d] dark:text-[#9ca3af]">Auditor Portal</p>
            </div>
          </div>
          <nav className="space-y-1">
            {navigation.map((item) => {
              const active = currentPage === item.page
              return (
                <button key={item.name} onClick={() => onNavigate(item.page)}
                  className={`group relative flex w-full items-center gap-3 rounded px-3 py-2.5 transition-all duration-200 justify-start ${active ? "bg-[#f0f3ff] text-[#031632] dark:bg-[#1f2937] dark:text-white" : "text-[#44474d] hover:bg-[#e2e8f8] hover:text-[#031632] dark:text-[#d1d5db] dark:hover:bg-[#1f2937] dark:hover:text-white"}`}>                  {active && <span className="absolute right-0 top-1/2 h-8 w-1 -translate-y-1/2 rounded-l bg-[#bb0011]" />}
                  <span className={`flex h-6 w-6 shrink-0 items-center justify-center text-base leading-none ${active ? "font-bold text-[#031632] dark:text-white" : ""}`}>{item.icon === "map-pin" ? (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]" aria-hidden="true">
                      <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
                      <circle cx="12" cy="10" r="3" />
                    </svg>
                  ) : item.icon}</span>
                  <span className="whitespace-nowrap text-sm font-medium">{item.name}</span>
                </button>
              )
            })}
          </nav>
          <div className="mt-7 space-y-0.5 border-t border-[#c5c6ce] pt-2 dark:border-[#374151]">
            {[{ icon: "⚙", label: "Settings", page: null }, { icon: "headphones", label: "Support", page: null }, { icon: "❓", label: "FAQ", page: "FAQ" }].map((item) => (
              <button key={item.label} onClick={() => item.page && onNavigate(item.page)} className="flex w-full items-center gap-3 rounded px-3 py-2 text-[#44474d] transition-all duration-200 hover:bg-[#e2e8f8] hover:text-[#031632] dark:text-[#d1d5db] dark:hover:bg-[#1f2937] dark:hover:text-white justify-start">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center text-base leading-none">
                  {item.icon === "headphones" ? (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]" aria-hidden="true">
                      <path d="M3 18v-6a9 9 0 0 1 18 0v6" />
                      <path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z" />
                    </svg>
                  ) : item.icon}
                </span>
                <span className="whitespace-nowrap text-sm font-medium">{item.label}</span>
              </button>
            ))}
          </div>
        </aside>
      </>
    )
  }

  return (
    <aside
      className={`
        fixed left-0 top-0 z-30 hidden h-screen flex-col overflow-hidden
        border-r border-[#c5c6ce]
        bg-[#f9f9ff] text-[#151c27]
        dark:border-[#374151] dark:bg-[#111827] dark:text-[#f3f4f6]
        transition-all duration-300 ease-in-out lg:flex
        ${collapsed ? "w-16 px-2" : "w-60 px-4"}
      `}
    >

      {/* BRANDING */}
      <div
        className={`
          mb-8 flex min-w-0 items-center
          ${collapsed ? "justify-center gap-0" : "gap-3"}
        `}
      >

        {/* LOGO */}
        <div
          className="
            flex h-10 w-10 shrink-0 items-center
            justify-center overflow-hidden rounded-full
            bg-[#1a2b48] text-lg leading-none text-white
            dark:bg-[#243b5a]
          "
        >
          🏛
        </div>

        {/* BRAND TEXT */}
        <div
          className={`
            overflow-hidden transition-all duration-300
            ${
              collapsed
                ? "w-0 opacity-0"
                : "w-auto opacity-100"
            }
          `}
        >
          <h1
            className="
              whitespace-nowrap text-lg font-bold
              text-[#031632]
              dark:text-[#f3f4f6]
            "
          >
            MPLADS Insight
          </h1>

          <p
            className="
              whitespace-nowrap text-xs
              text-[#44474d]
              dark:text-[#9ca3af]
            "
          >
            Auditor Portal
          </p>
        </div>

      </div>

      {/* MAIN NAVIGATION */}
      <nav className="space-y-1">

        {navigation.map((item) => {

          const active = currentPage === item.page

          return (
            <button
              key={item.name}
              onClick={() => onNavigate(item.page)}
              title={collapsed ? item.name : ""}
              className={`
                group relative flex w-full items-center
                gap-3 rounded px-3 py-2.5
                transition-all duration-200

                ${
                  collapsed
                    ? "justify-center"
                    : "justify-start"
                }

                ${
                  active
                    ? `
                      bg-[#f0f3ff]
                      text-[#031632]
                      dark:bg-[#1f2937]
                      dark:text-white
                    `
                    : `
                      text-[#44474d]
                      hover:bg-[#e2e8f8]
                      hover:text-[#031632]
                      dark:text-[#d1d5db]
                      dark:hover:bg-[#1f2937]
                      dark:hover:text-white
                    `
                }
              `}
            >

              {/* ACTIVE INDICATOR */}
              {active && (
                <span
                  className="
                    absolute right-0 top-1/2
                    h-8 w-1 -translate-y-1/2
                    rounded-l bg-[#bb0011]
                  "
                />
              )}

              {/* ICON */}
              <span
                className={`
                  flex h-6 w-6 shrink-0
                  items-center justify-center
                  text-base leading-none
                  ${
                    active
                      ? "font-bold text-[#031632] dark:text-white"
                      : ""
                  }
                `}
              >
                {item.icon === "map-pin" ? (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]" aria-hidden="true">
                    <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
                    <circle cx="12" cy="10" r="3" />
                  </svg>
                ) : item.icon}
              </span>

              {/* LABEL */}
              <span
                className={`
                  whitespace-nowrap text-sm font-medium
                  transition-all duration-300
                  ${
                    collapsed
                      ? "w-0 overflow-hidden opacity-0"
                      : "w-auto opacity-100"
                  }
                `}
              >
                {item.name}
              </span>

            </button>
          )
        })}

      </nav>

      {/* BOTTOM NAVIGATION — Settings, Support, FAQ */}
      <div className="mt-8 space-y-0.5 border-t
        border-[#c5c6ce] pt-3
        dark:border-[#374151]"
      >

        {[
          { icon: "⚙", label: "Settings", page: null },
          { icon: "headphones", label: "Support", page: null },
          { icon: "❓", label: "FAQ", page: "FAQ" },
        ].map((item) => (
          <button
            key={item.label}
            onClick={() => item.page && onNavigate(item.page)}
            title={collapsed ? item.label : ""}
            className={`
              flex w-full items-center gap-3 rounded
              px-3 py-2 text-[#44474d]
              transition-all duration-200
              hover:bg-[#e2e8f8]
              hover:text-[#031632]
              dark:text-[#d1d5db]
              dark:hover:bg-[#1f2937]
              dark:hover:text-white
              ${
                collapsed
                  ? "justify-center"
                  : "justify-start"
              }
            `}
          >

            <span className="flex h-6 w-6 shrink-0
              items-center justify-center text-base leading-none">
              {item.icon === "headphones" ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]" aria-hidden="true">
                  <path d="M3 18v-6a9 9 0 0 1 18 0v6" />
                  <path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z" />
                </svg>
              ) : item.icon}
            </span>

            <span
              className={`
                whitespace-nowrap text-sm font-medium
                transition-all duration-300
                ${
                  collapsed
                    ? "w-0 overflow-hidden opacity-0"
                    : "w-auto opacity-100"
                }
              `}
            >
              {item.label}
            </span>

          </button>
        ))}

      </div>

    </aside>
  )
}

export default Sidebar