/* The page frame: the bar at the top, the numbers and next step, the five tabs,
   the sidebar and the footer that links the legal pages. */
import { useEffect, useRef } from "react";
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

/** Logo on the left, the tabs in the centre (when given), and `end` on the right. */
function TopBar({ nav, end }: { nav?: React.ReactNode; end?: React.ReactNode }) {
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Link to="/" className="wordmark" style={{ borderBottom: 0 }}>
          <span className="mark" />
          JobHunt AI
        </Link>
        {nav ?? <span />}
        <span style={{ minWidth: 0 }}>{end}</span>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="footer">
      <span>Data stays on this laptop, in SQLite. No account, no tracking.</span>
      <span className="spacer" />
      <Link to="/privacy">Privacy</Link>
      <Link to="/terms">Terms</Link>
    </footer>
  );
}

function LegalPage({ children }: { children: React.ReactNode }) {
  return (
    <>
      <TopBar end={<Link to="/">Back to JobHunt AI</Link>} />
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
  const { tab, setTab, overview, error, resume } = useApp();
  const picked = useRef(false);

  // A long list leaves the page far down, so a new tab starts at its own top. The scroll
  // runs after the new tab has rendered, or it would aim at the old content's height.
  // The tabs live in the sticky top bar, so the top of the page is the top of the tab.
  useEffect(() => {
    if (!picked.current) return;
    const frame = requestAnimationFrame(() => {
      if (window.scrollY > 0) window.scrollTo({ top: 0, behavior: "smooth" });
    });
    return () => cancelAnimationFrame(frame);
  }, [tab]);
  const health = useLoad<{ database_problem: string }>(() => get("/health"), []);
  const counts = overview?.counts ?? {};

  const nav = (
    <div className="tabs nav" role="tablist" aria-label="What you want to do">
      {TABS.map((entry) => (
        <button
          type="button"
          role="tab"
          key={entry.key}
          aria-selected={tab === entry.key}
          // On a phone the bar scrolls sideways, so the tab in use is brought into
          // view. Only the bar moves: scrollIntoView would scroll the page as well.
          ref={(node) => {
            if (tab !== entry.key || !node) return;
            const bar = node.parentElement;
            if (bar) bar.scrollLeft = node.offsetLeft - (bar.clientWidth - node.clientWidth) / 2;
          }}
          onClick={() => {
            picked.current = true;
            setTab(entry.key);
          }}
        >
          {entry.label}
          {badge(entry.key, counts) !== null && <span className="tab-count">{badge(entry.key, counts)}</span>}
        </button>
      ))}
    </div>
  );

  return (
    <>
      <TopBar
        nav={nav}
        end={
          <span className="file" title={resume ? `Resume in use: ${resume.name}` : undefined}>
            {resume ? resume.name : "No resume yet"}
          </span>
        }
      />
      <main className="shell">
        {/* Matches uses the full width: the list and the job side by side. The sidebar's
            model picker stays on every other tab. */}
        <div className={`layout${tab === "matches" ? " wide" : ""}`}>
          {tab !== "matches" && <Sidebar />}
          <div className="main">
            {health.data?.database_problem && <Notice tone="bad">{health.data.database_problem}</Notice>}
            {error && <Notice tone="warn">{error}</Notice>}

            {/* Matches opens straight on its filters, list and job, as in the layout spec. */}
            {overview && tab !== "matches" && (
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

            {/* Keyed by tab, so each new tab fades in once instead of popping in. */}
            <div className="tabpanel enter" role="tabpanel" key={tab}>
              <Tab which={tab} />
            </div>
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
