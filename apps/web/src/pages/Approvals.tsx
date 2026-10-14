import { useState } from "react";
import {
  PRIORITIES, useAcknowledge, useApprove, useOverride, usePendingFlags, usePendingProposals,
  type PendingFlag, type PendingProposal, type Priority,
} from "../api";
import {
  Card, CitationList, ClinicianField, ErrorText, FlagChip, PatientLink, PriorityBadge,
} from "../components/ui";
import { waitLabel, useClinicianName } from "../lib";

export default function Approvals() {
  const [clinician, setClinician] = useClinicianName();
  const proposals = usePendingProposals();
  const flags = usePendingFlags();
  const named = clinician.trim().length >= 2;

  return (
    <div className="space-y-4">
      <Card title="Who is approving?">
        <div className="max-w-sm"><ClinicianField value={clinician} onChange={setClinician} /></div>
        <p className="mt-2 text-xs text-slate-500">
          Every approval, override and acknowledgement is recorded in the audit log under this name.
        </p>
      </Card>

      <Card title={`Pending priority proposals (${proposals.data?.proposals.length ?? 0})`}>
        <ErrorText error={proposals.error} />
        {proposals.data?.proposals.length === 0 && <p className="text-sm text-slate-500">Nothing to approve.</p>}
        <div className="space-y-4">
          {proposals.data?.proposals.map((p) => <ProposalCard key={p.id} p={p} clinician={clinician} named={named} />)}
        </div>
      </Card>

      <Card title={`Re-check flags (${flags.data?.flags.length ?? 0})`}>
        <ErrorText error={flags.error} />
        {flags.data?.flags.length === 0 && <p className="text-sm text-slate-500">No open flags.</p>}
        <div className="space-y-3">
          {flags.data?.flags.map((f) => <FlagCard key={f.id} f={f} clinician={clinician} named={named} />)}
        </div>
      </Card>
    </div>
  );
}

function ProposalCard({ p, clinician, named }: { p: PendingProposal; clinician: string; named: boolean }) {
  const approve = useApprove();
  const override = useOverride();
  const [overriding, setOverriding] = useState(false);
  const [newPriority, setNewPriority] = useState<Priority>(p.priority);
  const [reason, setReason] = useState("");

  return (
    <article className="rounded-lg border border-slate-200 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <PriorityBadge priority={p.priority} size="lg" />
        <div>
          <PatientLink id={p.patient.id} name={p.patient.display_name} />
          <div className="text-xs text-slate-500">waiting {waitLabel(p.patient.wait_minutes)} · proposal #{p.id}
            {p.decision.age_years != null && ` · age ${p.decision.age_years}`}</div>
        </div>
        {p.needs_recheck && <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">
          Proposed with vitals still to record</span>}
      </div>

      {p.note_text && (
        <pre className="mt-3 whitespace-pre-wrap rounded bg-slate-50 p-2 font-mono text-xs text-slate-700">{p.note_text}</pre>
      )}
      <p className="mt-3 text-sm"><span className="font-semibold">Agent rationale: </span>{p.rationale}</p>
      <div className="mt-3"><CitationList citations={p.citations} /></div>

      <div className="mt-4 flex flex-wrap items-start gap-2 border-t border-slate-100 pt-3">
        <button disabled={!named || approve.isPending}
          onClick={() => approve.mutate({ id: p.id, clinician_name: clinician.trim() })}
          className="rounded bg-teal-700 px-4 py-2 font-semibold text-white hover:bg-teal-800 disabled:opacity-50">
          Approve {p.priority}</button>
        <button disabled={!named} onClick={() => setOverriding(!overriding)}
          className="rounded border border-slate-300 px-4 py-2 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">
          Override…</button>
        {!named && <span className="self-center text-xs text-red-700">Enter your name above to approve or override.</span>}
      </div>
      {overriding && (
        <form className="mt-3 space-y-2 rounded bg-slate-50 p-3" onSubmit={(e) => {
          e.preventDefault();
          override.mutate({ id: p.id, clinician_name: clinician.trim(), priority: newPriority, reason: reason.trim() });
        }}>
          <div className="flex flex-wrap gap-2">
            {PRIORITIES.map((pr) => (
              <label key={pr} className="flex items-center gap-1 text-sm">
                <input type="radio" name={`prio-${p.id}`} checked={newPriority === pr} onChange={() => setNewPriority(pr)} />
                <PriorityBadge priority={pr} size="sm" />
              </label>
            ))}
          </div>
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} required minLength={3} rows={2}
            placeholder="Reason for override (required)" className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm" />
          <button disabled={override.isPending || reason.trim().length < 3}
            className="rounded bg-slate-800 px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-50">
            Confirm override to {newPriority}</button>
        </form>
      )}
      <ErrorText error={approve.error ?? override.error} />
    </article>
  );
}

function FlagCard({ f, clinician, named }: { f: PendingFlag; clinician: string; named: boolean }) {
  const ack = useAcknowledge();
  const [note, setNote] = useState("");
  const [priority, setPriority] = useState<Priority | "">("");
  const manual = f.flag_type === "MANUAL_TRIAGE";
  const details = f.details as { previous_tews?: { min: number; max: number }; new_tews?: { min: number; max: number };
    definitely_worse?: boolean; outstanding_inputs?: string[] };

  return (
    <article className="rounded-lg border border-slate-200 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <FlagChip flag={f} />
        <PatientLink id={f.patient.id} name={f.patient.display_name} />
        <span className="text-xs text-slate-500">current priority</span>
        <PriorityBadge priority={f.patient.approved_priority} size="sm" />
      </div>
      <p className="mt-2 text-sm">{f.reason}</p>
      {details.new_tews && (
        <p className="mt-1 text-xs text-slate-600">
          TEWS {details.previous_tews ? `${details.previous_tews.min}–${details.previous_tews.max} → ` : ""}
          {details.new_tews.min}–{details.new_tews.max}
          {details.definitely_worse && <span className="ml-1 font-semibold text-red-700">definitely worse</span>}
        </p>
      )}
      <form className="mt-2 flex flex-wrap items-center gap-2" onSubmit={(e) => {
        e.preventDefault();
        ack.mutate({ id: f.id, clinician_name: clinician.trim(), note: note.trim() || undefined,
                     priority: manual && priority ? priority : undefined });
      }}>
        {manual && (
          <select value={priority} onChange={(e) => setPriority(e.target.value as Priority)}
            className="rounded border border-slate-300 px-2 py-1.5 text-sm">
            <option value="">Set priority manually…</option>
            {PRIORITIES.map((pr) => <option key={pr} value={pr}>{pr}</option>)}
          </select>
        )}
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional)"
          className="min-w-48 flex-1 rounded border border-slate-300 px-2 py-1.5 text-sm" />
        <button disabled={!named || ack.isPending}
          className="rounded bg-slate-800 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50">
          Acknowledge{manual && priority ? ` + set ${priority}` : ""}</button>
      </form>
      <ErrorText error={ack.error} />
    </article>
  );
}
