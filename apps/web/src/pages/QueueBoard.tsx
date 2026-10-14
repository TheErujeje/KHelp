import { Link } from "react-router-dom";
import { useQueue, type Priority } from "../api";
import { Card, ErrorText, FlagChip, PatientLink, PriorityBadge } from "../components/ui";
import { waitLabel } from "../lib";

const ROW_ACCENT: Record<Priority, string> = {
  RED: "border-l-sats-red", ORANGE: "border-l-sats-orange", YELLOW: "border-l-sats-yellow", GREEN: "border-l-sats-green",
};

export default function QueueBoard() {
  const { data, isLoading, error } = useQueue();
  const patients = data?.patients ?? [];
  return (
    <Card title={`Waiting patients (${patients.length})`}
      actions={<span className="text-xs text-slate-500">Ordered by approved priority, then arrival · refreshes every 5 s</span>}>
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      <ErrorText error={error} />
      {patients.length === 0 && !isLoading && <p className="text-sm text-slate-500">No one is waiting.</p>}
      <ul className="space-y-2">
        {patients.map((p, i) => (
          <li key={p.id} className={`flex flex-wrap items-center gap-x-4 gap-y-2 rounded border border-slate-200 border-l-8 bg-white px-3 py-2.5 ${
            p.approved_priority ? ROW_ACCENT[p.approved_priority] : "border-l-slate-300"}`}>
            <span className="w-6 text-right font-mono text-slate-400">{i + 1}</span>
            <div className="min-w-48 flex-1">
              <PatientLink id={p.id} name={p.display_name} />
              <div className="text-xs text-slate-500">
                {p.age_years != null ? `${p.age_years} y · ` : ""}arrived {new Date(p.arrived_at).toLocaleTimeString()}
                {p.approved_by && ` · approved by ${p.approved_by}`}
              </div>
            </div>
            <div className="text-sm tabular-nums text-slate-700">waiting {waitLabel(p.wait_minutes)}</div>
            <PriorityBadge priority={p.approved_priority} />
            {p.pending_proposal && (
              <Link to="/approvals" className="text-sm text-slate-700 hover:underline">
                proposed <PriorityBadge priority={p.pending_proposal.priority} size="sm" /> awaiting approval
              </Link>
            )}
            {p.latest_run?.status === "RUNNING" && (
              <Link to={`/runs/${p.latest_run.id}`} className="animate-pulse text-sm text-teal-700 hover:underline">
                agent scoring…</Link>
            )}
            <div className="flex flex-wrap gap-1">{p.pending_flags.map((f) => <FlagChip key={f.id} flag={f} />)}</div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
