/* Find jobs tab: search the sources, paste a posting, see what is stored,
   back up or clean up. */
import { useEffect, useState } from "react";

import { del, download, get, post } from "../api";
import type { Job, RefreshState, SearchResult } from "../api";
import { countLabel, Chips, Empty, Field, Meta, Notice, OpenPosting, Panel, Skeleton, Working } from "../components/ui";
import { message, timeAgo, useFlash, useLoad } from "../hooks";
import { useApp } from "../state";

const PAGE = 10;

export function JobsTab() {
  const { catalog, resume, resumeId, country, reload } = useApp();
  const [keywords, setKeywords] = useState("");
  const [location, setLocation] = useState("");
  const [maxJobs, setMaxJobs] = useState(20);
  const [sources, setSources] = useState<string[]>([]);
  const [searching, setSearching] = useState(false);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [note, tone, flash] = useFlash();
  const [shown, setShown] = useState(PAGE);

  const stored = useLoad<{ jobs: Job[] }>(() => get("/jobs", { limit: 50 }), [], true);

  // The first search starts from the resume and .env, then the user's own text wins.
  useEffect(() => {
    if (!keywords && resume?.suggested_keywords) setKeywords(resume.suggested_keywords);
    if (!location && resume?.suggested_location) setLocation(resume.suggested_location);
  }, [resume, keywords, location]);
  useEffect(() => {
    if (!sources.length && catalog) {
      setSources(catalog.sources.filter((s) => s.default && s.configured).map((s) => s.key));
      setMaxJobs(Math.min(20, catalog.max_jobs_per_session));
    }
  }, [catalog, sources.length]);

  async function search() {
    if (!keywords.trim()) {
      flash("Enter at least one keyword.", "warn");
      return;
    }
    if (!sources.length) {
      flash("Pick at least one source.", "warn");
      return;
    }
    setSearching(true);
    setResult(null);
    try {
      const found = await post<SearchResult>("/jobs/search", {
        keywords,
        location,
        max_jobs: maxJobs,
        sources,
        resume_id: resumeId,
        country,
      });
      setResult(found);
      stored.reload();
      reload();
    } catch (exc) {
      flash(message(exc), "bad");
    } finally {
      setSearching(false);
    }
  }

  const cap = catalog?.max_jobs_per_session ?? 50;
  const jobs = stored.data?.jobs ?? [];

  return (
    <>
      <Panel title="Search the job sources">
        <div className="stack">
          <div className="grid2">
            <Field label="Job keywords" help="Starts with the main language on your resume.">
              <input
                type="text"
                value={keywords}
                placeholder="Java Developer, Backend Engineer"
                onChange={(event) => setKeywords(event.target.value)}
              />
            </Field>
            <Field
              label="Location"
              help="Himalayas and the company boards keep jobs in this place. The Muse needs its own spelling, e.g. Bangalore, India."
            >
              <input
                type="text"
                value={location}
                placeholder="Remote, or Bangalore, India"
                onChange={(event) => setLocation(event.target.value)}
              />
            </Field>
          </div>

          <Field label={`Most jobs to collect: ${maxJobs}`} help={`The cap from .env is ${cap} per search.`}>
            <input
              type="range"
              min={5}
              max={Math.max(5, Math.min(50, cap))}
              step={1}
              value={maxJobs}
              onChange={(event) => setMaxJobs(Number(event.target.value))}
            />
          </Field>

          <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
            <legend style={{ fontSize: "0.85rem", fontWeight: 500, padding: 0, marginBottom: 6 }}>Sources</legend>
            <div className="grid2">
              {(catalog?.sources ?? []).map((source) => (
                <label className="check" key={source.key} style={{ alignItems: "flex-start", minHeight: 0 }}>
                  <input
                    type="checkbox"
                    checked={sources.includes(source.key)}
                    disabled={!source.configured}
                    onChange={(event) =>
                      setSources((current) =>
                        event.target.checked
                          ? [...current, source.key]
                          : current.filter((key) => key !== source.key),
                      )
                    }
                  />
                  <span>
                    <span style={{ fontWeight: 500 }}>{source.name}</span>
                    <br />
                    <span className="hint">
                      {source.configured ? source.about : "Not configured in .env, so there is nothing to read."}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="row">
            <button type="button" className="primary" onClick={() => void search()} disabled={searching}>
              Find jobs
            </button>
            <span className="hint">
              Requests are spaced out to be polite to each site, so a search can take a minute.
            </span>
          </div>

          {searching && <Working text="Collecting jobs, then scoring them against your resume..." />}
          {note && <Notice tone={tone}>{note}</Notice>}
          {result && <SearchSummary result={result} />}
        </div>
      </Panel>

      <AutoRefresh />
      <AddJobYourself keywords={keywords} location={location} onAdded={() => { stored.reload(); reload(); }} />

      <Panel title="Recently stored jobs" count={jobs.length ? `${jobs.length} newest` : undefined}>
        {stored.loading ? (
          <Skeleton rows={3} />
        ) : stored.error ? (
          <Notice tone="bad">{stored.error}</Notice>
        ) : !jobs.length ? (
          <Empty
            icon="search"
            title="No jobs collected yet"
            hint="Enter keywords and a location above, then press Find jobs."
          />
        ) : (
          <div className="stack">
            <p className="hint">Scores and filters are on the Matches tab.</p>
            <div className="joblist">
              {jobs.slice(0, shown).map((job, i) => (
                <article className="jobrow" key={job.id ?? `${job.title}-${i}`}>
                  <div className="head">
                    <div>
                      <p className="title">{job.title}</p>
                      <Meta
                        parts={[
                          job.company,
                          job.location,
                          timeAgo(job.posted_date),
                          job.source_name,
                          job.experience_years !== null ? `asks ${job.experience_years} years` : null,
                        ]}
                      />
                    </div>
                    <OpenPosting url={job.url} small />
                  </div>
                  {job.skills.length > 0 && <Chips items={job.skills} empty={null} />}
                  {job.snippet && <p className="hint">{job.snippet}</p>}
                </article>
              ))}
            </div>
            {shown < jobs.length && (
              <button type="button" onClick={() => setShown(shown + PAGE)}>
                Show {Math.min(PAGE, jobs.length - shown)} more
              </button>
            )}
          </div>
        )}
      </Panel>

      <Housekeeping onChanged={() => { stored.reload(); reload(); }} />
      <Panel title="How this app collects jobs politely" tone="wash">
        <div className="stack">
          {(catalog?.collection_note ?? []).map((part) => (
            <div key={part.title}>
              <p style={{ fontWeight: 500 }}>{part.title}</p>
              <p className="hint">{part.body}</p>
            </div>
          ))}
        </div>
      </Panel>
    </>
  );
}

function SearchSummary({ result }: { result: SearchResult }) {
  if (!result.found) {
    return (
      <Notice tone="warn">
        No jobs came back. Try broader keywords, a different location or another source.
      </Notice>
    );
  }
  const split = result.per_source.map((p) => `${p.count} from ${p.name}`).join(", ");
  const tail = result.score_error
    ? result.score_error
    : result.scored
      ? `All ${result.scored} stored jobs are scored. Open Matches to see the best ones.`
      : "Upload your resume on the Resume tab to score them.";
  return (
    <div className="stack">
      {result.waiting.length > 0 && (
        <Notice tone="info">
          Skipping sites searched recently, to avoid being blocked. Next search allowed:{" "}
          {result.waiting.map((w) => `${w.name} in ${w.minutes} min`).join(", ")}.
        </Notice>
      )}
      <Notice tone={result.score_error ? "warn" : "ok"}>
        Collected {result.found} jobs ({split}); {result.new} {result.new === 1 ? "is" : "are"} new. {tail}
      </Notice>
    </div>
  );
}

/** LinkedIn and Naukri, when they are turned on, are searched again once their wait is over. */
function AutoRefresh() {
  const { catalog, resumeId, reload } = useApp();
  const [on, setOn] = useState(true);
  const [note, tone, flash] = useFlash();
  const state = useLoad<RefreshState>(() => get("/jobs/refresh-state"), [], Boolean(catalog?.auto_refresh_offered));

  const minutes = state.data?.minutes ?? catalog?.refresh_minutes ?? 60;
  useEffect(() => {
    if (!on || !catalog?.auto_refresh_offered) return;
    const timer = window.setInterval(
      () => {
        post<{ searched: string[]; new: number }>("/jobs/refresh", undefined, { resume_id: resumeId ?? "" })
          .then((result) => {
            if (result.new) {
              flash(`${result.new} new jobs from ${result.searched.join(" and ")}.`);
              reload();
            }
            state.reload();
          })
          .catch(() => undefined);
      },
      minutes * 60_000,
    );
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [on, minutes, resumeId, catalog?.auto_refresh_offered]);

  if (!catalog?.auto_refresh_offered) return null;
  const last = (state.data?.sites ?? [])
    .map((site) => (site.last_run ? `${site.name} at ${clock(site.last_run)}` : ""))
    .filter(Boolean)
    .join(", ");

  return (
    <Panel title="LinkedIn and Naukri">
      <label className="check">
        <input type="checkbox" checked={on} onChange={(event) => setOn(event.target.checked)} />
        <span>Search them again every {minutes} minutes while this page is open</span>
      </label>
      <p className="hint">
        Uses the keywords and location above. Each site is searched at most once per the wait set in .env, counting
        the searches you start yourself.
      </p>
      {last && <p className="hint">Last searched: {last}.</p>}
      {note && (
        <div style={{ marginTop: 10 }}>
          <Notice tone={tone}>{note}</Notice>
        </div>
      )}
    </Panel>
  );
}

function AddJobYourself({
  keywords,
  location,
  onAdded,
}: {
  keywords: string;
  location: string;
  onAdded: () => void;
}) {
  const { resumeId } = useApp();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ text: "", url: "", title: "", company: "", location: "" });
  const [busy, setBusy] = useState(false);
  const [note, tone, flash] = useFlash();
  const search = useLoad<{ url: string }>(
    () => get("/jobs/linkedin-search-url", { keywords, location }),
    [keywords, location],
    open,
  );

  async function add() {
    setBusy(true);
    try {
      const result = await post<{ job: Job; new: boolean; scored?: number; score_error?: string }>(
        "/jobs/manual",
        { ...form, resume_id: resumeId },
      );
      const what = `${result.job.title} at ${result.job.company}`;
      if (!result.new) {
        flash(`${what} is already stored.`, "info");
      } else {
        const tail = result.score_error
          ? result.score_error
          : result.scored
            ? "Open Matches to see its score."
            : "Upload your resume on the Resume tab to score it.";
        flash(`Added ${what}. ${tail}`, result.score_error ? "warn" : "ok");
        setForm({ text: "", url: "", title: "", company: "", location: "" });
        onAdded();
      }
    } catch (exc) {
      flash(message(exc), "bad");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel
      title="Add a job yourself"
      action={
        <button type="button" className="quiet small" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "Close" : "Open"}
        </button>
      }
    >
      <p className="hint">
        The app never opens a link you paste here. Open the job in your browser, select the whole posting, copy it
        and paste it below. LinkedIn forbids programs from reading its pages.
      </p>
      {open && (
        <div className="stack" style={{ marginTop: 12 }}>
          {search.data?.url && (
            <a className="btn" href={search.data.url} target="_blank" rel="noreferrer noopener">
              Search these keywords on LinkedIn
            </a>
          )}
          <Field label="Job posting" help="Paste the whole posting: title, company, location and description.">
            <textarea
              value={form.text}
              onChange={(event) => setForm({ ...form, text: event.target.value })}
              placeholder="Paste here"
            />
          </Field>
          <Field label="Job link (optional)" help="Stored so you can open the job later. The app does not visit it.">
            <input
              type="url"
              value={form.url}
              placeholder="https://www.linkedin.com/jobs/view/..."
              onChange={(event) => setForm({ ...form, url: event.target.value })}
            />
          </Field>
          <div className="grid3">
            <Field label="Title (optional)" help="Left empty, the first line is used.">
              <input type="text" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
            </Field>
            <Field label="Company (optional)" help="Left empty, read from the posting.">
              <input
                type="text"
                value={form.company}
                onChange={(event) => setForm({ ...form, company: event.target.value })}
              />
            </Field>
            <Field label="Location (optional)">
              <input
                type="text"
                value={form.location}
                onChange={(event) => setForm({ ...form, location: event.target.value })}
              />
            </Field>
          </div>
          <div className="row">
            <button type="button" onClick={() => void add()} disabled={busy}>
              Add job
            </button>
          </div>
        </div>
      )}
      {note && (
        <div style={{ marginTop: 10 }}>
          <Notice tone={tone}>{note}</Notice>
        </div>
      )}
    </Panel>
  );
}

function Housekeeping({ onChanged }: { onChanged: () => void }) {
  const { resumeId } = useApp();
  const [days, setDays] = useState(30);
  const [sure, setSure] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, tone, flash] = useFlash();
  const summary = useLoad<{ stale: number; kept: number }>(() => get("/housekeeping/stale", { days }), [days]);

  async function grab(kind: "jobs" | "matches") {
    try {
      const params = kind === "matches" && resumeId ? `?resume_id=${resumeId}` : "";
      await download(`/housekeeping/backup/${kind}${params}`, undefined, `jobhunt-${kind}.csv`);
    } catch (exc) {
      flash(message(exc), "bad");
    }
  }

  async function clean() {
    setBusy(true);
    try {
      const result = await del<{ deleted: number }>("/housekeeping/stale", { days });
      flash(`Deleted ${result.deleted} jobs older than ${days} days.`);
      setSure(false);
      summary.reload();
      onChanged();
    } catch (exc) {
      flash(message(exc), "bad");
    } finally {
      setBusy(false);
    }
  }

  const stale = summary.data?.stale ?? 0;
  const kept = summary.data?.kept ?? 0;

  return (
    <Panel title="Back up or clean up stored jobs">
      <div className="stack">
        <div>
          <p style={{ fontWeight: 500 }}>Back up</p>
          <p className="hint">
            Download your stored jobs and scores as spreadsheets. python scripts/housekeeping.py backup also copies
            the whole database.
          </p>
          <div className="row" style={{ marginTop: 8 }}>
            <button type="button" onClick={() => void grab("jobs")}>
              Download jobs.csv
            </button>
            <button type="button" onClick={() => void grab("matches")} disabled={!resumeId}>
              Download matches.csv
            </button>
          </div>
        </div>
        <hr className="divider" />
        <div>
          <p style={{ fontWeight: 500 }}>Clean up</p>
          <Field
            label="Delete jobs older than (days)"
            help="Age is counted from the posting date, or from when the job was collected if the posting has no date."
          >
            <input
              type="number"
              min={7}
              max={365}
              value={days}
              onChange={(event) => setDays(Number(event.target.value) || 30)}
            />
          </Field>
          <p className="hint" style={{ marginTop: 8 }}>
            {stale
              ? `${stale} jobs are older than ${days} days and would be deleted with their scores.`
              : `No jobs are older than ${days} days.`}
            {kept ? ` ${kept} older jobs stay because you saved, applied to or wrote for them.` : ""}
          </p>
          {stale > 0 && (
            <>
              <p className="hint">This cannot be undone, so back up first if you may want them.</p>
              <label className="check">
                <input type="checkbox" checked={sure} onChange={(event) => setSure(event.target.checked)} />
                <span>Yes, delete {countLabel(stale, "old job")}</span>
              </label>
              <button type="button" onClick={() => void clean()} disabled={!sure || busy}>
                Delete {countLabel(stale, "old job")}
              </button>
            </>
          )}
        </div>
        {note && <Notice tone={tone}>{note}</Notice>}
      </div>
    </Panel>
  );
}

function clock(epochSeconds: number): string {
  const when = new Date(epochSeconds * 1000);
  return Number.isNaN(when.getTime())
    ? ""
    : when.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}
