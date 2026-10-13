/* Applications tab: the jobs you saved, applied to or were turned down for. */
import { useState } from "react";

import { get, patch } from "../api";
import type { Match, MatchList } from "../api";
import { Empty, Meta, Notice, OpenPosting, Panel, Score, Skeleton } from "../components/ui";
import { message, timeAgo, useFlash, useLoad } from "../hooks";
import { useApp } from "../state";

const ALL = "all";

export function ApplicationsTab() {
  const { resume, resumeId, catalog, country, setTab, writeDocumentsFor, reload } = useApp();
  const [view, setView] = useState(ALL);
  const [note, tone, flash] = useFlash();
  const [busy, setBusy] = useState(false);
  const matches = useLoad<MatchList>(
    () => get("/matches", { resume_id: resumeId, country: country ?? "" }),
    [resumeId, country],
    Boolean(resumeId),
  );

  if (!resume || !resumeId) {
    return (
      <Empty
        icon="file"
        title="Add your resume first"
        hint="Applications are tracked per resume. Upload yours on the Resume tab."
      />
    );
  }
  if (matches.loading && !matches.data) return <Skeleton rows={3} />;
  if (matches.error) return <Notice tone="bad">{matches.error}</Notice>;

  const tracked = (catalog?.tracked_statuses ?? []).map((s) => s.key);
  const rows = (matches.data?.matches ?? []).filter((m) => tracked.includes(m.status));
  if (!rows.length) {
    return (
      <Empty
        icon="check"
        title="No applications tracked yet"
        hint="Press Save on a job in the Matches tab. It appears here, where you can mark it applied or rejected."
      />
    );
  }

  const counts = Object.fromEntries(tracked.map((s) => [s, rows.filter((m) => m.status === s).length]));
  const order = Object.fromEntries(tracked.map((s, i) => [s, i]));
  const shown = rows
    .filter((m) => view === ALL || m.status === view)
    .sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9) || b.score - a.score);

  async function setStatus(match: Match, status: string) {
    setBusy(true);
    try {
      const result = await patch<{ message: string }>(`/matches/${match.id}/status`, { status });
      flash(result.message);
      matches.reload();
      reload();
    } catch (exc) {
      flash(message(exc), "bad");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="stats">
        {(catalog?.tracked_statuses ?? []).map((status) => (
          <div key={status.key}>
            <b>{counts[status.key] ?? 0}</b>
            <span>
              {status.label.toLowerCase()}, {status.hint}
            </span>
          </div>
        ))}
      </div>

      <Panel title="Show">
        <div className="tabs" role="tablist" aria-label="Which applications to show">
          <button type="button" role="tab" aria-selected={view === ALL} onClick={() => setView(ALL)}>
            All <span className="tab-count">{rows.length}</span>
          </button>
          {(catalog?.tracked_statuses ?? []).map((status) => (
            <button
              type="button"
              role="tab"
              key={status.key}
              aria-selected={view === status.key}
              onClick={() => setView(status.key)}
            >
              {status.label} <span className="tab-count">{counts[status.key] ?? 0}</span>
            </button>
          ))}
        </div>
        {note && (
          <div style={{ marginTop: 10 }}>
            <Notice tone={tone}>{note}</Notice>
          </div>
        )}
      </Panel>

      {!shown.length ? (
        <Empty
          icon="filter"
          title="Nothing marked that way yet"
          hint="Pick All to see every tracked job, or change a job's status below."
        />
      ) : (
        <div className="joblist">
          {shown.map((match) => (
            <article className="jobrow" key={match.id}>
              <div className="head">
                <div>
                  <p className="title">{match.title}</p>
                  <Meta
                    parts={[match.company, match.location, timeAgo(match.posted_date), match.source_name]}
                  />
                </div>
                <Score value={match.score} band={match.band} label={match.band_label} />
              </div>
              <div className="row tight">
                <select
                  value={match.status}
                  disabled={busy}
                  aria-label={`Status of ${match.title}`}
                  onChange={(event) => void setStatus(match, event.target.value)}
                  style={{ width: "auto", minWidth: 160 }}
                >
                  {(catalog?.tracked_statuses ?? []).map((status) => (
                    <option key={status.key} value={status.key}>
                      {status.label}
                    </option>
                  ))}
                  <option value="new">Not tracked (back to new)</option>
                  <option value="hidden">Hidden</option>
                </select>
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
            </article>
          ))}
        </div>
      )}
    </>
  );
}
