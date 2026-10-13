import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "./api";

type Load<T> = { data: T | null; error: string; loading: boolean; reload: () => void };

/** Load something from the API, with a reload the screens call after they change it. */
export function useLoad<T>(fetcher: () => Promise<T>, deps: unknown[], enabled = true): Load<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(enabled);
  const [tick, setTick] = useState(0);
  const alive = useRef(true);
  // The fetcher closes over the deps, so it is read through a ref and the deps drive the effect.
  const call = useRef(fetcher);
  call.current = fetcher;

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      setData(null);
      return;
    }
    let current = true;
    setLoading(true);
    call
      .current()
      .then((value) => {
        if (current && alive.current) {
          setData(value);
          setError("");
        }
      })
      .catch((exc: unknown) => {
        if (current && alive.current) setError(message(exc));
      })
      .finally(() => {
        if (current && alive.current) setLoading(false);
      });
    return () => {
      current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data, error, loading, reload };
}

export function message(exc: unknown): string {
  if (exc instanceof ApiError) return exc.message;
  if (exc instanceof Error && exc.message) return exc.message;
  return "Something went wrong. Details are in the terminal the app runs in.";
}

/** A short-lived line of feedback under a control, the way a toast reads. */
export function useFlash(): [string, "ok" | "warn" | "bad" | "info", (text: string, kind?: "ok" | "warn" | "bad" | "info") => void] {
  const [text, setText] = useState("");
  const [kind, setKind] = useState<"ok" | "warn" | "bad" | "info">("ok");
  const timer = useRef<number>();
  const show = useCallback((next: string, nextKind: "ok" | "warn" | "bad" | "info" = "ok") => {
    setText(next);
    setKind(nextKind);
    window.clearTimeout(timer.current);
    if (next) timer.current = window.setTimeout(() => setText(""), 7000);
  }, []);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return [text, kind, show];
}

/** 'Today', '2 days ago', '3 weeks ago' for a posting date; '' when unknown. */
export function timeAgo(value: string | null): string {
  if (!value) return "";
  const then = new Date(value);
  if (Number.isNaN(then.getTime())) return "";
  const days = Math.floor((Date.now() - then.getTime()) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "1 day ago";
  if (days < 14) return `${days} days ago`;
  if (days < 60) return `${Math.floor(days / 7)} weeks ago`;
  return `${Math.floor(days / 30)} months ago`;
}

export function plural(n: number, one: string, many?: string): string {
  return n === 1 ? one : many ?? `${one}s`;
}

/** True while the media query matches, kept current as the window is resized. */
export function useMedia(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const list = window.matchMedia(query);
    const update = () => setMatches(list.matches);
    update();
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, [query]);
  return matches;
}
