import { useEffect, useMemo, useState } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import Navbar from "./components/Navbar";
import Sidebar from "./components/Sidebar";
import ThemeProvider from "./theme/ThemeProvider";
import Dashboard from "./pages/Dashboard";
import Campaigns from "./pages/Campaigns";
import Opportunities from "./pages/Opportunities";
import LeadDiscovery from "./pages/LeadDiscovery";
import Leads from "./pages/Leads";
import Calls from "./pages/Calls";
import Emails from "./pages/Emails";
import Knowledge from "./pages/Knowledge";
import Settings from "./pages/Settings";

const pageTitles = {
  "/": "Dashboard",
  "/campaigns": "Campaigns",
  "/opportunities": "Opportunities",
  "/discovery": "Lead Discovery",
  "/leads": "Leads",
  "/calls": "Calls",
  "/emails": "Emails",
  "/knowledge": "Knowledge",
  "/settings": "Settings",
};

const pageTransition = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
  transition: { duration: 0.32, ease: [0.22, 1, 0.36, 1] },
};

function AppShell() {
  const location = useLocation();
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const pageTitle = useMemo(
    () => pageTitles[location.pathname] || "AI Lead Generation",
    [location.pathname]
  );

  // lock body scroll while the mobile drawer is open
  useEffect(() => {
    document.body.style.overflow = isMobileSidebarOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [isMobileSidebarOpen]);

  return (
    <div className="min-h-screen overflow-x-hidden">
      <AnimatePresence>
        {isMobileSidebarOpen && (
          <motion.button
            key="scrim"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            type="button"
            aria-label="Close navigation"
            className="fixed inset-0 z-40 bg-black/55 backdrop-blur-sm lg:hidden"
            onClick={() => setIsMobileSidebarOpen(false)}
          />
        )}
      </AnimatePresence>

      <Sidebar
        collapsed={isSidebarCollapsed}
        mobileOpen={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
        onToggleCollapse={() => setIsSidebarCollapsed((value) => !value)}
      />

      <div
        className={[
          "flex min-h-screen min-w-0 flex-col transition-[padding] duration-400 ease-spring",
          isSidebarCollapsed ? "lg:pl-sidebar-sm" : "lg:pl-sidebar",
        ].join(" ")}
      >
        <Navbar
          pageTitle={pageTitle}
          collapsed={isSidebarCollapsed}
          onMenuClick={() => setIsMobileSidebarOpen(true)}
          onCollapseClick={() => setIsSidebarCollapsed((value) => !value)}
        />

        <main className="min-w-0 flex-1 px-4 py-6 sm:px-5 lg:px-8 lg:py-8">
          <div className="mx-auto w-full min-w-0 max-w-[1440px]">
            <AnimatePresence mode="wait">
              <motion.div key={location.pathname} {...pageTransition}>
                <Routes location={location}>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/campaigns" element={<Campaigns />} />
                  <Route path="/opportunities" element={<Opportunities />} />
                  <Route path="/discovery" element={<LeadDiscovery />} />
                  <Route path="/leads" element={<Leads />} />
                  <Route path="/calls" element={<Calls />} />
                  <Route path="/emails" element={<Emails />} />
                  <Route path="/knowledge" element={<Knowledge />} />
                  <Route path="/settings" element={<Settings />} />
                </Routes>
              </motion.div>
            </AnimatePresence>
          </div>
        </main>
      </div>
    </div>
  );
}

function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
