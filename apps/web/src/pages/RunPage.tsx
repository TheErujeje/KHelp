import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useRun } from "../api";
import { Card, CitationList, FlagChip, LiveFeed, PatientLink, PriorityBadge } from "../components/ui";

export default function RunPage() {
  const { runId = "" } = useParams();
  const { data } = useRun(runId);
  const qc = useQueryClient();
  const running = !data || data.run.status === "RUNNING";

  // Poll the run summary while it is in progress; the feed itself is pushed over SSE.
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => qc.invalidateQueries({ queryKey: ["run", runId] }), 2000);
    return () => clearInterval(t);
  }, [running, runId, qc]);

  const run = data?.run;
  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <div className="lg:col-span-3">
        <Card title="Live tool-call feed"><LiveFeed key={runId} runId={runId} /></Card>
      </div>
      <div className="space-y-4 lg:col-span-2">
        <Card title="Run">
          {!run ? <p className="text-sm text-slate-500">Starting…</p> : (
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
              <dt className="text-slate-500">Patient</dt><dd><PatientLink id={run.patient_id} name={`#${run.patient_id}`} /></dd>
              <dt className="text-slate-500">Kind</dt><dd>{run.kind}</dd>
              <dt className="text-slate-500">Status</dt><dd className="font-semibold">{run.status}</dd>
              <dt className="text-slate-500">Model</dt><dd className="font-mono text-xs">{run.model}</dd>
              <dt className="text-slate-500">Tool calls</dt><dd>{run.tool_calls}</dd>
              <dt className="text-slate-500">Latency</dt><dd>{run.latency_ms != null ? `${(run.latency_ms / 1000).toFixed(1)} s` : "…"}</dd>
              <dt className="text-slate-500">Tokens in / out</dt><dd>{run.input_tokens ?? "…"} / {run.output_tokens ?? "…"}</dd>
              {run.error && <><dt className="text-slate-500">Error</dt><dd className="text-red-700">{run.error}</dd></>}
            </dl>
          )}
        </Card>
        {data?.proposals.map((p) => (
          <Card key={p.id} title={<>Proposal <PriorityBadge priority={p.priority} /> <span className="text-sm font-normal text-slate-500">{p.status}</span></>}
            actions={p.status === "PENDING" && <Link to="/approvals" className="text-sm font-semibold text-teal-800 hover:underline">Review & approve →</Link>}>
            <p className="mb-3 text-sm">{p.rationale}</p>
            <CitationList citations={p.citations} />
          </Card>
        ))}
        {data?.flags.map((f) => (
          <Card key={f.id} title={<FlagChip flag={f} />}
            actions={<Link to="/approvals" className="text-sm font-semibold text-teal-800 hover:underline">Acknowledge →</Link>}>
            <p className="text-sm">{f.reason}</p>
          </Card>
        ))}
        {run && !running && run.final_message && (
          <Card title="Agent's closing message (log only)">
            <p className="text-sm text-slate-600">{run.final_message}</p>
            <p className="mt-2 text-xs text-slate-400">Not authoritative: the proposal above is what the server validated.</p>
          </Card>
        )}
      </div>
    </div>
  );
}
