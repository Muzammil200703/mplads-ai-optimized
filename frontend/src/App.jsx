import { useState, useEffect, lazy, Suspense, memo, useRef } from "react"
import Sidebar from "./components/Sidebar"
import TopBar from "./components/TopBar"
import { PageSkeleton } from "./components/Skeleton"
import { AuthProvider, useAuth } from "./context/AuthContext"

/* Application shell — single scroll-owner architecture:
   html/body never scroll; <main> is the only page-level scroll container
   (header and sidebar are viewport-fixed; overlays are viewport-bound).
   Page roots use min-h-full (not min-h-screen) so they size to <main>. */

const LoginView = lazy(() => import("./pages/Auth").then((m) => ({ default: m.LoginView })))
const SignupView = lazy(() => import("./pages/Auth").then((m) => ({ default: m.SignupView })))
const SavedProjectsPage = lazy(() => import("./pages/Workspace").then((m) => ({ default: m.SavedProjectsPage })))
const MyInvestigationsPage = lazy(() => import("./pages/Workspace").then((m) => ({ default: m.MyInvestigationsPage })))
const MyAuditCasesPage = lazy(() => import("./pages/Workspace").then((m) => ({ default: m.MyAuditCasesPage })))
const AdminPage = lazy(() => import("./pages/Workspace").then((m) => ({ default: m.AdminPage })))
const SettingsPage = lazy(() => import("./pages/Settings"))

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

function AppShell() {
  const { user, loading: authLoading } = useAuth()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [darkMode, setDarkMode] = useState(false)
  const [currentPage, setCurrentPage] = useState(
    () => (typeof window !== "undefined" && window.location.hash === "#signin" ? "Sign in" : "Overview")
  )
  // Global search — independent from project search
  const [globalSearchQuery, setGlobalSearchQuery] = useState("")
  // Project search — only set when navigating to Projects
  const [projectSearchQuery, setProjectSearchQuery] = useState("")
  const [drillDownParams, setDrillDownParams] = useState(null)
  const [selectedFY, setSelectedFY] = useState("")

  const isMobile = useIsMobile()
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(true)

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

  // Open a project drawer from a workspace page: switch to Projects, then
  // dispatch once the page is mounted (retry covers the lazy chunk load).
  const openProjectFromWorkspace = (projectId) => {
    setCurrentPage("Projects")
    if (isMobile) setMobileDrawerOpen(false)
    const dispatch = () => window.dispatchEvent(new CustomEvent("open-project", { detail: { projectId } }))
    setTimeout(dispatch, 400)
    setTimeout(dispatch, 1200)
  }

  // Page state preservation: track which pages have been visited so we keep them mounted
  const visitedPages = useRef(new Set(["Overview"]))
  // Add current page to visited set synchronously (not in useEffect)
  if (!visitedPages.current.has(currentPage)) {
    visitedPages.current.add(currentPage)
  }

  const renderPage = () => {
    // Auth pages render standalone (no sidebar nav entry, still inside shell)
    if (currentPage === "Sign in") return <LoginView onSwitch={() => setCurrentPage("Sign up")} />
    if (currentPage === "Sign up") return <SignupView onSwitch={() => setCurrentPage("Sign in")} />

    const pages = [
      { key: "Overview", el: <Overview darkMode={darkMode} onDrillDown={handleDrillDown} fy={selectedFY} /> },
      { key: "Projects", el: <Projects projectSearchQuery={projectSearchQuery} onClearProjectSearch={() => setProjectSearchQuery("")} drillDownParams={drillDownParams} onClearDrillDown={() => setDrillDownParams(null)} fy={selectedFY} /> },
      { key: "Risk Center", el: <RiskCenter drillDownParams={drillDownParams} onClearDrillDown={() => setDrillDownParams(null)} fy={selectedFY} /> },
      { key: "Reports", el: <Reports fy={selectedFY} /> },
      { key: "State Intelligence", el: <StateIntelligence onNavigateToProjects={(state) => handleDrillDown("Projects", { state })} fy={selectedFY} /> },
      { key: "Audit Priority", el: <AuditPriority fy={selectedFY} /> },
      { key: "Compare Projects", el: <CompareProjects fy={selectedFY} /> },
      { key: "FAQ", el: <FAQ /> },
      { key: "Settings", el: <SettingsPage darkMode={darkMode} onThemeToggle={() => setDarkMode((previous) => !previous)} /> },
      { key: "Saved Projects", el: <SavedProjectsPage onOpenProject={openProjectFromWorkspace} /> },
      { key: "My Investigations", el: <MyInvestigationsPage onOpenProject={openProjectFromWorkspace} /> },
      { key: "My Audit Cases", el: <MyAuditCasesPage onOpenProject={openProjectFromWorkspace} /> },
      { key: "Administration", el: <AdminPage /> },
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

  // Keep hash in sync so refresh/sign-in returns to the auth page when intended
  useEffect(() => {
    if (currentPage === "Sign in") window.location.hash = "signin"
    else if (window.location.hash === "#signin") window.location.hash = ""
  }, [currentPage])

  // After successful sign-in/sign-up, leave the auth page
  useEffect(() => {
    if (user && (currentPage === "Sign in" || currentPage === "Sign up")) {
      setCurrentPage("Overview")
    }
  }, [user]) // eslint-disable-line react-hooks/exhaustive-deps

  const getMainMargin = () => {
    if (isMobile) return "ml-0"
    return sidebarCollapsed ? "ml-16" : "ml-60"
  }

  return (
    <div
      className={`h-[100dvh] overflow-hidden ${
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
        searchQuery={globalSearchQuery}
        onSearchChange={setGlobalSearchQuery}
        onNavigateToResult={handleGlobalSearchNavigate}
        isMobile={isMobile}
        selectedFY={selectedFY}
        onFYChange={setSelectedFY}
      />

      <main
        className={`h-full overflow-x-auto overflow-y-auto pt-[64px] lg:pt-[72px] transition-[margin] duration-300 ease-in-out ${getMainMargin()}`}
      >
        {renderPage()}
      </main>
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  )
}

export default App
