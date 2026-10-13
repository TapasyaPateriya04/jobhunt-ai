/* The page frame: the bar at the top, the numbers and next step, the five tabs,
   the sidebar and the footer that links the legal pages. */
import { Link, Route, Routes } from "react-router-dom";

import { get } from "./api";
import { Notice, Panel } from "./components/ui";
import { Sidebar } from "./components/Sidebar";
import { useLoad } from "./hooks";
import { Privacy } from "./pages/Privacy";
import { Terms } from "./pages/Terms";
import { AppProvider, useApp } from "./state";
import type { TabKey } from "./state";
import { ApplicationsTab } from "./tabs/ApplicationsTab";
import { DocumentsTab } from "./tabs/DocumentsTab";
import { JobsTab } from "./tabs/JobsTab";
import { MatchesTab } from "./tabs/MatchesTab";
import { ResumeTab } from "./tabs/ResumeTab";

const TABS: { key: TabKey; label: string }[] = [
  { key: "resume", label: "Resume" },
  { key: "jobs", label: "Find jobs" },
  { key: "matches", label: "Matches" },
  { key: "applications", label: "Applications" },
  { key: "documents", label: "Documents" },
];

export default function App() {
  return (
    <AppProvider>
      <Routes>
        <Route path="/privacy" element={<LegalPage>{<Privacy />}</LegalPage>} />
        <Route path="/terms" element={<LegalPage>{<Terms />}</LegalPage>} />
        <Route path="*" element={<Dashboard />} />
      </Routes>
    </AppProvider>
  );
}

function TopBar({ children }: { children?: React.ReactNode }) {
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Link to="/" className="wordmark" style={{ borderBottom: 0, color: "inherit" }}>
          <span className="mark" />
          JobHunt AI
        </Link>
        <span className="spacer" />
        {children}
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="footer">
      <Link to="/privacy">Privacy policy</Link>
      <Link to="/terms">Terms and conditions</Link>
      <span>Runs on this machine. No account, no tracking.</span>
    </footer>
  );
}

function LegalPage({ children }: { children: React.ReactNode }) {
  return (
    <>
      <TopBar>
        <Link to="/">Back to JobHunt AI</Link>
      </TopBar>
      <main className="shell">
        <div className="prose" style={{ marginTop: 24 }}>
          {children}
        </div>
      </main>
      <Footer />
    </>
  );
}

function Dashboard() {
  const { tab, setTab, overview, error } = useApp();
  const health = useLoad<{ database_problem: string }>(() => get("/health"), []);
  const counts = overview?.counts ?? {};

  return (
    <>
      <TopBar>
        <span className="note">Everything stays on this machine</span>
      </TopBar>
      <main className="shell">
        <h1 style={{ marginTop: 24 }}>JobHunt AI</h1>
        <p className="lede">
          Find the jobs you can actually get, track your applications and write for each one.
        </p>

        <div className="layout">
          <Sidebar />
          <div className="main">
            {health.data?.database_problem && <Notice tone="bad">{health.data.database_problem}</Notice>}
            {error && <Notice tone="warn">{error}</Notice>}

            {overview && (
              <>
                {overview.has_resume && overview.stats.some((s) => s.value > 0) && (
                  <div className="stats">
                    {overview.stats.map((stat) => (
                      <div key={stat.label}>
                        <b>{stat.value}</b>
                        <span>{stat.label}</span>
                      </div>
                    ))}
                  </div>
                )}
                <div className="next">
                  <span>
                    <b>Next step:</b> {overview.next_step.text}
                  </span>
                  {overview.next_step.tab !== tab && (
                    <button
                      type="button"
                      className="small"
                      onClick={() => setTab(overview.next_step.tab as TabKey)}
                    >
                      Go to {TABS.find((t) => t.key === overview.next_step.tab)?.label}
                    </button>
                  )}
                </div>
              </>
            )}

            <div className="tabs" role="tablist" aria-label="What you want to do">
              {TABS.map((entry) => (
                <button
                  type="button"
                  role="tab"
                  key={entry.key}
                  aria-selected={tab === entry.key}
                  // On a phone the bar scrolls, so the tab in use is brought into view.
                  ref={(node) =>
                    tab === entry.key && node?.scrollIntoView({ inline: "center", block: "nearest" })
                  }
                  onClick={() => setTab(entry.key)}
                >
                  {entry.label}
                  {badge(entry.key, counts) !== null && <span className="tab-count">{badge(entry.key, counts)}</span>}
                </button>
              ))}
            </div>

            <Tab which={tab} />
          </div>
        </div>
      </main>
      <Footer />
    </>
  );
}

function badge(tab: TabKey, counts: Record<string, number>): number | null {
  if (tab === "applications") {
    const n = (counts.saved ?? 0) + (counts.applied ?? 0);
    return n || null;
  }
  return null;
}

function Tab({ which }: { which: TabKey }) {
  if (which === "resume") return <ResumeTab />;
  if (which === "jobs") return <JobsTab />;
  if (which === "matches") return <MatchesTab />;
  if (which === "applications") return <ApplicationsTab />;
  if (which === "documents") return <DocumentsTab />;
  return (
    <Panel>
      <p>Pick a tab above.</p>
    </Panel>
  );
}
