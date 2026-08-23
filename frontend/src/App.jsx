import { useState } from "react"

import Sidebar from "./components/Sidebar"
import TopBar from "./components/TopBar"

import Overview from "./pages/Overview"
import Projects from "./pages/Projects"
import RiskCenter from "./pages/RiskCenter"
import Reports from "./pages/Reports"
import DataQuality from "./pages/DataQuality"
import StateIntelligence from "./pages/StateIntelligence"
import AuditPriority from "./pages/AuditPriority"

function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [darkMode, setDarkMode] = useState(false)
  const [currentPage, setCurrentPage] = useState("Overview")
  const [searchQuery, setSearchQuery] = useState("")
  const [drillDownParams, setDrillDownParams] = useState(null)

  const toggleSidebar = () => {
    setSidebarCollapsed((previous) => !previous)
  }

  const handleSearchSubmit = (query) => {
    setSearchQuery(query)
    setCurrentPage("Projects")
  }

  const handleDrillDown = (page, params) => {
    setDrillDownParams(params || null)
    setCurrentPage(page)
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

  return (
    <div
      className={`
        min-h-screen overflow-x-hidden
        ${
          darkMode
            ? "dark bg-[#111827] text-[#f3f4f6]"
            : "bg-[#f9f9ff] text-[#151c27]"
        }
      `}
    >

      <Sidebar
        collapsed={sidebarCollapsed}
        currentPage={currentPage}
        onNavigate={setCurrentPage}
        darkMode={darkMode}
      />

      <TopBar
        collapsed={sidebarCollapsed}
        onMenuClick={toggleSidebar}
        currentPage={currentPage}
        onNavigate={setCurrentPage}
        darkMode={darkMode}
        onThemeToggle={() =>
          setDarkMode((previous) => !previous)
        }
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onSearchSubmit={handleSearchSubmit}
      />

      <main
        className={`
          min-h-screen
          pt-[78px]
          transition-all
          duration-300
          ease-in-out
          ${
            sidebarCollapsed
              ? "ml-16"
              : "ml-60"
          }
        `}
      >
        {renderPage()}
      </main>

    </div>
  )
}

export default App