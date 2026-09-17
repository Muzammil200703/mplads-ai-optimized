import React, { useState, lazy, Suspense } from "react";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import AssistantWidget from "./components/AssistantWidget";

const Landing = lazy(() => import("./pages/Landing"));
const Overview = lazy(() => import("./pages/Overview"));
const Projects = lazy(() => import("./pages/Projects"));
const RiskCenter = lazy(() => import("./pages/RiskCenter"));
const AuditCenter = lazy(() => import("./pages/AuditCenter"));
const VendorIntelligence = lazy(() => import("./pages/VendorIntelligence"));
const StateIntelligence = lazy(() => import("./pages/StateIntelligence"));
const VerificationQueue = lazy(() => import("./pages/VerificationQueue"));
const MyVerifications = lazy(() => import("./pages/MyVerifications"));
const MyDistrict = lazy(() => import("./pages/MyDistrict"));
const Inquiries = lazy(() => import("./pages/Inquiries"));
const AuditPriority = lazy(() => import("./pages/AuditPriority"));
const Workspace = lazy(() => import("./pages/Workspace"));
const CompareProjects = lazy(() => import("./pages/CompareProjects"));
const Reports = lazy(() => import("./pages/Reports"));
const FAQ = lazy(() => import("./pages/FAQ"));
const Settings = lazy(() => import("./pages/Settings"));
const Auth = lazy(() => import("./pages/Auth"));
const VerifyPortal = lazy(() => import("./pages/VerifyPortal"));
const VendorNetwork = lazy(() => import("./pages/VendorNetwork"));

export default function App() {
  const [currentPage, setCurrentPage] = useState(() => 
    typeof window !== "undefined" && window.location.hash === "#signin" ? "Sign in" : "Landing"
  );

  const renderPage = () => {
    switch (currentPage) {
      case "Landing": return <Landing onLaunch={() => setCurrentPage("Overview")} />;
      case "Overview": return <Overview />;
      case "Projects": return <Projects />;
      case "Risk Center": return <RiskCenter />;
      case "Audit Center": return <AuditCenter />;
      case "Vendor Intelligence": return <VendorIntelligence />;
      case "Vendor Network": return <VendorNetwork />;
      case "State Intelligence": return <StateIntelligence />;
      case "Verification Queue": return <VerificationQueue />;
      case "My Verifications": return <MyVerifications />;
      case "My District": return <MyDistrict />;
      case "Inquiries": return <Inquiries />;
      case "Audit Priority": return <AuditPriority />;
      case "Workspace": return <Workspace />;
      case "Compare Projects": return <CompareProjects />;
      case "Reports": return <Reports />;
      case "FAQ": return <FAQ />;
      case "Settings": return <Settings />;
      case "Sign in": return <Auth onSuccess={() => setCurrentPage("Overview")} />;
      case "Verify Portal": return <VerifyPortal />;
      default: return <Overview />;
    }
  };

  if (currentPage === "Landing") {
    return (
      <Suspense fallback={<div className="min-h-screen bg-slate-900 flex items-center justify-center text-slate-400">Loading...</div>}>
        <Landing onLaunch={() => setCurrentPage("Overview")} />
        <AssistantWidget currentPage={currentPage} />
      </Suspense>
    );
  }

  return (
    <div className="flex h-screen bg-slate-900 text-slate-100 overflow-hidden font-sans">
      <Sidebar currentPage={currentPage} setCurrentPage={setCurrentPage} />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TopBar currentPage={currentPage} setCurrentPage={setCurrentPage} />
        <main className="flex-1 overflow-y-auto p-6">
          <Suspense fallback={<div className="flex items-center justify-center h-full text-slate-400">Loading page...</div>}>
            {renderPage()}
          </Suspense>
        </main>
      </div>
      <AssistantWidget currentPage={currentPage} />
    </div>
  );
}