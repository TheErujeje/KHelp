import { useState } from "react";
import { Link } from "react-router-dom";
import { Download, Lock } from "lucide-react";
import { auditQueryString, useAudit } from "../api";
import { ErrorText, PageHeader } from "../components/ui";

const EMPTY = { patient_id: "", run_id: "", event_type: "", source: "" };
const FIELDS = [
  { key: "patient_id", label: "Patient ID", placeholder: "e.g. 12" },
  { key: "run_id", label: "Run ID", placeholder: "full run id" },
  { key: "event_type", label: "Event", placeholder: "TOOL_CALL, APPROVE, OVERRIDE…" },
  { key: "source", label: "Source", placeholder: "agent, triage-tools, api, runner" },
] as const;

export default function AuditPage() {
  const [draft, setDraft] = useState(EMPTY);
  const [filters, setFilters] = useState(EMPTY);
  const { data, isLoading, error } = useAudit(filters);
  const csvHref = `/api/audit?${auditQueryString({ ...filters, limit: "5000", format: "csv" })}`;

  return (
    <>
      <PageHeader title="Audit log" subtitle="Every tool call and every human decision, with who, when and what."
        actions={<a href={csvHref} className="btn-secondary"><Download size={16} /> Export CSV</a>} />

      <form className="card mb-4 flex flex-wrap items-end gap-3 p-4" onSubmit={(e) => { e.preventDefault(); setFilters(draft); }}>
        {FIELDS.map(({ key, label, placeholder }) => (
          <label key={key} className="min-w-40 flex-1">
            <span className="mb-1 block text-xs font-semibold text-ink-2">{label}</span>
            <input value={draft[key]} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} placeholder={placeholder} className="input" />
          </label>
        ))}
        <button className="btn-primary">Filter</button>
        <button type="button" onClick={() => { setDraft(EMPTY); setFilters(EMPTY); }} className="btn-secondary">Clear</button>
      </form>

      <p className="mb-2 flex items-center gap-1.5 text-xs text-ink-3"><Lock size={12} /> Append-only: the database rejects any update or delete.</p>
      <ErrorText error={error} />
      <section className="card overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line bg-slate-50 text-[11px] uppercase tracking-wide text-ink-3">
            <tr>{["Time", "Event", "Source", "Tool", "Who / model", "Patient", "Run", "ms", ""].map((h) =>
              <th key={h} className="px-3 py-2.5">{h}</th>)}</tr>
          </thead>
          <tbody>
            {isLoading && <tr><td colSpan={9} className="px-3 py-6 text-center text-ink-3">Loading…</td></tr>}
            {data?.entries.map((e) => (
              <tr key={e.id} className={`border-b border-line align-top last:border-0 ${e.is_error ? "bg-red-50" : ""}`}>
                <td className="whitespace-nowrap px-3 py-2 font-mono text-[11px]">{new Date(e.created_at).toLocaleString()}</td>
                <td className="px-3 py-2 text-xs font-semibold">{e.event_type}</td>
                <td className="px-3 py-2 text-xs">{e.source}</td>
                <td className="px-3 py-2 font-mono text-xs">{e.tool_name}</td>
                <td className="px-3 py-2 text-xs">{e.actor ?? <span className="font-mono text-ink-3">{e.model}</span>}</td>
                <td className="px-3 py-2">{e.patient_id && <Link to={`/patients/${e.patient_id}`} className="text-brand hover:underline">#{e.patient_id}</Link>}</td>
                <td className="px-3 py-2">{e.run_id && <Link to={`/runs/${e.run_id}`} className="font-mono text-xs text-brand hover:underline">{e.run_id.slice(0, 8)}</Link>}</td>
                <td className="px-3 py-2 tabular-nums text-xs">{e.latency_ms}</td>
                <td className="px-3 py-2"><details><summary className="cursor-pointer text-xs text-ink-3">data</summary>
                  <pre className="mt-1 max-h-60 max-w-xl overflow-auto rounded-md bg-slate-900 p-2 text-[11px] text-slate-100">
                    {JSON.stringify({ inputs: e.inputs, outputs: e.outputs }, null, 2)}</pre></details></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
