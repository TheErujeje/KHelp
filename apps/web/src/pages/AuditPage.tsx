import { useState } from "react";
import { Link } from "react-router-dom";
import { auditQueryString, useAudit } from "../api";
import { Card, ErrorText } from "../components/ui";

const EMPTY = { patient_id: "", run_id: "", event_type: "", source: "" };

export default function AuditPage() {
  const [draft, setDraft] = useState(EMPTY);
  const [filters, setFilters] = useState(EMPTY);
  const { data, isLoading, error } = useAudit(filters);
  const csvHref = `/api/audit?${auditQueryString({ ...filters, limit: "5000", format: "csv" })}`;

  return (
    <Card title="Audit log" actions={<a href={csvHref} className="rounded border border-slate-300 px-3 py-1 text-sm font-semibold hover:bg-slate-50">Export CSV</a>}>
      <form className="mb-3 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); setFilters(draft); }}>
        {(["patient_id", "run_id", "event_type", "source"] as const).map((k) => (
          <label key={k} className="text-xs text-slate-600">{k.replace("_", " ")}
            <input value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
              placeholder={k === "source" ? "agent / triage-tools / api / runner" : k === "event_type" ? "TOOL_CALL, APPROVE…" : ""}
              className="mt-0.5 block w-44 rounded border border-slate-300 px-2 py-1 text-sm" />
          </label>
        ))}
        <button className="rounded bg-slate-800 px-3 py-1.5 text-sm font-semibold text-white">Filter</button>
        <button type="button" onClick={() => { setDraft(EMPTY); setFilters(EMPTY); }} className="text-sm text-slate-600 underline">Clear</button>
      </form>
      <p className="mb-2 text-xs text-slate-500">Append-only: the database rejects any update or delete on this table.</p>
      <ErrorText error={error} />
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-slate-500">
            <tr><th className="py-1 pr-2">Time</th><th className="pr-2">Event</th><th className="pr-2">Source</th><th className="pr-2">Tool</th>
              <th className="pr-2">Who / model</th><th className="pr-2">Patient</th><th className="pr-2">Run</th><th className="pr-2">ms</th><th>Detail</th></tr>
          </thead>
          <tbody>
            {data?.entries.map((e) => (
              <tr key={e.id} className={`border-t border-slate-100 align-top ${e.is_error ? "bg-red-50" : ""}`}>
                <td className="py-1 pr-2 font-mono text-xs whitespace-nowrap">{new Date(e.created_at).toLocaleString()}</td>
                <td className="pr-2">{e.event_type}</td>
                <td className="pr-2">{e.source}</td>
                <td className="pr-2 font-mono text-xs">{e.tool_name}</td>
                <td className="pr-2 text-xs">{e.actor ?? e.model}</td>
                <td className="pr-2">{e.patient_id && <Link to={`/patients/${e.patient_id}`} className="text-teal-800 hover:underline">#{e.patient_id}</Link>}</td>
                <td className="pr-2">{e.run_id && <Link to={`/runs/${e.run_id}`} className="font-mono text-xs text-teal-800 hover:underline">{e.run_id.slice(0, 8)}</Link>}</td>
                <td className="pr-2 tabular-nums">{e.latency_ms}</td>
                <td><details><summary className="cursor-pointer text-xs text-slate-500">inputs / outputs</summary>
                  <pre className="max-h-60 max-w-xl overflow-auto rounded bg-slate-900 p-2 text-xs text-slate-100">
                    {JSON.stringify({ inputs: e.inputs, outputs: e.outputs }, null, 2)}</pre></details></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
