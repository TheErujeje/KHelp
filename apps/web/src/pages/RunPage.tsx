import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useRun } from "../api";
import { Card, FlagChip, PageHeader, PriorityBadge, StepTimeline, ToolFeed, useRunEvents } from "../components/ui";

export default function RunPage() {
  const { runId = "" } = useParams();
  return <RunView key={runId} runId={runId} />;
}

function RunView({ runId }: { runId: string }) {
  const { events, state } = useRunEvents(runId);
  const { data } = useRun(runId);
  const qc = useQueryClient();

  useEffect(() => {
    if (state === "ended") qc.invalidateQueries({ queryKey: ["run", runId] });
  }, [state, runId, qc]);

  const run = data?.run;
  return (
    <>
      <PageHeader title="Assistant run" back="/queue" subtitle={`Every tool call, as recorded in the audit log · run ${runId.slice(0, 8)}`} />
      <div className="grid gap-5 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <Card title="Tool calls" subtitle="Click a row for its exact inputs and outputs."><ToolFeed events={events} state={state} /></Card>
        </div>
        <div className="space-y-5 lg:col-span-2">
          <Card title="In plain words"><StepTimeline events={events} state={state} /></Card>
          <Card title="Run details">
            {!run ? <p className="text-sm text-ink-3">Starting…</p> : (
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm">
                <dt className="text-ink-3">Patient</dt>
                <dd><Link to={`/patients/${run.patient_id}`} className="font-semibold text-brand hover:underline">#{run.patient_id}</Link></dd>
                <dt className="text-ink-3">Kind</dt><dd>{run.kind.toLowerCase()}</dd>
                <dt className="text-ink-3">Status</dt><dd className="font-semibold">{run.status}</dd>
                <dt className="text-ink-3">Model</dt><dd className="truncate font-mono text-xs">{run.model}</dd>
                <dt className="text-ink-3">Tool calls</dt><dd>{run.tool_calls}</dd>
                <dt className="text-ink-3">Time</dt><dd>{run.latency_ms != null ? `${(run.latency_ms / 1000).toFixed(1)} s` : "…"}</dd>
                <dt className="text-ink-3">Tokens in / out</dt><dd className="tabular-nums">{run.input_tokens ?? "…"} / {run.output_tokens ?? "…"}</dd>
                {run.error && <><dt className="text-ink-3">Error</dt><dd className="text-red-700">{run.error}</dd></>}
              </dl>
            )}
          </Card>
          {data?.proposals.map((p) => (
            <Card key={p.id} title="Result">
              <div className="flex items-center gap-2 text-sm">
                Proposed <PriorityBadge priority={p.priority} /> <span className="text-ink-3">{p.status.toLowerCase()}</span>
              </div>
              <p className="mt-2 text-sm text-ink-2">{p.rationale}</p>
              {p.status === "PENDING" && <Link to="/approvals" className="mt-3 inline-block text-sm font-semibold text-brand">Review and approve →</Link>}
            </Card>
          ))}
          {data?.flags.map((f) => (
            <Card key={f.id} title="Flag raised"><FlagChip flag={f} /><p className="mt-2 text-sm">{f.reason}</p></Card>
          ))}
          {run?.final_message && run.status !== "RUNNING" && (
            <Card title="Assistant's closing message" subtitle="Log only. The result above is what the server validated.">
              <p className="text-sm text-ink-2">{run.final_message}</p>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
