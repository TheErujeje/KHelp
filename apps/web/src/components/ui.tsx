import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle, ArrowLeft, ChevronDown, ChevronRight, Flag as FlagIcon, X } from "lucide-react";
import type { Citation, Flag, Priority } from "../api";
import { useRulesStatus } from "../api";

// ---------------------------------------------------------------- priority & flags

const PRIORITY_STYLE: Record<Priority, string> = {
  RED: "bg-sats-red text-white",
  ORANGE: "bg-sats-orange text-white",
  YELLOW: "bg-sats-yellow text-slate-900",
  GREEN: "bg-sats-green text-white",
};

export function PriorityBadge({ priority, size = "md" }: { priority: Priority | null; size?: "sm" | "md" | "lg" | "xl" }) {
  const pad = {
    sm: "px-1.5 py-0.5 text-[11px]", md: "px-2 py-0.5 text-xs", lg: "px-3 py-1 text-sm", xl: "px-4 py-1.5 text-lg",
  }[size];
  if (!priority) {
    return <span className={`inline-block rounded-md border border-dashed border-slate-300 font-semibold text-ink-3 ${pad}`}>
      Not set</span>;
  }
  return <span className={`inline-block rounded-md font-bold tracking-wide ${PRIORITY_STYLE[priority]} ${pad}`}>{priority}</span>;
}

export const FLAG_LABEL: Record<Flag["flag_type"], string> = {
  MISSING_VITALS: "Vitals needed",
  DETERIORATION: "Second look: worse",
  MANUAL_TRIAGE: "Manual triage",
  OTHER: "Re-check",
};

export function FlagChip({ flag }: { flag: Pick<Flag, "flag_type" | "reason"> }) {
  const urgent = flag.flag_type === "DETERIORATION" || flag.flag_type === "MANUAL_TRIAGE";
  return (
    <span title={flag.reason}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
        urgent ? "bg-red-50 text-red-700 ring-1 ring-red-200" : "bg-amber-50 text-amber-800 ring-1 ring-amber-200"}`}>
      <FlagIcon size={11} /> {FLAG_LABEL[flag.flag_type]}
    </span>
  );
}

// ---------------------------------------------------------------- layout bits

export function Card({ title, subtitle, children, actions, padded = true }: {
  title?: ReactNode; subtitle?: ReactNode; children: ReactNode; actions?: ReactNode; padded?: boolean;
}) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-3.5">
          <div>
            <h2 className="font-semibold">{title}</h2>
            {subtitle && <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className={padded ? "p-5" : ""}>{children}</div>
    </section>
  );
}

/** Back to wherever the user came from; if they arrived directly (no in-app history), go to `fallback`. */
export function BackButton({ fallback }: { fallback: string }) {
  const navigate = useNavigate();
  const canGoBack = ((window.history.state as { idx?: number } | null)?.idx ?? 0) > 0;
  return (
    <button onClick={() => (canGoBack ? navigate(-1) : navigate(fallback))}
      className="mb-2 inline-flex items-center gap-1 text-sm font-semibold text-ink-2 hover:text-brand">
      <ArrowLeft size={16} /> Back
    </button>
  );
}

export function PageHeader({ title, subtitle, actions, back }: {
  title: string; subtitle?: string; actions?: ReactNode; back?: string;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        {back && <div><BackButton fallback={back} /></div>}
        <h1 className="text-xl font-bold">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-ink-2">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return <p className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{(error as Error).message}</p>;
}

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
      <aside className="relative z-50 flex h-full w-full max-w-2xl flex-col bg-canvas shadow-2xl">
        <header className="flex items-center justify-between border-b border-line bg-white px-5 py-3.5">
          <div className="font-semibold">{title}</div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-ink-2 hover:bg-slate-100" aria-label="Close"><X size={18} /></button>
        </header>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </aside>
    </div>
  );
}

export function RulesBanner() {
  const { data } = useRulesStatus();
  if (!data || data.all_verified) return null;
  return (
    <div role="alert" className="flex items-center gap-2 border-b border-amber-300 bg-amber-100 px-5 py-2 text-xs font-semibold text-amber-900">
      <AlertTriangle size={14} className="shrink-0" />
      UNVERIFIED RULES: {data.unverified_count} of {data.total} SATS rule entries are not yet checked against the SATS
      manual. Demonstration with synthetic patients only.
    </div>
  );
}

export function PatientLink({ id, name }: { id: number; name: string }) {
  return <Link to={`/patients/${id}`} className="font-semibold text-ink hover:text-brand hover:underline">{name}</Link>;
}

// ---------------------------------------------------------------- citations

function SourceRef({ c }: { c: { source: { document: string; edition: string; location: string }; verified: boolean } }) {
  return (
    <span className="text-[11px] text-ink-3">
      {c.source.document}{c.source.edition !== "n/a" && ` ${c.source.edition}`} · {c.source.location}
      {!c.verified && <span className="ml-1 rounded bg-amber-100 px-1 font-semibold text-amber-800">unverified</span>}
    </span>
  );
}

/** One-line answer to "why this priority?", built from the server's citations. */
export function WhySummary({ citations, priority }: { citations: Citation[]; priority: Priority }) {
  const rule = citations.find((c) => c.type === "tews_rule");
  const signs = citations.filter((c) => c.type === "discriminator");
  const missing = citations.find((c) => c.type === "missing_inputs_rule");
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-sm">
      {rule && (
        <span className="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-2 py-1">
          TEWS {rule.tews_total ?? `${rule.tews_min}–${rule.tews_max}`} <PriorityBadge priority={rule.priority} size="sm" />
        </span>
      )}
      {signs.map((s) => (
        <span key={s.discriminator_id} className="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-2 py-1">
          {s.name} <PriorityBadge priority={s.priority} size="sm" />
        </span>
      ))}
      <span className="text-ink-3">→ highest wins →</span>
      <PriorityBadge priority={priority} />
      {missing && <span className="text-xs font-medium text-amber-700">Not recorded: {missing.outstanding_inputs.join(", ")}</span>}
    </div>
  );
}

export function CitationList({ citations }: { citations: Citation[] }) {
  const vitals = citations.filter((c) => c.type === "vital");
  const rules = citations.filter((c) => c.type === "tews_rule");
  const signs = citations.filter((c) => c.type === "discriminator");
  const missing = citations.filter((c) => c.type === "missing_inputs_rule");
  return (
    <div className="space-y-4 text-sm">
      {vitals.length > 0 && (
        <div>
          <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-3">Vitals → TEWS band → points</h4>
          <div className="overflow-hidden rounded-lg border border-line">
            <table className="w-full text-left">
              <tbody>
                {vitals.map((c) => (
                  <tr key={c.band_id} className="border-b border-line align-top last:border-0">
                    <td className="px-3 py-2 font-medium">{c.label}</td>
                    <td className="px-3 py-2 tabular-nums">{String(c.value)}{c.unit ? ` ${c.unit}` : ""}</td>
                    <td className="px-3 py-2 text-ink-2">{c.band}</td>
                    <td className="px-3 py-2 font-bold tabular-nums">{c.points}</td>
                    <td className="px-3 py-2"><SourceRef c={c} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {rules.map((c) => (
        <div key={c.rule_id}>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-3">TEWS rule</h4>
          {c.tews_total !== null ? `Total ${c.tews_total}` : `Total ${c.tews_min}–${c.tews_max}`} falls in{" "}
          {c.range[0]}{c.range[1] === null ? "+" : `–${c.range[1]}`} → <PriorityBadge priority={c.priority} size="sm" />{" "}
          <div><SourceRef c={c} /></div>
        </div>
      ))}
      {signs.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-3">Emergency signs</h4>
          <ul className="space-y-1.5">
            {signs.map((c) => (
              <li key={c.discriminator_id}>
                <span className="font-medium">{c.name}</span> <PriorityBadge priority={c.priority} size="sm" />{" "}
                <span className="text-ink-2">from “{c.matched_phrase}” in “{c.clause}”</span>
                <div><SourceRef c={c} /></div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {missing.map((c) => (
        <div key={c.rule_id} className="rounded-lg bg-amber-50 p-3 text-amber-900">
          <span className="font-semibold">Not recorded: </span>{c.outstanding_inputs.join(", ")}. Priority could be{" "}
          {c.priority_low}{c.priority_high !== c.priority_low && ` to ${c.priority_high}`} until recorded.
          <div><SourceRef c={c} /></div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- run events (SSE)

export interface RunEvent {
  id: number;
  created_at: string;
  event_type: string;
  source: string;
  tool_name: string | null;
  inputs: Record<string, unknown> | null;
  outputs: Record<string, unknown> | null;
  is_error: boolean;
  latency_ms: number | null;
}

export type StreamState = "connecting" | "live" | "ended" | "error";

/** Subscribe to a run's audit events. Mount the caller with key={runId}. */
export function useRunEvents(runId: string): { events: RunEvent[]; state: StreamState } {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [state, setState] = useState<StreamState>("connecting");
  useEffect(() => {
    const source = new EventSource(`/api/runs/${runId}/events`);
    source.onopen = () => setState("live");
    source.addEventListener("audit", (msg) => {
      const event = JSON.parse((msg as MessageEvent).data) as RunEvent;
      setEvents((prev) => (prev.some((p) => p.id === event.id) ? prev : [...prev, event]));
    });
    source.addEventListener("end", () => { setState("ended"); source.close(); });
    source.onerror = () => setState((s) => (s === "ended" ? s : "error"));
    return () => source.close();
  }, [runId]);
  return { events, state };
}

export function errorCodes(e: RunEvent): string[] {
  const body = (e.outputs?.json ?? e.outputs) as { errors?: { code: string }[] } | undefined;
  return body?.errors?.map((x) => x.code) ?? [];
}

const STEP_TEXT: Record<string, [string, string]> = {
  read_text_file: ["Read the intake note", "Reading the intake note"],
  lookup_discriminators: ["Checked for emergency signs", "Checking for emergency signs"],
  compute_tews: ["Calculated the TEWS score", "Calculating the TEWS score"],
  propose_priority: ["Proposed a priority", "Proposing a priority"],
  request_recheck: ["Raised a flag for you", "Raising a flag"],
  get_queue: ["Looked at the queue", "Looking at the queue"],
};

const ERROR_TEXT: Record<string, string> = {
  PRIORITY_MISMATCH: "the rules give a different priority",
  UNCITED_DISCRIMINATOR: "an emergency sign was left out",
  DISCRIMINATOR_NOT_IN_NOTE: "it cited a sign that isn't in the note",
  UNGROUNDED_VITALS: "a vital wasn't in the note",
  UNGROUNDED_AGE: "the age wasn't in the note",
  NOT_SCORING_LANGUAGE: "the rationale sounded like a diagnosis",
  MISSING_RATIONALE: "the rationale was missing",
};

/** Plain-language progress for the nurse. The technical feed is on the run page. */
export function StepTimeline({ events, state }: { events: RunEvent[]; state: StreamState }) {
  const steps = events.filter((e) => e.source === "agent" || e.event_type === "NUDGE");
  const done = state === "ended";
  return (
    <ol className="space-y-2.5">
      {steps.map((e) => {
        if (e.event_type === "NUDGE") {
          return <Step key={e.id} tone="warn" text="Assistant paused; asked it to finish" />;
        }
        const [doneText] = STEP_TEXT[e.tool_name ?? ""] ?? [e.tool_name ?? "Step", ""];
        const codes = errorCodes(e);
        if (e.is_error) {
          const why = codes.map((c) => ERROR_TEXT[c] ?? c.toLowerCase().replaceAll("_", " ")).join("; ");
          return <Step key={e.id} tone="error" text={`Server rejected the proposal: ${why || "error"}. Correcting…`} />;
        }
        return <Step key={e.id} tone="ok" text={doneText} ms={e.latency_ms} />;
      })}
      {!done && <Step tone="pending" text={steps.length === 0 ? "Starting…" : "Working…"} />}
    </ol>
  );
}

function Step({ tone, text, ms }: { tone: "ok" | "error" | "warn" | "pending"; text: string; ms?: number | null }) {
  const dot = {
    ok: "bg-brand text-white", error: "bg-red-500 text-white", warn: "bg-amber-400 text-white",
    pending: "border-2 border-brand/40 bg-white animate-pulse",
  }[tone];
  return (
    <li className="flex items-center gap-3 text-sm">
      <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${dot}`}>
        {tone === "ok" ? "✓" : tone === "error" ? "!" : tone === "warn" ? "…" : ""}
      </span>
      <span className={tone === "error" ? "text-red-700" : tone === "pending" ? "text-ink-3" : "text-ink"}>{text}</span>
      {ms != null && <span className="ml-auto text-[11px] tabular-nums text-ink-3">{ms} ms</span>}
    </li>
  );
}

/** Every audit row for a run, expandable to raw inputs/outputs. For the demo and audits. */
export function ToolFeed({ events, state, showServerRows = false }: { events: RunEvent[]; state: StreamState; showServerRows?: boolean }) {
  const shown = events.filter((e) => showServerRows || e.source !== "triage-tools");
  return (
    <div>
      <div className="mb-3 flex items-center gap-2 text-xs text-ink-3">
        <span className={`inline-block h-2 w-2 rounded-full ${
          state === "live" ? "animate-pulse bg-green-500" : state === "ended" ? "bg-slate-400" : "bg-amber-500"}`} />
        {state === "live" ? "Live" : state === "ended" ? "Run finished" : state === "error" ? "Reconnecting…" : "Connecting…"}
      </div>
      <ol className="space-y-1.5">
        {shown.map((e) => <FeedRow key={e.id} e={e} />)}
        {shown.length === 0 && <li className="text-sm text-ink-3">Waiting for the agent…</li>}
      </ol>
    </div>
  );
}

function FeedRow({ e }: { e: RunEvent }) {
  const [open, setOpen] = useState(false);
  const codes = errorCodes(e);
  const isTool = e.event_type === "TOOL_CALL";
  const label = isTool ? e.tool_name : e.event_type.replaceAll("_", " ").toLowerCase();
  return (
    <li className={`rounded-lg border text-sm ${e.is_error ? "border-red-200 bg-red-50" : "border-line bg-white"}`}>
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-3 py-2 text-left">
        {open ? <ChevronDown size={14} className="text-ink-3" /> : <ChevronRight size={14} className="text-ink-3" />}
        <span className="font-mono text-[11px] text-ink-3">{e.created_at.slice(11, 19)}</span>
        <span className={`rounded px-1.5 text-[11px] font-medium ${isTool ? "bg-brand-soft text-teal-900" : "bg-slate-100 text-ink-2"}`}>
          {isTool ? (e.source === "agent" ? "tool" : e.source) : e.source}
        </span>
        <span className="font-mono font-semibold">{label}</span>
        {codes.length > 0 && <span className="text-xs font-semibold text-red-700">{codes.join(", ")}</span>}
        <span className="ml-auto text-[11px] tabular-nums text-ink-3">{e.latency_ms != null ? `${e.latency_ms} ms` : ""}</span>
      </button>
      {open && (
        <div className="grid gap-2 border-t border-line p-2 md:grid-cols-2">
          <pre className="max-h-72 overflow-auto rounded-md bg-slate-900 p-2 text-[11px] text-slate-100">
            {JSON.stringify(e.inputs, null, 2)}</pre>
          <pre className="max-h-72 overflow-auto rounded-md bg-slate-900 p-2 text-[11px] text-slate-100">
            {JSON.stringify(e.outputs, null, 2)}</pre>
        </div>
      )}
    </li>
  );
}
