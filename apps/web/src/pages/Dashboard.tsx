import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle, ClipboardCheck, Clock, Plus, Users } from "lucide-react";
import { usePendingFlags, usePendingProposals, useQueue, useScorePatient, type Priority, type QueueRow } from "../api";
import { FlagReview, ProposalReview } from "../components/Review";
import { Drawer, ErrorText, FlagChip, PageHeader, PriorityBadge } from "../components/ui";
import { waitLabel } from "../lib";

const ROW_ACCENT: Record<Priority, string> = {
  RED: "bg-sats-red", ORANGE: "bg-sats-orange", YELLOW: "bg-sats-yellow", GREEN: "bg-sats-green",
};

type Review = { kind: "proposal"; id: number } | { kind: "flag"; id: number } | null;

export default function Dashboard() {
  const queue = useQueue();
  const proposals = usePendingProposals();
  const flags = usePendingFlags();
  const [review, setReview] = useState<Review>(null);

  const rows = queue.data?.patients ?? [];
  const pendingCount = proposals.data?.proposals.length ?? 0;
  const flagCount = flags.data?.flags.length ?? 0;
  const urgent = rows.filter((r) => r.approved_priority === "RED" || r.approved_priority === "ORANGE").length;
  const longest = rows.reduce((m, r) => Math.max(m, r.wait_minutes), 0);

  const proposal = review?.kind === "proposal" ? proposals.data?.proposals.find((p) => p.id === review.id) : undefined;
  const flag = review?.kind === "flag" ? flags.data?.flags.find((f) => f.id === review.id) : undefined;

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Waiting patients, ordered by approved priority, then arrival."
        actions={<Link to="/triage" className="btn-primary"><Plus size={16} /> New patient</Link>} />

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat icon={Users} label="Waiting" value={rows.length} />
        <Stat icon={ClipboardCheck} label="Awaiting approval" value={pendingCount} tone={pendingCount ? "amber" : undefined}
          to="/approvals" />
        <Stat icon={AlertTriangle} label="Open flags" value={flagCount} tone={flagCount ? "red" : undefined} to="/approvals" />
        <Stat icon={Clock} label="Longest wait" value={rows.length ? waitLabel(longest) : "—"} hint={`${urgent} RED/ORANGE waiting`} />
      </div>

      <section className="card overflow-hidden">
        <ErrorText error={queue.error} />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-slate-50 text-[11px] uppercase tracking-wide text-ink-3">
              <tr>
                <th className="w-1 p-0" />
                <th className="px-4 py-3">#</th>
                <th className="px-4 py-3">Patient</th>
                <th className="px-4 py-3">Waiting</th>
                <th className="px-4 py-3">Priority</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => <QueueLine key={r.id} r={r} pos={i + 1} onReview={setReview} />)}
              {rows.length === 0 && !queue.isLoading && (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-ink-3">No one is waiting.
                  <Link to="/triage" className="ml-1 font-semibold text-brand">Add a patient</Link></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <Drawer open={!!review} onClose={() => setReview(null)}
        title={proposal ? proposal.patient.display_name : flag ? flag.patient.display_name : "Review"}>
        {proposal && <ProposalReview proposal={proposal} noteText={proposal.note_text} onDone={() => setReview(null)} />}
        {flag && <FlagReview flag={flag} onDone={() => setReview(null)} />}
        {review && !proposal && !flag && <p className="text-sm text-ink-3">This item has already been handled.</p>}
      </Drawer>
    </>
  );
}

function QueueLine({ r, pos, onReview }: { r: QueueRow; pos: number; onReview: (r: Review) => void }) {
  const scoring = r.latest_run?.status === "RUNNING";
  const firstFlag = r.pending_flags[0];
  const score = useScorePatient();
  const navigate = useNavigate();
  const unscored = !r.latest_run && !r.approved_priority;
  return (
    <tr className="border-b border-line last:border-0 hover:bg-slate-50/60">
      <td className={`w-1 p-0 ${r.approved_priority ? ROW_ACCENT[r.approved_priority] : "bg-slate-200"}`} />
      <td className="px-4 py-3 font-mono text-ink-3">{pos}</td>
      <td className="px-4 py-3">
        <Link to={`/patients/${r.id}`} className="font-semibold hover:text-brand">{r.display_name}</Link>
        <div className="text-xs text-ink-3">
          {r.age_years != null ? `${r.age_years} y · ` : ""}arrived {new Date(r.arrived_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </div>
      </td>
      <td className="px-4 py-3 tabular-nums">{waitLabel(r.wait_minutes)}</td>
      <td className="px-4 py-3">
        <PriorityBadge priority={r.approved_priority} />
        {r.approved_by && <div className="mt-0.5 text-[11px] text-ink-3">by {r.approved_by}</div>}
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {scoring && <span className="animate-pulse text-xs font-semibold text-brand">Scoring…</span>}
          {r.pending_proposal && (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-800 ring-1 ring-amber-200">
              Proposed <PriorityBadge priority={r.pending_proposal.priority} size="sm" />
            </span>
          )}
          {r.pending_flags.map((f) => <FlagChip key={f.id} flag={f} />)}
          {unscored && <span className="text-xs text-ink-3">Not scored yet</span>}
          {!unscored && !scoring && !r.pending_proposal && r.pending_flags.length === 0 && <span className="text-xs text-ink-3">—</span>}
        </div>
      </td>
      <td className="px-4 py-3 text-right">
        {r.pending_proposal ? (
          <button className="btn-primary px-3 py-1.5 text-xs" onClick={() => onReview({ kind: "proposal", id: r.pending_proposal!.id })}>
            Review</button>
        ) : firstFlag ? (
          <button className="btn-secondary px-3 py-1.5 text-xs" onClick={() => onReview({ kind: "flag", id: firstFlag.id })}>
            Review flag</button>
        ) : unscored ? (
          <button className="btn-primary px-3 py-1.5 text-xs" disabled={score.isPending}
            onClick={() => score.mutate(r.id, { onSuccess: (x) => navigate(`/runs/${x.run_id}`) })}>
            Score</button>
        ) : scoring && r.latest_run ? (
          <Link to={`/runs/${r.latest_run.id}`} className="btn-secondary px-3 py-1.5 text-xs">Watch</Link>
        ) : (
          <Link to={`/patients/${r.id}`} className="btn-secondary px-3 py-1.5 text-xs">Open</Link>
        )}
      </td>
    </tr>
  );
}

function Stat({ icon: Icon, label, value, hint, tone, to }: {
  icon: typeof Users; label: string; value: string | number; hint?: string; tone?: "amber" | "red"; to?: string;
}) {
  const ring = tone === "red" ? "text-red-600 bg-red-50" : tone === "amber" ? "text-amber-700 bg-amber-50" : "text-brand bg-brand-soft";
  const body = (
    <div className="card flex h-full items-center gap-3 p-4 transition hover:shadow-md">
      <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${ring}`}><Icon size={18} /></div>
      <div>
        <div className="text-xs text-ink-3">{label}</div>
        <div className="text-xl font-bold tabular-nums">{value}</div>
        {hint && <div className="text-[11px] text-ink-3">{hint}</div>}
      </div>
    </div>
  );
  return to ? <Link to={to} className="block h-full">{body}</Link> : body;
}
