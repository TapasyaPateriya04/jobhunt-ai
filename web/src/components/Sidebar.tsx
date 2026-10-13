/* The column that is the same on every tab: which resume is in use, which model
   writes, and where the data is kept. */
import { useApp } from "../state";
import { countLabel, Field, Panel, StatusDot } from "./ui";

const GEMINI = "gemini";

export function Sidebar() {
  const { resume, resumes, resumeId, status, model, setModel, pickResume } = useApp();

  return (
    <aside className="sidebar">
      <Panel title="Your resume">
        {!resume ? (
          <p className="hint">No resume yet. Upload one on the Resume tab.</p>
        ) : resumes.length > 1 ? (
          <Field
            label="Resume in use"
            help="Matches, applications, skill suggestions and documents all use this resume."
          >
            <select
              value={resumeId ?? ""}
              onChange={(event) => pickResume(Number(event.target.value))}
            >
              {resumes.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.name} ({countLabel(entry.skill_count, "skill")}
                  {entry.created_at ? `, ${day(entry.created_at)}` : ""})
                </option>
              ))}
            </select>
          </Field>
        ) : (
          <>
            <p style={{ fontWeight: 600 }}>{resume.name}</p>
            <p className="hint">{countLabel(resume.skill_count, "skill")} found</p>
          </>
        )}
      </Panel>

      <Panel title="Language model">
        <p className="hint" style={{ marginBottom: 8 }}>
          Writes cover letters and resume suggestions.
        </p>
        <StatusDot
          label="Ollama"
          ok={Boolean(status?.ollama.enabled && status.ollama.reachable)}
          okText={`ready, ${countLabel(status?.ollama.models.length ?? 0, "model")} installed`}
          badText={
            status?.ollama.enabled === false
              ? "turned off (USE_OLLAMA=false)"
              : "not running. Start it with ollama serve"
          }
        />
        <StatusDot
          label="Gemini"
          ok={Boolean(status?.gemini.configured)}
          okText="API key configured"
          badText="not set up (no GEMINI_API_KEY)"
        />
        {status && status.models.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <Field
              label="Model for writing"
              help="Smaller models write faster on a laptop without a graphics card. Install more with ollama pull."
            >
              <select value={model ?? ""} onChange={(event) => setModel(event.target.value)}>
                {status.models.map((name) => (
                  <option key={name} value={name}>
                    {name === GEMINI ? "Gemini (online, sends your resume to Google)" : withSize(name, status)}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        )}
      </Panel>

      <Panel title="Storage">
        <p className="hint">Database</p>
        <p style={{ fontFamily: "var(--mono)", fontSize: "0.8rem", wordBreak: "break-all" }}>
          {status?.database ?? "reading..."}
        </p>
        <p className="hint" style={{ marginTop: 8 }}>
          Documents
        </p>
        <p style={{ fontFamily: "var(--mono)", fontSize: "0.8rem", wordBreak: "break-all" }}>
          {status?.docs_dir ?? "reading..."}
        </p>
        <hr className="divider" />
        <p className="hint">
          Everything runs on this machine. Your data only leaves it if you enable Gemini.
        </p>
        {status && (
          <p className="hint" style={{ marginTop: 6 }}>
            {status.embedding_model
              ? `Jobs are compared by meaning with ${status.embedding_model}.`
              : "Jobs are compared by keywords: the meaning model is not available here."}
          </p>
        )}
      </Panel>
    </aside>
  );
}

function withSize(name: string, status: { ollama: { models: { name: string; size: string }[] } }): string {
  const found = status.ollama.models.find((m) => m.name === name);
  return found?.size ? `${name} (${found.size})` : name;
}

function day(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}
