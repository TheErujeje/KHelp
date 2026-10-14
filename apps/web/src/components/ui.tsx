import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Citation, Flag, Priority } from "../api";
import { useRulesStatus } from "../api";

const PRIORITY_STYLE: Record<Priority, string> = {
  RED: "bg-sats-red text-white",
  ORANGE: "bg-sats-orange text-white",
  YELLOW: "bg-sats-yellow text-slate-900",
  GREEN: "bg-sats-green text-white",
};

export function PriorityBadge({ priority, size = "md" }: { priority: Priority | null; size?: "sm" | "md" | "lg" }) {
  const pad = size === "lg" ? "px-3 py-1 text-base" : size === "sm" ? "px-1.5 py-0.5 text-xs" : "px-2 py-0.5 text-sm";
  if (!priority) {
    return <span className={`inline-block rounded font-semibold border border-dashed border-slate-400 text-slate-500 ${pad}`}>
      Not prioritised</span>;
  }
  return <span className={`inline-block rounded font-bold tracking-wide ${PRIORITY_STYLE[priority]} ${pad}`}>{priority}</span>;
}

const FLAG_LABEL: Record<Flag["flag_type"], string> = {
  MISSING_VITALS: "Vitals needed",
  DETERIORATION: "Second look: worse",
  MANUAL_TRIAGE: "Manual triage",
  OTHER: "Re-check",
};

export function FlagChip({ flag }: { flag: Flag }) {
  const urgent = flag.flag_type === "DETERIORATION" || flag.flag_type === "MANUAL_TRIAGE";
  return (
    <span title={flag.reason}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${
        urgent ? "bg-red-100 text-red-800 ring-1 ring-red-300" : "bg-amber-100 text-amber-900 ring-1 ring-amber-300"}`}>
      ⚑ {FLAG_LABEL[flag.flag_type]}
    </span>
  );
}

export function Card({ title, children, actions }: { title?: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-2.5">
          <h2 className="font-semibold text-slate-800">{title}</h2>
          {actions}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return <p className="mt-2 rounded bg-red-50 px-2 py-1 text-sm text-red-700">{(error as Error).message}</p>;
}

// ---------------------------------------------------------------- clinician name

export function ClinicianField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-slate-700">Your name (required)</span>
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder="e.g. Nurse A. Okafor"
        className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 focus:border-teal-600 focus:outline-none" />
    </label>
  );
}

// ---------------------------------------------------------------- rules banner

export function RulesBanner() {
  const { data } = useRulesStatus();
  if (!data || data.all_verified) return null;
  return (
    <div role="alert" className="bg-amber-400 px-4 py-2 text-center text-sm font-semibold text-amber-950">
      UNVERIFIED RULES: {data.unverified_count} of {data.total} SATS rule entries have not yet been checked against the
      SATS manual. Every priority shown here is a draft for demonstration with synthetic patients only.
    </div>
  );
}

// ---------------------------------------------------------------- citations

function SourceRef({ c }: { c: { source: { document: string; edition: string; location: string }; verified: boolean } }) {
  return (
    <span className="text-xs text-slate-500">
      {c.source.document} {c.source.edition !== "n/a" && `(${c.source.edition})`}, {c.source.location}
      {!c.verified && <span className="ml-1 rounded bg-amber-100 px-1 font-semibold text-amber-800">unverified</span>}
    </span>
  );
}

export function CitationList({ citations }: { citations: Citation[] }) {
  const vitals = citations.filter((c) => c.type === "vital");
  const rules = citations.filter((c) => c.type === "tews_rule");
  const signs = citations.filter((c) => c.type === "discriminator");
  const missing = citations.filter((c) => c.type === "missing_inputs_rule");
  return (
    <div className="space-y-3 text-sm">
      {vitals.length > 0 && (
        <div>
          <h4 className="mb-1 font-semibold text-slate-700">Vitals → TEWS band → points</h4>
          <table className="w-full text-left">
            <tbody>
              {vitals.map((c) => (
                <tr key={c.band_id} className="border-t border-slate-100 align-top">
                  <td className="py-1 pr-2 font-medium">{c.label}</td>
                  <td className="py-1 pr-2 tabular-nums">{String(c.value)}{c.unit ? ` ${c.unit}` : ""}</td>
                  <td className="py-1 pr-2">band {c.band}</td>
                  <td className="py-1 pr-2 font-semibold tabular-nums">{c.points} pt</td>
                  <td className="py-1"><SourceRef c={c} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rules.map((c) => (
        <div key={c.rule_id}>
          <span className="font-semibold text-slate-700">TEWS rule: </span>
          {c.tews_total !== null ? `total ${c.tews_total}` : `total ${c.tews_min}–${c.tews_max}`} → range{" "}
          {c.range[0]}{c.range[1] === null ? "+" : `–${c.range[1]}`} → <PriorityBadge priority={c.priority} size="sm" />{" "}
          <SourceRef c={c} />
        </div>
      ))}
      {signs.map((c) => (
        <div key={c.discriminator_id}>
          <span className="font-semibold text-slate-700">Emergency sign: </span>
          {c.name} <PriorityBadge priority={c.priority} size="sm" />{" "}
          <span className="text-slate-600">matched “{c.matched_phrase}” in “{c.clause}”</span>{" "}
          <SourceRef c={c} />
        </div>
      ))}
      {missing.map((c) => (
        <div key={c.rule_id} className="rounded bg-amber-50 p-2">
          <span className="font-semibold text-amber-900">Not recorded: </span>
          {c.outstanding_inputs.join(", ")}. Priority could be {c.priority_low}
          {c.priority_high !== c.priority_low && ` to ${c.priority_high}`} until recorded. <SourceRef c={c} />
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- live tool-call feed

interface FeedEvent {
  id: number;
  created_at: string;
  event_type: string;
  source: string;
  tool_name: string | null;
  inputs: Record<string, unknown> | null;
  outputs: Record<string, unknown> | null;
  is_error: boolean;
  latency_ms: number | null;
  actor: string | null;
}

function errorCodes(e: FeedEvent): string[] {
  const body = (e.outputs?.json ?? e.outputs) as { errors?: { code: string }[] } | undefined;
  return body?.errors?.map((x) => x.code) ?? [];
}

export function LiveFeed({ runId, showServerRows = false }: { runId: string; showServerRows?: boolean }) {
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [state, setState] = useState<"connecting" | "live" | "ended" | "error">("connecting");

  // Mounted with key={runId}, so state starts fresh for each run.
  useEffect(() => {
    const source = new EventSource(`/api/runs/${runId}/events`);
    source.onopen = () => setState("live");
    source.addEventListener("audit", (msg) => {
      const event = JSON.parse((msg as MessageEvent).data) as FeedEvent;
      setEvents((prev) => (prev.some((p) => p.id === event.id) ? prev : [...prev, event]));
    });
    source.addEventListener("end", () => { setState("ended"); source.close(); });
    source.onerror = () => setState((s) => (s === "ended" ? s : "error"));
    return () => source.close();
  }, [runId]);

  const shown = events.filter((e) => showServerRows || e.source !== "triage-tools");
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
        <span className={`inline-block h-2 w-2 rounded-full ${
          state === "live" ? "animate-pulse bg-green-500" : state === "ended" ? "bg-slate-400" : "bg-amber-500"}`} />
        {state === "live" ? "Live" : state === "ended" ? "Run finished" : state === "error" ? "Reconnecting…" : "Connecting…"}
        <span className="ml-auto font-mono">run {runId.slice(0, 8)}</span>
      </div>
      <ol className="space-y-1.5">
        {shown.map((e) => <FeedRow key={e.id} e={e} />)}
        {shown.length === 0 && <li className="text-sm text-slate-500">Waiting for the agent…</li>}
      </ol>
    </div>
  );
}

function FeedRow({ e }: { e: FeedEvent }) {
  const [open, setOpen] = useState(false);
  const codes = errorCodes(e);
  const isTool = e.event_type === "TOOL_CALL";
  const label = isTool ? e.tool_name : e.event_type.replaceAll("_", " ").toLowerCase();
  return (
    <li className={`rounded border text-sm ${e.is_error ? "border-red-300 bg-red-50" : "border-slate-200 bg-white"}`}>
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-2 py-1.5 text-left">
        <span className="font-mono text-xs text-slate-500">{e.created_at.slice(11, 19)}</span>
        <span className={`rounded px-1.5 text-xs ${isTool ? "bg-teal-100 text-teal-900" : "bg-slate-100 text-slate-700"}`}>
          {isTool ? (e.source === "agent" ? "tool" : e.source) : e.source}
        </span>
        <span className="font-mono font-semibold">{label}</span>
        {codes.length > 0 && <span className="text-xs font-semibold text-red-700">{codes.join(", ")}</span>}
        {e.event_type === "NUDGE" && <span className="text-xs text-amber-700">runner asked the model to finish</span>}
        <span className="ml-auto text-xs tabular-nums text-slate-500">{e.latency_ms != null ? `${e.latency_ms} ms` : ""}</span>
        <span className="text-xs text-slate-400">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="grid gap-2 border-t border-slate-200 p-2 md:grid-cols-2">
          <pre className="max-h-64 overflow-auto rounded bg-slate-900 p-2 text-xs text-slate-100">
            {JSON.stringify(e.inputs, null, 2)}</pre>
          <pre className="max-h-64 overflow-auto rounded bg-slate-900 p-2 text-xs text-slate-100">
            {JSON.stringify(e.outputs, null, 2)}</pre>
        </div>
      )}
    </li>
  );
}

export function PatientLink({ id, name }: { id: number; name: string }) {
  return <Link to={`/patients/${id}`} className="font-medium text-teal-800 hover:underline">{name}</Link>;
}
