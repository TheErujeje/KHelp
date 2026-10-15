import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, DoorOpen, Timer } from "lucide-react";
import { useCallIn, useMarkSeen, useQueue, type QueueRow } from "../api";
import { ROLE_CODE, useClinician } from "../auth";
import { CitationList, ErrorText, FlagChip, PageHeader, PriorityBadge, WhySummary } from "../components/ui";
import { waitLabel } from "../lib";

/** The doctor's view: who to call next, already briefed, against the SATS target times. */
export default function NextUp() {
  const { data, error } = useQueue();
  const triaged = (data?.patients ?? []).filter((p) => p.approved_priority);
  const awaiting = (data?.patients ?? []).length - triaged.length;
  const withDoctors = data?.in_consult ?? [];
  const overdue = triaged.filter((p) => (p.target?.overdue_minutes ?? 0) > 0).length;

  return (
    <>
      <PageHeader title="Next up"
        subtitle="Triaged patients in priority order, then arrival. Timers count from triage against the SATS target time (manual p.7)." />
      <ErrorText error={error} />

      <div className="mb-4 flex flex-wrap gap-2 text-sm">
        <Pill>{triaged.length} triaged and waiting</Pill>
        {overdue > 0 && <Pill tone="red">{overdue} past SATS target time</Pill>}
        {awaiting > 0 && <Pill tone="amber">{awaiting} still at the triage desk</Pill>}
      </div>

      {withDoctors.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">In consultation</h2>
          <div className="space-y-2">{withDoctors.map((p) => <PatientCard key={p.id} p={p} inConsult />)}</div>
        </section>
      )}

      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">Waiting, call in this order</h2>
      <div className="space-y-3">
        {triaged.map((p, i) => <PatientCard key={p.id} p={p} position={i + 1} />)}
        {triaged.length === 0 && (
          <div className="card p-10 text-center text-sm text-ink-3">No triaged patients waiting.</div>
        )}
      </div>
    </>
  );
}

function Pill({ children, tone }: { children: React.ReactNode; tone?: "red" | "amber" }) {
  const cls = tone === "red" ? "bg-red-50 text-red-700 ring-red-200" : tone === "amber"
    ? "bg-amber-50 text-amber-800 ring-amber-200" : "bg-white text-ink-2 ring-line";
  return <span className={`rounded-full px-3 py-1 font-semibold ring-1 ${cls}`}>{children}</span>;
}

function TargetTimer({ t }: { t: NonNullable<QueueRow["target"]> }) {
  const over = t.overdue_minutes > 0;
  const pct = t.minutes === 0 ? 100 : Math.min(100, (t.since_triage_minutes / t.minutes) * 100);
  return (
    <div className="min-w-44">
      <div className={`flex items-center gap-1.5 text-sm font-semibold ${over ? "text-red-700" : "text-ink"}`}>
        <Timer size={14} />
        {over ? `${waitLabel(t.overdue_minutes)} over target` : `${waitLabel(t.since_triage_minutes)} since triage`}
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full ${over ? "bg-red-500" : pct > 75 ? "bg-amber-400" : "bg-brand"}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-0.5 text-[11px] text-ink-3">SATS target {t.label}</div>
    </div>
  );
}

function PatientCard({ p, position, inConsult = false }: { p: QueueRow; position?: number; inConsult?: boolean }) {
  const me = useClinician();
  const call = useCallIn();
  const seen = useMarkSeen();
  const [open, setOpen] = useState(position === 1);
  const worse = p.pending_flags.some((f) => f.flag_type === "DETERIORATION");
  const decided = p.decided_proposal;
  const who = { id: p.id, clinician_name: me.name, clinician_role: ROLE_CODE[me.role] };

  return (
    <article className={`card overflow-hidden ${worse ? "ring-2 ring-red-300" : ""}`}>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3 p-4">
        {position && <span className="w-6 text-center font-mono text-lg font-bold text-ink-3">{position}</span>}
        <PriorityBadge priority={p.approved_priority} size="lg" />
        <div className="min-w-48 flex-1">
          <Link to={`/patients/${p.id}`} className="font-semibold hover:text-brand">{p.display_name}</Link>
          <div className="text-xs text-ink-3">
            arrived {new Date(p.arrived_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            {p.approved_by && ` · triaged by ${p.approved_by}`}
            {decided?.status === "OVERRIDDEN" && ` · changed from ${decided.proposed}`}
            {inConsult && p.called_by && ` · with ${p.called_by}`}
          </div>
        </div>
        {p.target && !inConsult && <TargetTimer t={p.target} />}
        <div className="flex flex-wrap gap-1">
          {worse && <span className="inline-flex items-center gap-1 rounded-full bg-red-600 px-2 py-0.5 text-[11px] font-bold text-white">
            <AlertTriangle size={11} /> Worse since triage</span>}
          {p.pending_flags.filter((f) => f.flag_type !== "DETERIORATION").map((f) => <FlagChip key={f.id} flag={f} />)}
        </div>
        <div className="flex gap-2">
          {inConsult ? (
            <button className="btn-secondary" disabled={seen.isPending} onClick={() => seen.mutate(who)}>
              <CheckCircle2 size={16} /> Seen</button>
          ) : (
            <button className="btn-primary" disabled={call.isPending} onClick={() => call.mutate(who)}>
              <DoorOpen size={16} /> Call in</button>
          )}
        </div>
      </div>

      <button onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-1 border-t border-line bg-slate-50/60 px-4 py-2 text-left text-xs font-semibold text-ink-2">
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Brief: complaint, vitals and why this priority
      </button>
      {open && (
        <div className="grid gap-4 border-t border-line p-4 lg:grid-cols-2">
          <div className="space-y-3">
            {p.note_text && (
              <div>
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-3">Note as written at triage</div>
                <pre className="whitespace-pre-wrap rounded-lg bg-slate-100 p-3 font-mono text-xs">{p.note_text}</pre>
              </div>
            )}
            {decided && p.approved_priority && (
              <div>
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-3">Why</div>
                <WhySummary citations={decided.citations} priority={decided.proposed} />
                {decided.status === "OVERRIDDEN" && (
                  <p className="mt-1 text-xs text-ink-2">Changed to <b>{p.approved_priority}</b> by {p.approved_by}.</p>
                )}
              </div>
            )}
            {p.pending_flags.map((f) => <p key={f.id} className="text-sm text-red-700">{f.reason}</p>)}
          </div>
          {decided && <CitationList citations={decided.citations} />}
        </div>
      )}
      <ErrorText error={call.error ?? seen.error} />
    </article>
  );
}
