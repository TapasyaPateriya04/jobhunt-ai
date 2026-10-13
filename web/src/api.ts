/* Every call to the local API lives here, so no screen builds a URL by hand.
   The API runs on 127.0.0.1 and talks to the same Python functions the Streamlit
   app uses, so nothing in this file sends data anywhere else. */

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError("The app cannot reach its own server. Check that it is still running.");
  }
  if (!response.ok) {
    let detail = `Something went wrong (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep the status line */
    }
    throw new ApiError(detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const get = <T,>(path: string, params?: Record<string, unknown>) =>
  request<T>(params ? `${path}?${query(params)}` : path);

export const post = <T,>(path: string, body?: unknown, params?: Record<string, unknown>) =>
  request<T>(params ? `${path}?${query(params)}` : path, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

export const patch = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const del = <T,>(path: string, params?: Record<string, unknown>) =>
  request<T>(params ? `${path}?${query(params)}` : path, { method: "DELETE" });

export function query(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  return search.toString();
}

/** Upload a resume file. FormData, so no JSON body. */
export async function uploadResume(file: File, replaces?: number | null): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  const url = `/api/resume/upload${replaces ? `?replaces=${replaces}` : ""}`;
  const response = await fetch(url, { method: "POST", body: form });
  if (!response.ok) {
    let detail = `The file could not be read (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep the status line */
    }
    throw new ApiError(detail);
  }
  return (await response.json()) as UploadResult;
}

/** Stream a draft, handing each piece of text to ``onChunk`` as it arrives. */
export async function streamDraft(
  body: { match_id: number; doc_type: string; model?: string | null },
  onChunk: (text: string) => void,
  signal?: AbortSignal,
): Promise<string> {
  const response = await fetch("/api/documents/draft", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    let detail = "The draft could not be started.";
    try {
      const parsed = await response.json();
      if (typeof parsed?.detail === "string") detail = parsed.detail;
    } catch {
      /* keep the default line */
    }
    throw new ApiError(detail);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let all = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    const text = decoder.decode(value, { stream: true });
    all += text;
    onChunk(text);
  }
  return all;
}

/** Ask the server for a file (Word, PDF or CSV) and hand it to the browser. */
export async function download(path: string, init: RequestInit | undefined, filename: string): Promise<void> {
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    let detail = `The file could not be prepared (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep the status line */
    }
    throw new ApiError(detail);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function saveText(content: string, filename: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/* ----------------------------------------------------------------- types */

export type Source = {
  key: string;
  name: string;
  about: string;
  default: boolean;
  configured: boolean;
  opt_in: boolean;
};

export type ScorePart = { key: string; label: string; weight: number; about: string };

export type Catalog = {
  sources: Source[];
  statuses: { key: string; label: string }[];
  tracked_statuses: { key: string; label: string; hint: string }[];
  bands: { key: string; label: string; min: number }[];
  score_parts: ScorePart[];
  score_note: string;
  doc_types: { key: string; label: string }[];
  sorts: string[];
  collection_note: { title: string; body: string }[];
  max_jobs_per_session: number;
  upload_max_bytes: number;
  refresh_minutes: number;
  auto_refresh_offered: boolean;
};

export type OllamaModel = { name: string; size: string; bytes: number };

export type Status = {
  database: string;
  docs_dir: string;
  counts: Record<string, number>;
  ollama: {
    enabled: boolean;
    reachable: boolean;
    base_url: string;
    configured_model: string;
    models: OllamaModel[];
  };
  gemini: { configured: boolean; model: string };
  models: string[];
  embedding_model: string;
};

export type Overview = {
  has_resume: boolean;
  stats: { value: number; label: string }[];
  counts: Record<string, number>;
  next_step: { tab: string; text: string };
};

export type ExperienceEntry = { head: string; dates: string };

export type Resume = {
  id: number;
  name: string;
  created_at: string | null;
  skills: string[];
  extra_skills: string[];
  skill_count: number;
  experience: ExperienceEntry[];
  experience_count: number;
  education: string[];
  summary: string;
  raw_text: string;
  raw_truncated: boolean;
  years: number;
  suggested_keywords: string;
  suggested_location: string;
};

export type ResumeListEntry = { id: number; name: string; skill_count: number; created_at: string | null };

export type UploadResult = { resume: Resume; scored: number; score_error: string };

export type Job = {
  id: number | null;
  title: string;
  company: string;
  location: string;
  url: string;
  source: string;
  source_name: string;
  posted_date: string | null;
  experience_years: number | null;
  skills: string[];
  snippet: string;
};

export type Gap = { required: string[]; matched: string[]; missing: string[]; nice_missing: string[] };

export type Match = {
  id: number;
  job_id: number;
  title: string;
  company: string;
  location: string;
  url: string;
  source: string;
  source_name: string;
  posted_date: string | null;
  status: string;
  score: number;
  band: string;
  band_label: string;
  parts: Record<string, number | null>;
  snippet: string;
  has_description: boolean;
  location_status: string;
  location_text: string;
  location_ok: boolean | null;
  years: number | null;
  gap: Gap;
  near_miss: boolean;
};

export type MatchList = {
  matches: Match[];
  country: string;
  cities: string[];
  candidate_years: number;
  sources: string[];
  source_names: Record<string, string>;
};

export type MatchDetail = {
  description: string;
  requirements: { must_have: string[]; nice_to_have: string[]; source: string };
  keywords: { matched: string[]; missing: string[] };
  have: string[];
};

export type LearnList = {
  skills: { skill: string; jobs: number; closes: number }[];
  jobs: { id: number; title: string; company: string; missing: string[]; matched: number; required: number }[];
  near_count: number;
};

export type SearchResult = {
  found: number;
  new: number;
  per_source: { name: string; count: number }[];
  waiting: { name: string; minutes: number }[];
  scored: number;
  score_error: string;
};

export type DraftableJob = {
  id: number;
  title: string;
  company: string;
  location: string;
  status: string;
  status_label: string;
  score: number;
  band_label: string;
  source_name: string;
  posted_date: string | null;
};

export type SavedDocument = {
  id: number;
  doc_type: string;
  label: string;
  generated_at: string | null;
  content: string;
  words: number;
};

export type FactFlag = { sentence: string; why: string };

export type ExportFormat = { kind: string; available: boolean; reason: string };

export type RefreshState = {
  sites: { key: string; name: string; wait_seconds: number; last_run: number | null }[];
  minutes: number;
};
