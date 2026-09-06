import { useEffect, useState } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { CommandPalette } from "@/components/CommandPalette";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Overview } from "@/routes/Overview";
import { Timeline } from "@/routes/Timeline";
import { VersionDetail } from "@/routes/VersionDetail";
import { Features } from "@/routes/Features";
import { FeatureDetail } from "@/routes/FeatureDetail";
import { Compare } from "@/routes/Compare";
import { Memory } from "@/routes/Memory";
import { Intelligence } from "@/routes/Intelligence";
import { SafeToChange } from "@/routes/SafeToChange";
import { Search } from "@/routes/Search";
import { NotFound } from "@/routes/NotFound";

export function App() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    setNavOpen(false);
    document.querySelector(".app-content")?.scrollTo(0, 0);
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <div className="app-shell">
      <div className={`sidebar-wrap${navOpen ? " sidebar-wrap--open" : ""}`}>
        <Sidebar onNavigate={() => setNavOpen(false)} />
        <div className="sidebar-scrim" onClick={() => setNavOpen(false)} />
      </div>

      <div className="app-main">
        <TopBar onOpenPalette={() => setPaletteOpen(true)} onOpenNav={() => setNavOpen(true)} />
        <main className="app-content">
          <ErrorBoundary key={location.pathname}>
            <div className="route-fade" key={location.pathname}>
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/timeline" element={<Timeline />} />
                <Route path="/version/:id" element={<VersionDetail />} />
                <Route path="/features" element={<Features />} />
                <Route path="/feature/:name" element={<FeatureDetail />} />
                <Route path="/compare" element={<Compare />} />
                <Route path="/compare/:pair" element={<Compare />} />
                <Route path="/memory" element={<Memory />} />
                <Route path="/memory/:q" element={<Memory />} />
                <Route path="/intelligence" element={<Intelligence />} />
                <Route path="/safe-to-change" element={<SafeToChange />} />
                <Route path="/search" element={<Search />} />
                <Route path="/search/:q" element={<Search />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </div>
          </ErrorBoundary>
        </main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
