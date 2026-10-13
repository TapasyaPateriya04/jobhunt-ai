/* One place for what every screen needs: the resume in use, the settings the app
   found, the country matches are judged against and the model that writes drafts. */
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { get } from "./api";
import type { Catalog, Overview, Resume, ResumeListEntry, Status } from "./api";
import { useLoad } from "./hooks";

export type TabKey = "resume" | "jobs" | "matches" | "applications" | "documents";

type Ctx = {
  catalog: Catalog | null;
  status: Status | null;
  overview: Overview | null;
  resume: Resume | null;
  resumes: ResumeListEntry[];
  resumeId: number | null;
  loading: boolean;
  error: string;
  country: string | null;
  model: string | null;
  tab: TabKey;
  writeFor: number | null;
  pickResume: (id: number) => void;
  setCountry: (country: string) => void;
  setModel: (model: string) => void;
  setTab: (tab: TabKey) => void;
  writeDocumentsFor: (matchId: number | null) => void;
  reload: () => void;
};

const AppContext = createContext<Ctx | null>(null);

export function useApp(): Ctx {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp outside the provider");
  return ctx;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [resumeId, setResumeId] = useState<number | null>(null);
  const [country, setCountryState] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("resume");
  const [writeFor, setWriteFor] = useState<number | null>(null);
  const [version, setVersion] = useState(0);

  const catalog = useLoad<Catalog>(() => get<Catalog>("/catalog"), []);
  const status = useLoad<Status>(() => get<Status>("/status"), [version]);
  const resumes = useLoad<{ resumes: ResumeListEntry[] }>(() => get("/resumes"), [version]);
  const resume = useLoad<{ resume: Resume | null }>(
    () => get("/resume", resumeId ? { id: resumeId } : undefined),
    [resumeId, version],
  );
  // The numbers at the top are read again on every tab change: jobs can land from another tab
  // (a search, the timed refresh) without anything else telling this provider.
  const overview = useLoad<Overview>(
    () => get("/overview", resumeId ? { resume_id: resumeId } : undefined),
    [resumeId, version, tab],
  );
  const countries = useLoad<{ configured: string }>(() => get("/countries"), []);

  // The resume the server picked becomes the one in use, so the picker has a value.
  const currentId = resume.data?.resume?.id ?? null;
  useEffect(() => {
    if (resumeId === null && currentId !== null) setResumeId(currentId);
  }, [currentId, resumeId]);

  // Default country from .env, and the default writing model from what is installed.
  useEffect(() => {
    if (country === null && countries.data) setCountryState(countries.data.configured ?? "");
  }, [countries.data, country]);
  useEffect(() => {
    if (model !== null || !status.data) return;
    const { models, ollama } = status.data;
    if (!models.length) return;
    const configured = models.find((m) => same(m, ollama.configured_model));
    setModel(configured ?? models[0]);
  }, [status.data, model]);

  // Open on the tab with the work to do, once, when the app first knows the state.
  const [landed, setLanded] = useState(false);
  useEffect(() => {
    if (landed || !overview.data) return;
    setTab(overview.data.next_step.tab as TabKey);
    setLanded(true);
  }, [overview.data, landed]);

  const value = useMemo<Ctx>(
    () => ({
      catalog: catalog.data,
      status: status.data,
      overview: overview.data,
      resume: resume.data?.resume ?? null,
      resumes: resumes.data?.resumes ?? [],
      resumeId: currentId,
      loading: catalog.loading || resume.loading,
      error: catalog.error || resume.error || status.error,
      country,
      model,
      tab,
      writeFor,
      pickResume: setResumeId,
      setCountry: setCountryState,
      setModel,
      setTab,
      writeDocumentsFor: setWriteFor,
      reload: () => setVersion((n) => n + 1),
    }),
    [
      catalog.data, catalog.loading, catalog.error,
      status.data, status.error,
      overview.data,
      resume.data, resume.loading, resume.error,
      resumes.data,
      currentId, country, model, tab, writeFor,
    ],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

/** 'mistral' and 'mistral:latest' name the same Ollama model. */
function same(a: string, b: string): boolean {
  const norm = (s: string) => (s.includes(":") ? s : `${s}:latest`);
  return norm(a || "") === norm(b || "");
}
