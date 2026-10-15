import { useState } from "react";
import { Check, ChevronDown, ChevronRight, PenLine } from "lucide-react";
import {
  PRIORITIES, useAcknowledge, useApprove, useOverride, type Flag, type Priority, type Proposal,
} from "../api";
import { ROLE_CODE, isSenior, useClinician } from "../auth";
import { priorityRank } from "../lib";
import { CitationList, ErrorText, FlagChip, PriorityBadge, WhySummary } from "./ui";

const QUICK_REASONS = [
  "Clinical appearance worse than scored",
  "Vitals re-taken at the desk",
  "Emergency sign matched wrongly",
  "Emergency sign missed",
];

/** Review a PENDING proposal: why, the evidence, then Approve or Override as the signed-in clinician. */
export function ProposalReview({ proposal, noteText, onDone }: {
  proposal: Proposal; noteText?: string | null; onDone?: () => void;
}) {
  const me = useClinician();
  const approve = useApprove();
  const override = useOverride();
  const [showEvidence, setShowEvidence] = useState(false);
  const [overriding, setOverriding] = useState(false);
  const [newPriority, setNewPriority] = useState<Priority | null>(null);
  const [reason, setReason] = useState("");
  const pending = proposal.status === "PENDING";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <PriorityBadge priority={proposal.priority} size="xl" />
        <div className="text-sm">
          <div className="font-semibold">Proposed priority</div>
          <div className="text-ink-3">{pending ? "Waiting for your approval. The queue has not changed." : proposal.status}</div>
        </div>
      </div>

      <div className="rounded-lg border border-line bg-white p-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">Why</div>
        <WhySummary citations={proposal.citations} priority={proposal.priority} />
        <p className="mt-2 text-sm text-ink-2">{proposal.rationale}</p>
      </div>

      {noteText && (
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-3">Note as written</div>
          <pre className="whitespace-pre-wrap rounded-lg bg-slate-100 p-3 font-mono text-xs text-ink-2">{noteText}</pre>
        </div>
      )}

      <div>
        <button onClick={() => setShowEvidence(!showEvidence)} className="flex items-center gap-1 text-sm font-semibold text-brand">
          {showEvidence ? <ChevronDown size={16} /> : <ChevronRight size={16} />} Full evidence and sources
        </button>
        {showEvidence && <div className="mt-3"><CitationList citations={proposal.citations} /></div>}
      </div>

      {pending && (
        <div className="space-y-3 border-t border-line pt-4">
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-primary px-5 py-2.5" disabled={approve.isPending}
              onClick={() => approve.mutate({ id: proposal.id, clinician_name: me.name, clinician_role: ROLE_CODE[me.role] },
                { onSuccess: onDone })}>
              <Check size={16} /> Approve {proposal.priority}
            </button>
            <button className="btn-secondary py-2.5" onClick={() => setOverriding(!overriding)}>
              <PenLine size={16} /> Change priority
            </button>
            <span className="text-xs text-ink-3">as {me.name}, {me.role}</span>
          </div>

          {overriding && (
            <form className="space-y-3 rounded-lg border border-line bg-white p-4" onSubmit={(e) => {
              e.preventDefault();
              if (!newPriority) return;
              override.mutate({ id: proposal.id, clinician_name: me.name, clinician_role: ROLE_CODE[me.role],
                                priority: newPriority, reason: reason.trim() }, { onSuccess: onDone });
            }}>
              <div>
                <div className="mb-1.5 text-xs font-semibold text-ink-2">New priority</div>
                <div className="flex flex-wrap gap-2">
                  {PRIORITIES.map((p) => {
                    const lower = priorityRank(p) < priorityRank(proposal.priority);
                    const blocked = lower && !isSenior(me.role);
                    return (
                      <button type="button" key={p} disabled={blocked} onClick={() => setNewPriority(p)}
                        title={blocked ? "Lowering needs a doctor or senior nurse" : undefined}
                        className={`rounded-lg p-1 ring-2 transition disabled:cursor-not-allowed disabled:opacity-30 ${
                          newPriority === p ? "ring-ink" : "ring-transparent hover:ring-line"}`}>
                        <PriorityBadge priority={p} size="lg" />
                      </button>
                    );
                  })}
                </div>
                {!isSenior(me.role) && (
                  <p className="mt-1.5 text-xs text-ink-3">
                    You can raise the priority. Lowering it below the SATS result needs a doctor or senior nurse
                    (SATS manual p.6, senior healthcare professional's discretion).
                  </p>
                )}
              </div>
              <div>
                <div className="mb-1.5 text-xs font-semibold text-ink-2">Reason (required)</div>
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {QUICK_REASONS.map((r) => (
                    <button type="button" key={r} onClick={() => setReason(r)}
                      className={`rounded-full border px-2.5 py-1 text-xs ${reason === r ? "border-brand bg-brand-soft text-teal-900" : "border-line hover:bg-slate-50"}`}>
                      {r}</button>
                  ))}
                </div>
                <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className="input"
                  placeholder="Or write your reason" />
              </div>
              <button className="btn-primary bg-ink hover:bg-slate-800" disabled={!newPriority || reason.trim().length < 3 || override.isPending}>
                Confirm {newPriority ?? "new priority"}
              </button>
            </form>
          )}
          <ErrorText error={approve.error ?? override.error} />
        </div>
      )}
    </div>
  );
}

/** Acknowledge a re-check flag. MANUAL_TRIAGE flags also let the clinician set the priority themselves. */
export function FlagReview({ flag, onDone }: { flag: Flag; onDone?: () => void }) {
  const me = useClinician();
  const ack = useAcknowledge();
  const [note, setNote] = useState("");
  const [priority, setPriority] = useState<Priority | null>(null);
  const manual = flag.flag_type === "MANUAL_TRIAGE";
  const canSetPriority = manual && isSenior(me.role);
  const d = flag.details as { previous_tews?: { min: number; max: number }; new_tews?: { min: number; max: number };
    definitely_worse?: boolean; outstanding_inputs?: string[] };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2"><FlagChip flag={flag} /></div>
      <p className="text-sm">{flag.reason}</p>
      {d.new_tews && (
        <p className="text-sm text-ink-2">
          TEWS {d.previous_tews ? `${d.previous_tews.min}–${d.previous_tews.max} → ` : ""}{d.new_tews.min}–{d.new_tews.max}
          {d.definitely_worse && <span className="ml-2 font-semibold text-red-700">definitely worse</span>}
        </p>
      )}
      {d.outstanding_inputs && d.outstanding_inputs.length > 0 && (
        <p className="text-sm text-amber-800">Please record: {d.outstanding_inputs.join(", ")}</p>
      )}
      {flag.status === "PENDING" && (
        <form className="space-y-3 border-t border-line pt-3" onSubmit={(e) => {
          e.preventDefault();
          ack.mutate({ id: flag.id, clinician_name: me.name, clinician_role: ROLE_CODE[me.role],
                       note: note.trim() || undefined,
                       priority: canSetPriority && priority ? priority : undefined }, { onSuccess: onDone });
        }}>
          {manual && !canSetPriority && (
            <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
              This patient is outside the adult scale (child, or no age recorded). Hand over to a doctor or senior
              nurse to set the priority.
            </p>
          )}
          {canSetPriority && (
            <div>
              <div className="mb-1.5 text-xs font-semibold text-ink-2">Your priority for this patient</div>
              <div className="flex flex-wrap gap-2">
                {PRIORITIES.map((p) => (
                  <button type="button" key={p} onClick={() => setPriority(p)}
                    className={`rounded-lg p-1 ring-2 ${priority === p ? "ring-ink" : "ring-transparent hover:ring-line"}`}>
                    <PriorityBadge priority={p} size="lg" />
                  </button>
                ))}
              </div>
            </div>
          )}
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional)" className="input" />
          {(!manual || canSetPriority) && (
            <button className="btn-primary" disabled={ack.isPending || (canSetPriority && !priority)}>
              <Check size={16} /> {canSetPriority ? `Set ${priority ?? "priority"} and close flag` : "Acknowledge"}
            </button>
          )}
          <ErrorText error={ack.error} />
        </form>
      )}
    </div>
  );
}
