import { useState, useEffect, lazy, Suspense, memo, useRef } from "react"

import Sidebar from "./components/Sidebar"
import TopBar from "./components/TopBar"
import { PageSkeleton } from "./components/Skeleton"

// Lazy-load page components — only the active page is loaded
const Overview = lazy(() => import("./pages/Overview"))
const Projects = lazy(() => import("./pages/Projects"))
const RiskCenter = lazy(() => import("./pages/RiskCenter"))
const Reports = lazy(() => import("./pages/Reports"))
const StateIntelligence = lazy(() => import("./pages/StateIntelligence"))
const AuditPriority = lazy(() => import("./pages/AuditPriority"))
const CompareProjects = lazy(() => import("./pages/CompareProjects"))
const FAQ = lazy(() => import("./pages/FAQ"))

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== "undefined" ? window.innerWidth < 1024 : false
  )
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1023px)")
    const handler = (e) => setIsMobile(e.matches)
    mq.addEventListener("change", handler)
    setIsMobile(mq.matches)
    return () => mq.removeEventListener("change", handler)
  }, [])
  return isMobile
}

function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true)
  const [darkMode, setDarkMode] = useState(false)
  const [currentPage, setCurrentPage] = useState("Overview")
  // Global search — independent from project search
  const [globalSearchQuery, setGlobalSearchQuery] = useState("")
  // Project search — only set when navigating to Projects
  const [projectSearchQuery, setProjectSearchQuery] = useState("")
  const [drillDownParams, setDrillDownParams] = useState(null)
  const [selectedFY, setSelectedFY] = useState("")

  const isMobile = useIsMobile()
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false)

  const handleNavigate = (page) => {
    setCurrentPage(page)
    if (isMobile) setMobileDrawerOpen(false)
  }

  const toggleSidebar = () => {
    if (isMobile) {
      setMobileDrawerOpen((prev) => !prev)
    } else {
      setSidebarCollapsed((previous) => !previous)
    }
  }

  const closeMobileDrawer = () => setMobileDrawerOpen(false)

  // Keyboard shortcut: Ctrl+B or [ to toggle sidebar
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "b") {
        e.preventDefault()
        toggleSidebar()
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [isMobile])

  // Listen for navigate-to-project events from any component (e.g. RiskCenter modal)
  useEffect(() => {
    const handler = (e) => {
      const query = e.detail?.query
      if (query) {
        setProjectSearchQuery(query)
        setCurrentPage("Projects")
        if (isMobile) setMobileDrawerOpen(false)
      }
    }
    window.addEventListener("navigate-to-project", handler)
    return () => window.removeEventListener("navigate-to-project", handler)
  }, [isMobile])

  // Global search submit: only navigate when user explicitly selects a result
  const handleGlobalSearchNavigate = (page, params) => {
    setGlobalSearchQuery("")
    if (params?.keyword) {
      setProjectSearchQuery(params.keyword)
    }
    setCurrentPage(page)
    if (isMobile) setMobileDrawerOpen(false)
  }

  const handleDrillDown = (page, params) => {
    setDrillDownParams(params || null)
    setCurrentPage(page)
    if (isMobile) setMobileDrawerOpen(false)
  }

  // Page state preservation: track which pages have been visited so we keep them mounted
  const visitedPages = useRef(new Set(["Overview"]))
  // Add current page to visited set synchronously (not in useEffect)
  if (!visitedPages.current.has(currentPage)) {
    visitedPages.current.add(currentPage)
  }

  const renderPage = () => {
    const pages = [
      { key: "Overview", el: <Overview darkMode={darkMode} onDrillDown={handleDrillDown} fy={selectedFY} /> },
      { key: "Projects", el: <Projects projectSearchQuery={projectSearchQuery} onClearProjectSearch={() => setProjectSearchQuery("")} drillDownParams={drillDownParams} onClearDrillDown={() => setDrillDownParams(null)} fy={selectedFY} /> },
      { key: "Risk Center", el: <RiskCenter drillDownParams={drillDownParams} onClearDrillDown={() => setDrillDownParams(null)} fy={selectedFY} /> },
      { key: "Reports", el: <Reports fy={selectedFY} /> },
      { key: "State Intelligence", el: <StateIntelligence onNavigateToProjects={(state) => handleDrillDown("Projects", { state })} fy={selectedFY} /> },
      { key: "Audit Priority", el: <AuditPriority fy={selectedFY} /> },
      { key: "Compare Projects", el: <CompareProjects fy={selectedFY} /> },
      { key: "FAQ", el: <FAQ /> },
    ]
    return (
      <Suspense fallback={<PageSkeleton cards={4} columns={4} />}>
        {pages.map(({ key, el }) => (
          <div key={key} style={{ display: key === currentPage ? "block" : "none" }}>
            {visitedPages.current.has(key) ? el : null}
          </div>
        ))}
      </Suspense>
    )
  }

  const getMainMargin = () => {
    if (isMobile) return "ml-0"
    return sidebarCollapsed ? "ml-16" : "ml-60"
  }

  return (
    <div
      className={`min-h-screen overflow-x-hidden ${
        darkMode
          ? "dark bg-[#111827] text-[#f3f4f6]"
          : "bg-[#f9f9ff] text-[#151c27]"
      }`}
    >
      {isMobile && mobileDrawerOpen && (
        <div
          className="fixed inset-0 z-[55] bg-black/50 transition-opacity"
          onClick={closeMobileDrawer}
        />
      )}

      <Sidebar
        collapsed={isMobile ? false : sidebarCollapsed}
        currentPage={currentPage}
        onNavigate={handleNavigate}
        darkMode={darkMode}
        isMobile={isMobile}
        isOpen={mobileDrawerOpen}
        onClose={closeMobileDrawer}
      />

      <TopBar
        collapsed={isMobile ? false : sidebarCollapsed}
        onMenuClick={toggleSidebar}
        currentPage={currentPage}
        onNavigate={handleNavigate}
        darkMode={darkMode}
        onThemeToggle={() => setDarkMode((previous) => !previous)}
        searchQuery={globalSearchQuery}
        onSearchChange={setGlobalSearchQuery}
        onNavigateToResult={handleGlobalSearchNavigate}
        isMobile={isMobile}
        selectedFY={selectedFY}
        onFYChange={setSelectedFY}
      />

      <main
        className={`min-h-screen pt-[64px] lg:pt-[72px] transition-all duration-300 ease-in-out ${getMainMargin()}`}
      >
        {renderPage()}
      </main>
    </div>
  )
}

export default App