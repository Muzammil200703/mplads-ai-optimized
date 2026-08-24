import { useState, useEffect } from "react"

import Sidebar from "./components/Sidebar"
import TopBar from "./components/TopBar"

import Overview from "./pages/Overview"
import Projects from "./pages/Projects"
import RiskCenter from "./pages/RiskCenter"
import Reports from "./pages/Reports"
import DataQuality from "./pages/DataQuality"
import StateIntelligence from "./pages/StateIntelligence"
import AuditPriority from "./pages/AuditPriority"

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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [darkMode, setDarkMode] = useState(false)
  const [currentPage, setCurrentPage] = useState("Overview")
  const [searchQuery, setSearchQuery] = useState("")
  const [drillDownParams, setDrillDownParams] = useState(null)

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

  const handleSearchSubmit = (query) => {
    setSearchQuery(query)
    setCurrentPage("Projects")
    if (isMobile) setMobileDrawerOpen(false)
  }

  const handleDrillDown = (page, params) => {
    setDrillDownParams(params || null)
    setCurrentPage(page)
    if (isMobile) setMobileDrawerOpen(false)
  }

  const renderPage = () => {
    switch (currentPage) {
      case "Overview":
        return <Overview darkMode={darkMode} onDrillDown={handleDrillDown} />
      case "Projects":
        return <Projects globalSearchQuery={searchQuery} onClearSearch={() => setSearchQuery("")} drillDownParams={drillDownParams} onClearDrillDown={() => setDrillDownParams(null)} />
      case "Risk Center":
        return <RiskCenter drillDownParams={drillDownParams} onClearDrillDown={() => setDrillDownParams(null)} />
      case "Reports":
        return <Reports />
      case "Data Quality":
        return <DataQuality />
      case "State Intelligence":
        return <StateIntelligence onNavigateToProjects={(state) => handleDrillDown("Projects", { state })} />
      case "Audit Priority":
        return <AuditPriority />
      default:
        return <Overview />
    }
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
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onSearchSubmit={handleSearchSubmit}
        isMobile={isMobile}
      />

      <main
        className={`min-h-screen pt-[64px] lg:pt-[78px] transition-all duration-300 ease-in-out ${getMainMargin()}`}
      >
        {renderPage()}
      </main>
    </div>
  )
}

export default App