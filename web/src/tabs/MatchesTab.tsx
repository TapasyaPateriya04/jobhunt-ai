/* Matches tab: the ranked list on the left, the job you picked on the right. */
import { useEffect, useMemo, useState } from "react";

import { get, patch, post } from "../api";
import type { Catalog, LearnList, Match, MatchDetail, MatchList } from "../api";
import {
  Bars,
  Chips,
  CountBars,
  Empty,
  Field,
  Meta,
  Notice,
  OpenPosting,
  Panel,
  Posting,
  Score,
  Skeleton,
  Working,
} from "../components/ui";
import { countLabel, Icon } from "../components/ui";
import { message, plural, timeAgo, useFlash, useLoad } from "../hooks";
import { useApp } from "../state";

const ANY_YEARS = 15; // top of the years slider: no limit
const ALL = "All";
const BLOCKED = ["restricted", "elsewhere"];

type Filters = {
  query: string;
  minScore: number;
  maxYears: number;
  onlyTakeable: boolean;
  keepUnknownYears: boolean;
  source: string;
  status: string;
  sort: string;
};

function defaults(years: number, hasCountry: boolean): Filters {
  return {
    query: "",
    minScore: 0,
    maxYears: Math.min(ANY_YEARS, Math.ceil(years) + 2),
    onlyTakeable: hasCountry,
    keepUnknownYears: true,
    source: ALL,
    status: ALL,
    sort: "Best match",
  };
}

export function MatchesTab() {
  const { resume, resumeId, catalog, country, setCountry, reload } = useApp();
  const [scoring, setScoring] = useState(false);
  const [note, tone, flash] = useFlash();
  const [picked, setPicked] = useState<number | null>(null);
  const [filters, setFilters] = useState<Filters | null>(null);

  const countries = useLoad<{ countries: string[]; configured: string }>(() => get("/countries"), []);
  const matches = useLoad<MatchList>(
    () => get("/matches", { resume_id: resumeId, country: country ?? "" }),
    [resumeId, country],
    Boolean(resumeId),
  );

  const years = matches.data?.candidate_years ?? 0;
  useEffect(() => {
    if (!filters && matches.data) setFilters(defaults(years, Boolean(country)));
  }, [matches.data, filters, years, country]);

  async function score() {
    if (!resumeId) return;
    setScoring(true);
    try {
      const result = await post<{ scored: number }>(`/resume/${resumeId}/score`, undefined, {
        country: country ?? "",
      });
      flash(
        result.scored
          ? `Scored ${result.scored} jobs against your resume. The best matches are listed first.`
          : "No jobs to score yet. Collect some on the Find jobs tab first.",
        result.scored ? "ok" : "warn",
      );
      matches.reload();
      reload();
    } catch (exc) {
      flash(message(exc), "bad");
    } finally {
      setScoring(false);
    }
  }

  if (!resume || !resumeId) {
    return (
      <Empty
        icon="file"
        title="Add your resume first"
        hint="Matches are scored against your resume. Upload it on the Resume tab."
      />
    );
  }

  const all = matches.data?.matches ?? [];
  const shown = filters ? sortMatches(all.filter((m) => keep(m, filters, Boolean(country))), filters.sort) : [];
  const selected = shown.find((m) => m.id === picked) ?? shown[0] ?? null;

  return (
    <>
      <Panel title="Where you can work">
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ flex: "1 1 240px" }}>
            <Field
              label="Your country"
              help="Jobs restricted to other countries, time zones or languages are ranked down. CANDIDATE_COUNTRY in .env sets the default."
            >
              <select value={country ?? ""} onChange={(event) => setCountry(event.target.value)}>
                <option value="">Ignore location</option>
                {(countries.data?.countries ?? []).map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <button type="button" className="primary" onClick={() => void score()} disabled={scoring}>
            Score stored jobs
          </button>
        </div>
        {scoring && (
          <div style={{ marginTop: 12 }}>
            <Working text="Comparing your resume with every stored job. The first run loads the model, which can take a minute." />
          </div>
        )}
        {note && (
          <div style={{ marginTop: 12 }}>
            <Notice tone={tone}>{note}</Notice>
          </div>
        )}
      </Panel>

      {matches.loading && !matches.data ? (
        <Skeleton rows={4} />
      ) : matches.error ? (
        <Notice tone="bad">{matches.error}</Notice>
      ) : !all.length ? (
        <Empty
          icon="search"
          title="No matches yet"
          hint="Collect jobs on the Find jobs tab, then press Score stored jobs above."
        />
      ) : (
        <>
          {filters && catalog && (
            <FilterPanel
              filters={filters}
              setFilters={setFilters}
              catalog={catalog}
              data={matches.data!}
              hasCountry={Boolean(country)}
              onReset={() => setFilters(defaults(years, Boolean(country)))}
            />
          )}

          <SummaryStrip all={all} shown={shown} filters={filters} country={country ?? ""} />

          {!shown.length ? (
            <Empty
              icon="filter"
              title="No jobs pass these filters"
              hint="Clear the search, raise the years limit or lower the minimum confidence. Reset filters puts everything back."
            />
          ) : (
            <>
              <Charts shown={shown} />
              <div className="split">
                <div className="joblist">
                  {shown.map((match) => (
                    <JobRow
                      key={match.id}
                      match={match}
                      selected={selected?.id === match.id}
                      onPick={() => setPicked(match.id)}
                    />
                  ))}
                </div>
                <div className="detail">
                  {selected && (
                    <Detail
                      match={selected}
                      onChanged={() => {
                        matches.reload();
                        reload();
                      }}
                    />
                  )}
                </div>
              </div>
            </>
          )}

          <SkillsToLearn />
        </>
      )}
    </>
  );
}

function keep(m: Match, f: Filters, hasCountry: boolean): boolean {
  if (m.score < f.minScore) return false;
  const words = f.query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length) {
    const hay = [m.title, m.company, m.location, m.gap.required.join(" ")].join(" ").toLowerCase();
    if (!words.every((word) => hay.includes(word))) return false;
  }
  if (hasCountry && f.onlyTakeable && BLOCKED.includes(m.location_status)) return false;
  if (f.source !== ALL && m.source !== f.source) return false;
  if (f.status !== ALL ? m.status !== f.status : m.status === "hidden") return false;
  if (m.years === null) return f.keepUnknownYears;
  return f.maxYears >= ANY_YEARS || m.years <= f.maxYears;
}

function sortMatches(rows: Match[], how: string): Match[] {
  const byScore = (a: Match, b: Match) => b.score - a.score;
  const copy = [...rows];
  if (how === "Fewest missing skills") {
    return copy.sort(
      (a, b) =>
        Number(a.gap.required.length < 3) - Number(b.gap.required.length < 3) ||
        a.gap.missing.length - b.gap.missing.length ||
        byScore(a, b),
    );
  }
  if (how === "Newest posting") {
    const at = (m: Match) => (m.posted_date ? new Date(m.posted_date).getTime() : -Infinity);
    return copy.sort((a, b) => at(b) - at(a) || byScore(a, b));
  }
  if (how === "Least experience asked") {
    return copy.sort(
      (a, b) =>
        Number(a.years === null) - Number(b.years === null) || (a.years ?? 0) - (b.years ?? 0) || byScore(a, b),
    );
  }
  return copy.sort(byScore);
}

function FilterPanel({
  filters,
  setFilters,
  catalog,
  data,
  hasCountry,
  onReset,
}: {
  filters: Filters;
  setFilters: (f: Filters) => void;
  catalog: Catalog;
  data: MatchList;
  hasCountry: boolean;
  onReset: () => void;
}) {
  const set = <K extends keyof Filters,>(key: K, value: Filters[K]) => setFilters({ ...filters, [key]: value });
  return (
    <Panel
      title="Filters"
      action={
        <button type="button" className="quiet small" onClick={onReset}>
          Reset filters
        </button>
      }
    >
      <div className="stack">
        <Field
          label="Search"
          help="Every word you type must appear in the job's title, company, location or required skills."
        >
          <input
            type="text"
            value={filters.query}
            placeholder="Spring Boot Bangalore"
            onChange={(event) => set("query", event.target.value)}
          />
        </Field>
        <div className="grid2">
          <Field
            label={`Minimum confidence: ${filters.minScore}`}
            help="50 and above is a strong match, 35 to 49 a possible one."
          >
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={filters.minScore}
              onChange={(event) => set("minScore", Number(event.target.value))}
            />
          </Field>
          <Field
            label={
              filters.maxYears >= ANY_YEARS
                ? "Asks for at most: any number of years"
                : `Asks for at most ${filters.maxYears} ${plural(filters.maxYears, "year")}`
            }
            help={`Your resume shows about ${data.candidate_years} years. ${ANY_YEARS} shows every level.`}
          >
            <input
              type="range"
              min={0}
              max={ANY_YEARS}
              step={1}
              value={filters.maxYears}
              onChange={(event) => set("maxYears", Number(event.target.value))}
            />
          </Field>
        </div>
        <div className="grid2">
          <label className="check">
            <input
              type="checkbox"
              checked={filters.onlyTakeable && hasCountry}
              disabled={!hasCountry}
              onChange={(event) => set("onlyTakeable", event.target.checked)}
            />
            <span>
              Only jobs I can take
              <br />
              <span className="hint">
                {hasCountry
                  ? "Hides jobs on site in another country or restricted to other countries, time zones or languages."
                  : "Pick your country above to use this."}
              </span>
            </span>
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={filters.keepUnknownYears}
              onChange={(event) => set("keepUnknownYears", event.target.checked)}
            />
            <span>Include jobs that state no years</span>
          </label>
        </div>
        <div className="grid3">
          <Field label="Source">
            <select value={filters.source} onChange={(event) => set("source", event.target.value)}>
              <option value={ALL}>{ALL}</option>
              {data.sources.map((key) => (
                <option key={key} value={key}>
                  {data.source_names[key] ?? key}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Status" help="All leaves out hidden jobs.">
            <select value={filters.status} onChange={(event) => set("status", event.target.value)}>
              <option value={ALL}>{ALL}</option>
              {catalog.statuses.map((status) => (
                <option key={status.key} value={status.key}>
                  {status.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Sort by">
            <select value={filters.sort} onChange={(event) => set("sort", event.target.value)}>
              {catalog.sorts.map((sort) => (
                <option key={sort} value={sort}>
                  {sort}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </div>
    </Panel>
  );
}

function SummaryStrip({
  all,
  shown,
  filters,
  country,
}: {
  all: Match[];
  shown: Match[];
  filters: Filters | null;
  country: string;
}) {
  const hidden = all.filter((m) => m.status === "hidden").length;
  const near = shown.filter((m) => m.near_miss).length;
  return (
    <div className="row tight" style={{ fontSize: "0.85rem" }}>
      <span>
        <b style={{ fontFamily: "var(--mono)" }}>{shown.length}</b> of {all.length} jobs
      </span>
      {country && filters?.onlyTakeable && <span className="badge accent">{country} or remote</span>}
      {filters && filters.maxYears < ANY_YEARS && (
        <span className="badge">up to {countLabel(filters.maxYears, "year")}</span>
      )}
      {filters?.query && <span className="badge">matching "{filters.query.slice(0, 40)}"</span>}
      {near > 0 && (
        <span className="muted">
          <b style={{ fontFamily: "var(--mono)" }}>{near}</b> within 3 skills of a full match
        </span>
      )}
      {hidden > 0 && <span className="muted">{hidden} hidden (Status: Hidden shows them)</span>}
    </div>
  );
}

function Charts({ shown }: { shown: Match[] }) {
  const { catalog } = useApp();
  const bands = (catalog?.bands ?? []).map((band, i, list) => {
    const upper = i === 0 ? 101 : list[i - 1].min;
    const label = i === 0 ? `${band.label} (${band.min}+)` : `${band.label} (${band.min} to ${upper - 1})`;
    return [label, shown.filter((m) => m.score >= band.min && m.score < upper).length] as [string, number];
  });
  const perSource = new Map<string, number>();
  const wanted = new Map<string, number>();
  const have = new Set<string>();
  for (const match of shown) {
    const name = match.source_name || "Unknown";
    perSource.set(name, (perSource.get(name) ?? 0) + 1);
    match.gap.matched.forEach((skill) => have.add(skill));
    for (const skill of match.gap.required) wanted.set(skill, (wanted.get(skill) ?? 0) + 1);
  }
  const skills = [...wanted.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 8)
    .map(([name, n]) => [have.has(name) ? name : `${name} (missing)`, n] as [string, number]);

  return (
    <Panel title="The jobs shown at a glance">
      <div className="grid3">
        <div>
          <h4 style={{ marginBottom: 8 }}>Match strength</h4>
          <CountBars rows={bands} />
        </div>
        <div>
          <h4 style={{ marginBottom: 8 }}>Where they came from</h4>
          <CountBars rows={[...perSource.entries()].sort((a, b) => b[1] - a[1])} />
        </div>
        <div>
          <h4 style={{ marginBottom: 8 }}>Skills asked for most</h4>
          {skills.length ? (
            <CountBars rows={skills} note="Skills marked (missing) are not on your resume." />
          ) : (
            <p className="hint">These postings name no skills the app recognises.</p>
          )}
        </div>
      </div>
    </Panel>
  );
}

function JobRow({ match, selected, onPick }: { match: Match; selected: boolean; onPick: () => void }) {
  return (
    <button type="button" className="jobrow" aria-current={selected} onClick={onPick}>
      <span className="head">
        <span>
          <span className="title">{match.title}</span>
          <br />
          <Meta
            parts={[
              match.company,
              match.location,
              timeAgo(match.posted_date),
              match.source_name,
              match.years !== null ? `asks ${countLabel(match.years, "year")}` : null,
            ]}
          />
        </span>
        <Score value={match.score} band={match.band} label={match.band_label} />
      </span>
      <span className="row tight">
        {match.status !== "new" && <span className="badge accent">{statusLabel(match.status)}</span>}
        {match.location_ok === false && (
          <span className="badge bad">
            <Icon name="alert" size={12} />
            {match.location_text || "Not open to you"}
          </span>
        )}
        {match.near_miss && (
          <span className="badge ok">
            {countLabel(match.gap.missing.length, "skill")} short of a full match
          </span>
        )}
      </span>
      {match.gap.matched.length + match.gap.missing.length > 0 && (
        <span className="row tight">
          <Chips items={match.gap.matched.slice(0, 4)} kind="ok" empty={null} />
          <Chips items={match.gap.missing.slice(0, 4)} kind="miss" empty={null} />
        </span>
      )}
    </button>
  );
}

function statusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function Detail({ match, onChanged }: { match: Match; onChanged: () => void }) {
  const { resumeId, catalog, model, setTab, writeDocumentsFor } = useApp();
  const [note, tone, flash] = useFlash();
  const [busy, setBusy] = useState(false);
  const [showPosting, setShowPosting] = useState(false);
  const [llmRequirements, setLlmRequirements] = useState<MatchDetail["requirements"] | null>(null);
  const detail = useLoad<MatchDetail>(
    () => get(`/matches/${match.id}`, { resume_id: resumeId }),
    [match.id, resumeId],
    Boolean(resumeId),
  );

  useEffect(() => {
    setLlmRequirements(null);
    setShowPosting(false);
  }, [match.id]);

  const parts = useMemo(
    () =>
      (catalog?.score_parts ?? []).map((part) => ({
        label: part.label,
        value: match.parts[part.key] ?? null,
        about: part.about,
      })),
    [catalog, match],
  );

  async function setStatus(status: string) {
    setBusy(true);
    try {
      const result = await patch<{ message: string }>(`/matches/${match.id}/status`, { status });
      flash(result.message);
      onChanged();
    } catch (exc) {
      flash(message(exc), "bad");
    } finally {
      setBusy(false);
    }
  }

  async function recheck() {
    setBusy(true);
    try {
      const result = await post<MatchDetail["requirements"]>(
        `/matches/${match.id}/requirements`,
        undefined,
        { resume_id: resumeId ?? "", model: model ?? "" },
      );
      setLlmRequirements(result);
    } catch (exc) {
      flash(message(exc), "warn");
    } finally {
      setBusy(false);
    }
  }

  const requirements = llmRequirements ?? detail.data?.requirements;
  const have = new Set((detail.data?.have ?? []).map((s) => s.toLowerCase()));
  const split = (skills: string[]) => ({
    known: skills.filter((s) => have.has(s.toLowerCase())),
    missing: skills.filter((s) => !have.has(s.toLowerCase())),
  });

  return (
    <div className="stack">
      <Panel>
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h3>{match.title}</h3>
            <Meta parts={[match.company, match.location, timeAgo(match.posted_date), match.source_name]} />
          </div>
          <Score value={match.score} band={match.band} label={match.band_label} />
        </div>
        <div className="row tight" style={{ marginTop: 10 }}>
          {match.location_text && (
            <span className={`badge${match.location_ok === false ? " bad" : match.location_ok ? " ok" : ""}`}>
              {match.location_text}
            </span>
          )}
          {match.years !== null && <span className="badge">asks {countLabel(match.years, "year")}</span>}
          {match.status !== "new" && <span className="badge accent">{statusLabel(match.status)}</span>}
        </div>
        <hr className="divider" />
        <div className="row tight">
          <button
            type="button"
            className={match.status === "saved" ? "" : "primary"}
            disabled={busy}
            onClick={() => void setStatus(match.status === "saved" ? "new" : "saved")}
          >
            {match.status === "saved" ? "Unsave" : "Save"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void setStatus(match.status === "hidden" ? "new" : "hidden")}
          >
            {match.status === "hidden" ? "Unhide" : "Hide"}
          </button>
          <button
            type="button"
            onClick={() => {
              writeDocumentsFor(match.id);
              setTab("documents");
            }}
          >
            Write documents
          </button>
          <OpenPosting url={match.url} />
        </div>
        <div className="row tight" style={{ marginTop: 8 }}>
          <Field label="Status">
            <select
              value={match.status}
              disabled={busy}
              onChange={(event) => void setStatus(event.target.value)}
            >
              {(catalog?.statuses ?? []).map((status) => (
                <option key={status.key} value={status.key}>
                  {status.label}
                </option>
              ))}
            </select>
          </Field>
        </div>
        {note && (
          <div style={{ marginTop: 10 }}>
            <Notice tone={tone}>{note}</Notice>
          </div>
        )}
      </Panel>

      <Panel title="How this score was worked out">
        <Bars parts={parts} note={catalog?.score_note} />
      </Panel>

      {requirements && (requirements.must_have.length > 0 || requirements.nice_to_have.length > 0) && (
        <Panel title="What the posting asks for">
          <div className="grid2">
            {(
              [
                ["Must have", requirements.must_have],
                ["Nice to have", requirements.nice_to_have],
              ] as [string, string[]][]
            ).map(([title, skills]) => {
              const group = split(skills);
              return (
                <div key={title}>
                  <h4 style={{ marginBottom: 6 }}>{title}</h4>
                  <div className="stack">
                    <Chips items={group.known} kind="ok" empty={null} />
                    <Chips items={group.missing} kind="miss" empty={null} />
                    {!skills.length && <p className="hint">None found.</p>}
                  </div>
                </div>
              );
            })}
          </div>
          <p className="hint" style={{ marginTop: 10 }}>
            A tick means the skill is on your resume, a cross means it is missing. Split by{" "}
            {requirements.source === "llm" ? "the language model" : "keyword rules"}.
          </p>
          {requirements.source !== "llm" && (
            <button type="button" className="small" onClick={() => void recheck()} disabled={busy}>
              Re-check with the language model
            </button>
          )}
        </Panel>
      )}

      {detail.data && (detail.data.keywords.matched.length > 0 || detail.data.keywords.missing.length > 0) && (
        <Panel title="Keywords">
          <div className="grid2">
            <div>
              <h4 style={{ marginBottom: 6 }}>On your resume</h4>
              <Chips items={detail.data.keywords.matched} kind="ok" />
            </div>
            <div>
              <h4 style={{ marginBottom: 6 }}>Missing</h4>
              <Chips items={detail.data.keywords.missing} kind="miss" />
            </div>
          </div>
        </Panel>
      )}

      {match.has_description && (
        <Panel
          title="The posting"
          action={
            <button type="button" className="quiet small" onClick={() => setShowPosting(!showPosting)}>
              {showPosting ? "Hide" : "Show"}
            </button>
          }
        >
          {showPosting ? (
            detail.data ? (
              <Posting text={detail.data.description} />
            ) : (
              <Skeleton rows={1} />
            )
          ) : (
            <p className="hint">{match.snippet}</p>
          )}
        </Panel>
      )}
    </div>
  );
}

function SkillsToLearn() {
  const { resumeId, country } = useApp();
  const learn = useLoad<LearnList>(
    () => get("/skills-to-learn", { resume_id: resumeId, country: country ?? "" }),
    [resumeId, country],
    Boolean(resumeId),
  );
  if (!learn.data) return null;
  const { skills, jobs, near_count } = learn.data;
  return (
    <Panel title="Skills worth adding">
      {!near_count ? (
        <p className="hint">
          No scored job is within 3 skills of a full match yet. Collect more postings, or raise the years limit.
        </p>
      ) : (
        <div className="stack">
          <p className="hint">
            {near_count} scored {plural(near_count, "job is", "jobs are")} only 1 to 3 skills short. These come up
            most in them:
          </p>
          <Chips
            items={skills.map((s) => `${s.skill} (${countLabel(s.jobs, "job")})`)}
            kind="miss"
            empty="None found."
          />
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {jobs.map((job) => (
              <li key={job.id}>
                <span style={{ fontWeight: 500 }}>{job.title}</span> at {job.company}: add{" "}
                <span style={{ fontWeight: 500 }}>{job.missing.join(", ")}</span> (you have {job.matched} of{" "}
                {job.required})
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}
