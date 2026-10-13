/* Resume tab: upload a file, see what was read from it, add the skills it missed. */
import { useRef, useState } from "react";

import { post, uploadResume } from "../api";
import type { Resume } from "../api";
import { countLabel, Chips, Empty, Field, Notice, Panel, Working } from "../components/ui";
import { message, plural, useFlash } from "../hooks";
import { useApp } from "../state";

const ACCEPT = ".tex,.txt,.md,.pdf";

export function ResumeTab() {
  const { resume, resumeId, catalog, reload } = useApp();
  const [busy, setBusy] = useState("");
  const [note, tone, flash] = useFlash();
  const fileInput = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  async function send(file: File | undefined) {
    if (!file) return;
    const limit = catalog?.upload_max_bytes ?? 2_000_000;
    if (file.size > limit) {
      flash(`That file is ${Math.round(file.size / 1000)} kB. The limit is ${Math.round(limit / 1000)} kB.`, "bad");
      return;
    }
    setBusy("Reading your resume and scoring your stored jobs against it...");
    try {
      const result = await uploadResume(file, resumeId);
      const found = `${countLabel(result.resume.skill_count, "skill")} found`;
      const tail = result.score_error
        ? result.score_error
        : result.scored
          ? `${result.scored} stored ${result.scored === 1 ? "job was" : "jobs were"} scored against it, so Matches is up to date.`
          : "Next, open Find jobs to collect postings.";
      flash(`${resume ? "Resume updated" : "Resume saved"}: ${found}. ${tail}`, result.score_error ? "warn" : "ok");
      reload();
    } catch (exc) {
      flash(message(exc), "bad");
    } finally {
      setBusy("");
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <>
      <Panel title={resume ? "Upload a newer version" : "Upload your resume"}>
        <div
          className={`file-drop${over ? " over" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(event) => {
            event.preventDefault();
            setOver(false);
            void send(event.dataTransfer.files[0]);
          }}
        >
          <p style={{ fontWeight: 500 }}>Drop your resume here, or choose a file</p>
          <p className="hint" style={{ maxWidth: "48ch" }}>
            LaTeX (.tex), plain text (.txt), Markdown (.md) or PDF, up to{" "}
            {Math.round((catalog?.upload_max_bytes ?? 2_000_000) / 1_000_000)} MB. A new version replaces the one
            in use, keeps the skills you added by hand and scores your stored jobs against it.
          </p>
          <button type="button" className="primary" onClick={() => fileInput.current?.click()} disabled={Boolean(busy)}>
            Choose a file
          </button>
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPT}
            aria-label="Resume file"
            onChange={(event) => void send(event.target.files?.[0])}
          />
        </div>
        {busy && (
          <div style={{ marginTop: 12 }}>
            <Working text={busy} />
          </div>
        )}
        {note && (
          <div style={{ marginTop: 12 }}>
            <Notice tone={tone}>{note}</Notice>
          </div>
        )}
      </Panel>

      {!resume ? (
        <Empty
          icon="file"
          title="No resume yet"
          hint="Upload your resume above. It is read on this machine and never sent anywhere."
        />
      ) : (
        <ResumeDetail resume={resume} />
      )}
    </>
  );
}

function ResumeDetail({ resume }: { resume: Resume }) {
  const { reload } = useApp();
  const [typed, setTyped] = useState("");
  const [saving, setSaving] = useState(false);
  const [note, tone, flash] = useFlash();

  async function change(body: { add?: string; remove?: string }) {
    setSaving(true);
    try {
      const result = await post<{ added: string[]; removed: string | null }>(
        `/resume/${resume.id}/skills`,
        body,
      );
      if (result.added.length) {
        flash(`Added ${result.added.join(", ")}. Press Score stored jobs on the Matches tab to update the scores.`);
        setTyped("");
      } else if (result.removed) {
        flash(`Removed ${result.removed}. Press Score stored jobs on the Matches tab to update the scores.`);
      } else if (body.add?.trim()) {
        flash("That skill is already on your list.", "info");
      } else {
        flash("Type a skill first.", "warn");
      }
      reload();
    } catch (exc) {
      flash(message(exc), "bad");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="stats">
        <div>
          <b>{resume.skill_count}</b>
          <span>{plural(resume.skill_count, "skill")}</span>
        </div>
        <div>
          <b>{resume.experience_count}</b>
          <span>{plural(resume.experience_count, "experience entry", "experience entries")}</span>
        </div>
        <div>
          <b>{resume.years}</b>
          <span>years of experience read</span>
        </div>
      </div>

      {resume.summary && (
        <Panel title="Summary">
          <p>{resume.summary}</p>
        </Panel>
      )}

      <Panel title="Skills" count={resume.skill_count}>
        <Chips items={resume.skills} empty="No skills were read from the file. Add them below." />
        {resume.extra_skills.length > 0 && (
          <>
            <p className="hint" style={{ margin: "10px 0 6px" }}>
              Added by you
            </p>
            <Chips items={resume.extra_skills} kind="ok" onRemove={(skill) => void change({ remove: skill })} />
          </>
        )}
        <hr className="divider" />
        <form
          className="row"
          onSubmit={(event) => {
            event.preventDefault();
            void change({ add: typed });
          }}
        >
          <div style={{ flex: "1 1 240px" }}>
            <Field label="Add a skill" help="For skills your resume file does not mention. Separate several with commas.">
              <input
                type="text"
                value={typed}
                placeholder="Kafka, Hibernate, System Design"
                onChange={(event) => setTyped(event.target.value)}
              />
            </Field>
          </div>
          <button type="submit" disabled={saving}>
            Add skill
          </button>
        </form>
        {note && (
          <div style={{ marginTop: 10 }}>
            <Notice tone={tone}>{note}</Notice>
          </div>
        )}
      </Panel>

      <div className="grid2">
        <Panel title="Experience">
          {resume.experience.length ? (
            <ul className="stack" style={{ margin: 0, paddingLeft: 18 }}>
              {resume.experience.map((entry, i) => (
                <li key={`${entry.head}-${i}`}>
                  <span style={{ fontWeight: 500 }}>{entry.head}</span>
                  {entry.dates && <span className="muted"> ({entry.dates})</span>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="hint">No experience section detected.</p>
          )}
        </Panel>
        <Panel title="Education">
          {resume.education.length ? (
            <div className="stack">
              {resume.education.map((line, i) => (
                <p key={i}>{line}</p>
              ))}
            </div>
          ) : (
            <p className="hint">No education section detected.</p>
          )}
        </Panel>
      </div>

      {resume.raw_text && (
        <Panel title="Text read from your file">
          <details>
            <summary className="hint" style={{ cursor: "pointer" }}>
              Show the text {resume.raw_truncated ? "(first 10,000 characters)" : ""}
            </summary>
            <pre
              style={{
                marginTop: 10,
                maxHeight: 360,
                overflow: "auto",
                whiteSpace: "pre-wrap",
                fontFamily: "var(--mono)",
                fontSize: "0.8rem",
                color: "var(--ink-2)",
              }}
            >
              {resume.raw_text}
            </pre>
          </details>
        </Panel>
      )}
    </>
  );
}
