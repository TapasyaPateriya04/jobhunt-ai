/* Documents tab: draft a cover letter or resume suggestions for one job, edit the
   draft, check the claims it makes, then download or save it. */
import { useEffect, useRef, useState } from "react";

import { download, get, post, saveText, streamDraft } from "../api";
import type { DraftableJob, ExportFormat, FactFlag, SavedDocument } from "../api";
import { countLabel, Empty, Field, Meta, Notice, Panel, Skeleton } from "../components/ui";
import { message, timeAgo, useFlash, useLoad } from "../hooks";
import { useApp } from "../state";

export function DocumentsTab() {
  const { resume, resumeId, catalog, model, writeFor, writeDocumentsFor } = useApp();
  const [matchId, setMatchId] = useState<number | null>(null);
  const [docType, setDocType] = useState("cover_letter");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [streaming, setStreaming] = useState(false);
  const [flags, setFlags] = useState<FactFlag[] | null>(null);
  const [note, tone, flash] = useFlash();
  const abort = useRef<AbortController>();

  const jobs = useLoad<{ jobs: DraftableJob[] }>(
    () => get("/documents/jobs", { resume_id: resumeId }),
    [resumeId],
    Boolean(resumeId),
    `documents-jobs:${resumeId}`,
  );
  const writer = useLoad<{ ready: boolean; note: string }>(
    () => get("/documents/writer", { model: model ?? "" }),
    [model],
  );
  const formats = useLoad<{ formats: ExportFormat[] }>(() => get("/documents/export-formats"), []);
  const saved = useLoad<{ documents: SavedDocument[] }>(
    () => get("/documents", { match_id: matchId }),
    [matchId],
    Boolean(matchId),
  );

  const list = jobs.data?.jobs ?? [];
  // A Write documents button on another tab picks the job here.
  useEffect(() => {
    if (writeFor && list.some((job) => job.id === writeFor)) {
      setMatchId(writeFor);
      writeDocumentsFor(null);
    } else if (matchId === null && list.length) {
      setMatchId(list[0].id);
    }
  }, [writeFor, list, matchId, writeDocumentsFor]);

  const job = list.find((entry) => entry.id === matchId) ?? null;
  const key = `${matchId}-${docType}`;
  const draft = drafts[key] ?? "";

  async function generate() {
    if (!matchId) return;
    abort.current?.abort();
    abort.current = new AbortController();
    setStreaming(true);
    setFlags(null);
    setDrafts((current) => ({ ...current, [key]: "" }));
    try {
      const all = await streamDraft(
        { match_id: matchId, doc_type: docType, model },
        (text) => setDrafts((current) => ({ ...current, [key]: (current[key] ?? "") + text })),
        abort.current.signal,
      );
      const tidied = await post<{ content: string }>("/documents/tidy", {
        match_id: matchId,
        doc_type: docType,
        content: all,
      });
      setDrafts((current) => ({ ...current, [key]: tidied.content }));
      if (tidied.content.trim()) {
        flash("Draft ready. Edit it below, then download or save it.");
        void check(tidied.content);
      } else {
        flash("The language model returned an empty draft. Press Generate to try again.", "warn");
      }
    } catch (exc) {
      if (!(exc instanceof DOMException && exc.name === "AbortError")) flash(message(exc), "warn");
    } finally {
      setStreaming(false);
    }
  }

  async function check(content: string) {
    if (!matchId || !content.trim()) return;
    try {
      const result = await post<{ flags: FactFlag[] }>("/documents/check", {
        match_id: matchId,
        doc_type: docType,
        content,
        resume_id: resumeId,
      });
      setFlags(result.flags);
    } catch {
      setFlags(null);
    }
  }

  async function keep() {
    if (!matchId) return;
    try {
      const result = await post<{ path: string }>("/documents/save", {
        match_id: matchId,
        doc_type: docType,
        content: draft,
      });
      flash(`Saved to ${result.path}. It is also listed below.`);
      saved.reload();
    } catch (exc) {
      flash(message(exc), "bad");
    }
  }

  async function grab(kind: string) {
    const label = catalog?.doc_types.find((t) => t.key === docType)?.label ?? docType;
    const stem = `${docType}_${(job?.company ?? "job").replace(/[^A-Za-z0-9]/g, "").slice(0, 40) || "job"}`;
    if (kind === "txt") {
      saveText(draft, `${stem}.txt`);
      return;
    }
    try {
      await download(
        "/documents/export",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: draft, title: `${label}: ${job?.title} at ${job?.company}`, kind }),
        },
        `${stem}.${kind}`,
      );
    } catch (exc) {
      flash(message(exc), "bad");
    }
  }

  if (!resume || !resumeId) {
    return (
      <Empty
        icon="file"
        title="Add your resume first"
        hint="Cover letters and resume suggestions are written from your resume."
      />
    );
  }
  if (jobs.loading && !jobs.data) return <Skeleton rows={2} />;
  if (!list.length) {
    return (
      <Empty
        icon="search"
        title="No matches to write for yet"
        hint="Score some jobs on the Matches tab, then come back to draft a cover letter."
      />
    );
  }

  return (
    <>
      <Panel title="Which job">
        <div className="stack">
          <Field label="Job" help="Saved and applied jobs are listed first, then the rest by match score.">
            <select value={matchId ?? ""} onChange={(event) => setMatchId(Number(event.target.value))}>
              {list.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.status !== "new" ? `[${entry.status_label}] ` : ""}
                  {Math.round(entry.score)} - {entry.title} at {entry.company}
                </option>
              ))}
            </select>
          </Field>
          {job && (
            <Meta
              parts={[
                job.location,
                `score ${Math.round(job.score)} (${job.band_label.toLowerCase()})`,
                timeAgo(job.posted_date),
                job.source_name,
              ]}
            />
          )}
          <div className="tabs" role="tablist" aria-label="Which document to write">
            {(catalog?.doc_types ?? []).map((type) => (
              <button
                type="button"
                role="tab"
                key={type.key}
                aria-selected={docType === type.key}
                onClick={() => setDocType(type.key)}
              >
                {type.label}
              </button>
            ))}
          </div>
          <div className="row">
            <button
              type="button"
              className="primary"
              onClick={() => void generate()}
              disabled={streaming || !writer.data?.ready}
            >
              {draft ? "Generate again" : "Generate"}
            </button>
            {streaming && (
              <button type="button" onClick={() => abort.current?.abort()}>
                Stop
              </button>
            )}
            <span className="hint">{writer.data?.note}</span>
          </div>
          {!writer.data?.ready && (
            <Notice tone="warn">
              No language model is ready. Start Ollama, or connect a Gemini API key.
            </Notice>
          )}
          {note && <Notice tone={tone}>{note}</Notice>}
        </div>
      </Panel>

      {(draft || streaming) && (
        <Panel
          title={streaming ? "Writing..." : "Edit before saving"}
          count={draft ? countLabel(draft.trim().split(/\s+/).filter(Boolean).length, "word") : undefined}
        >
          <div className="stack">
            <textarea
              value={draft}
              aria-label="The draft"
              style={{ minHeight: 360, fontSize: "0.95rem" }}
              onChange={(event) => setDrafts((current) => ({ ...current, [key]: event.target.value }))}
              onBlur={() => void check(draft)}
            />
            <p className="hint">Changes you type here go into the files you download.</p>
            {flags !== null &&
              (flags.length ? (
                <Notice tone="warn">
                  <p style={{ fontWeight: 600 }}>
                    Check {countLabel(flags.length, "sentence")} before you send this. They may claim more than
                    your resume shows.
                  </p>
                  <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                    {flags.map((flag, i) => (
                      <li key={i}>
                        <em>{flag.sentence}</em>
                        <br />
                        <span className="hint">{flag.why}</span>
                      </li>
                    ))}
                  </ul>
                </Notice>
              ) : (
                <p className="hint">
                  No claims found that go beyond your resume. Still read it once before you send it.
                </p>
              ))}
            <div className="row tight">
              <button type="button" onClick={() => void grab("txt")} disabled={!draft.trim()}>
                Download .txt
              </button>
              {(formats.data?.formats ?? []).map((format) => (
                <button
                  type="button"
                  key={format.kind}
                  onClick={() => void grab(format.kind)}
                  disabled={!draft.trim() || !format.available}
                  title={format.available ? undefined : format.reason}
                >
                  Download .{format.kind}
                </button>
              ))}
              <button type="button" onClick={() => void keep()} disabled={!draft.trim()}>
                Save to documents
              </button>
            </div>
          </div>
        </Panel>
      )}

      {saved.data && saved.data.documents.length > 0 && (
        <Panel title="Saved documents for this job" count={saved.data.documents.length}>
          <div className="stack">
            {saved.data.documents.map((doc) => (
              <div className="row" key={doc.id} style={{ justifyContent: "space-between" }}>
                <div>
                  <p style={{ fontWeight: 500 }}>{doc.label}</p>
                  <Meta parts={[when(doc.generated_at), countLabel(doc.words, "word")]} />
                </div>
                <div className="row tight">
                  <button
                    type="button"
                    className="small"
                    onClick={() => {
                      setDocType(doc.doc_type);
                      setDrafts((current) => ({ ...current, [`${matchId}-${doc.doc_type}`]: doc.content }));
                    }}
                  >
                    Open in the editor
                  </button>
                  <button
                    type="button"
                    className="small"
                    onClick={() => saveText(doc.content, `${doc.doc_type}_${doc.id}.txt`)}
                  >
                    Download .txt
                  </button>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}
    </>
  );
}

function when(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString(undefined, { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
