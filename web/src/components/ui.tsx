/* The small pieces every screen is built from: panels, chips, bars, notices.
   Icons are inline SVG on a 16 px grid, so the app loads no icon font. */
import type { ReactNode } from "react";

import { plural } from "../hooks";

export type Tone = "ok" | "warn" | "bad" | "info";

const ICONS: Record<string, ReactNode> = {
  briefcase: (
    <>
      <rect x="2" y="5" width="12" height="8.5" rx="1.8" />
      <path d="M6 5V3.8A1.3 1.3 0 0 1 7.3 2.5h1.4A1.3 1.3 0 0 1 10 3.8V5M2 9h12" />
    </>
  ),
  pin: (
    <>
      <path d="M8 14.2s4.3-3.9 4.3-7.4a4.3 4.3 0 0 0-8.6 0c0 3.5 4.3 7.4 4.3 7.4Z" />
      <circle cx="8" cy="6.7" r="1.5" />
    </>
  ),
  check: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="m5.4 8.2 1.8 1.8 3.5-3.7" />
    </>
  ),
  cross: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="m5.8 5.8 4.4 4.4M10.2 5.8l-4.4 4.4" />
    </>
  ),
  alert: (
    <>
      <path d="M8 2.4 14 13H2L8 2.4Z" />
      <path d="M8 6.6v3M8 11.3v.1" />
    </>
  ),
  file: (
    <>
      <path d="M4 2.5h5l3 3v8H4v-11Z" />
      <path d="M9 2.5v3h3M6 9h4M6 11.2h4" />
    </>
  ),
  search: (
    <>
      <circle cx="7.2" cy="7.2" r="4.2" />
      <path d="m10.4 10.4 3.1 3.1" />
    </>
  ),
  filter: <path d="M2.5 3.5h11L9.3 8.6v3.6l-2.6 1.3V8.6L2.5 3.5Z" />,
  external: (
    <>
      <path d="M9 3.5h3.5V7" />
      <path d="M12.5 3.5 7.5 8.5" />
      <path d="M11 9.5v3h-8v-8h3" />
    </>
  ),
  spark: <path d="M8 2v3M8 11v3M2 8h3M11 8h3M4.2 4.2l1.6 1.6M10.2 10.2l1.6 1.6M11.8 4.2l-1.6 1.6M5.8 10.2l-1.6 1.6" />,
  dot: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 5.2v3.1M8 10.7v.1" />
    </>
  ),
};

export function Icon({ name, size = 16 }: { name: keyof typeof ICONS | string; size?: number }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ flex: "0 0 auto" }}
    >
      {ICONS[name] ?? ICONS.dot}
    </svg>
  );
}

export function Panel({
  title,
  count,
  action,
  children,
  tone,
}: {
  title?: string;
  count?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  tone?: "wash" | "flat";
}) {
  return (
    <section className={`card${tone ? ` ${tone}` : ""}`}>
      {(title || action) && (
        <div className="card-title">
          <span>{title}</span>
          {count !== undefined && <span className="count">{count}</span>}
          {action && <span style={{ marginLeft: "auto" }}>{action}</span>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Chips({
  items,
  kind,
  empty = "None found.",
  onRemove,
}: {
  items: string[];
  kind?: "ok" | "miss" | "accent" | "warn";
  empty?: string | null;
  onRemove?: (item: string) => void;
}) {
  if (!items.length) return empty ? <p className="hint">{empty}</p> : null;
  return (
    <div className="chips">
      {items.map((item) => (
        <span className={`chip${kind ? ` ${kind}` : ""}`} key={item}>
          {kind === "ok" && <Icon name="check" size={12} />}
          {kind === "miss" && <Icon name="cross" size={12} />}
          {item}
          {onRemove && (
            <button type="button" aria-label={`Remove ${item}`} onClick={() => onRemove(item)}>
              <Icon name="cross" size={12} />
            </button>
          )}
        </span>
      ))}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <div className={`notice ${tone}`} role={tone === "bad" ? "alert" : "status"}>
      {children}
    </div>
  );
}

export function Empty({ icon, title, hint }: { icon: string; title: string; hint: string }) {
  return (
    <div className="empty">
      <span className="icon">
        <Icon name={icon} size={20} />
      </span>
      <h4>{title}</h4>
      <p>{hint}</p>
    </div>
  );
}

export function Score({ value, band, label }: { value: number; band: string; label: string }) {
  return (
    <span className={`score ${band}`}>
      <span className="num">{Math.round(value)}</span>
      <span className="band">{label}</span>
    </span>
  );
}

export function Bars({
  parts,
  note,
}: {
  parts: { label: string; value: number | null; about?: string }[];
  note?: string;
}) {
  return (
    <div className="bars">
      {parts.map((part) => (
        <div className="bar" key={part.label}>
          <span className="label">{part.label}</span>
          <span className="value">{part.value === null ? "not scored" : `${Math.round(part.value)} / 100`}</span>
          <span className="track">
            <span className="fill" style={{ width: `${Math.max(0, Math.min(100, part.value ?? 0))}%` }} />
          </span>
          {part.about && <span className="about">{part.about}</span>}
        </div>
      ))}
      {note && <p className="hint">{note}</p>}
    </div>
  );
}

export function CountBars({ rows, note }: { rows: [string, number][]; note?: string }) {
  const top = Math.max(1, ...rows.map(([, n]) => n));
  return (
    <div className="countbars">
      {rows.map(([label, n]) => (
        <div className="countbar" key={label}>
          <span>{label}</span>
          <span className="track">
            <span className="fill" style={{ width: `${(n / top) * 100}%` }} />
          </span>
          <span className="n">{n}</span>
        </div>
      ))}
      {note && <p className="hint">{note}</p>}
    </div>
  );
}

export function StatusDot({ label, ok, okText, badText }: { label: string; ok: boolean; okText: string; badText: string }) {
  return (
    <p className="status-row">
      <span className={`dot${ok ? " on" : ""}`} />
      <span className="label">{label}:</span>
      <span className="muted">{ok ? okText : badText}</span>
    </p>
  );
}

export function Field({
  label,
  help,
  children,
}: {
  label: string;
  help?: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {help && <span className="help">{help}</span>}
    </label>
  );
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="stack" aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div className="card" key={i} style={{ display: "grid", gap: 8 }}>
          <div className="skeleton" style={{ height: 15, width: `${60 - i * 7}%` }} />
          <div className="skeleton" style={{ height: 11, width: "42%" }} />
          <div className="skeleton" style={{ height: 11, width: "72%" }} />
        </div>
      ))}
    </div>
  );
}

export function Working({ text }: { text: string }) {
  return (
    <div className="stack" role="status">
      <p className="hint">{text}</p>
      <span className="progress">
        <span className="fill" />
      </span>
    </div>
  );
}

export function Meta({ parts }: { parts: (string | null | undefined)[] }) {
  const shown = parts.filter((p): p is string => Boolean(p && p.trim()));
  return (
    <span className="meta">
      {shown.map((part, i) => (
        <span key={`${part}-${i}`}>
          {i > 0 && <span className="sep">·</span>}
          {part}
        </span>
      ))}
    </span>
  );
}

export function OpenPosting({ url, small }: { url: string; small?: boolean }) {
  if (!/^https?:\/\//.test(url)) return null;
  return (
    <a className={`btn${small ? " small" : ""}`} href={url} target="_blank" rel="noreferrer noopener">
      Open posting
      <Icon name="external" size={13} />
    </a>
  );
}

export function countLabel(n: number, one: string, many?: string): string {
  return `${n} ${plural(n, one, many)}`;
}

/** A posting's text as paragraphs and bullet lists, with no HTML from the source trusted. */
export function Posting({ text }: { text: string }) {
  const blocks: { kind: "p" | "ul" | "h"; lines: string[] }[] = [];
  for (const raw of text.split(/\n+/)) {
    const line = raw.trim();
    if (!line) continue;
    const bullet = line.match(/^(?:[-*•·‣▪●]|\d{1,2}[.)])\s+(.*)$/);
    const heading = line.length < 60 && /[:：]$/.test(line);
    const last = blocks[blocks.length - 1];
    if (bullet) {
      if (last?.kind === "ul") last.lines.push(bullet[1]);
      else blocks.push({ kind: "ul", lines: [bullet[1]] });
    } else if (heading) {
      blocks.push({ kind: "h", lines: [line.replace(/[:：]$/, "")] });
    } else {
      blocks.push({ kind: "p", lines: [line] });
    }
  }
  return (
    <div className="posting">
      {blocks.map((block, i) => {
        if (block.kind === "ul") {
          return (
            <ul key={i}>
              {block.lines.map((line, j) => (
                <li key={j}>{line}</li>
              ))}
            </ul>
          );
        }
        if (block.kind === "h") return <h5 key={i}>{block.lines[0]}</h5>;
        return <p key={i}>{block.lines[0]}</p>;
      })}
    </div>
  );
}
