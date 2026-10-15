import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Activity, CheckCircle2 } from "lucide-react";
import { useCreateRecheck, useMarkSeen, usePatient } from "../api";
import { ROLE_CODE, useClinician } from "../auth";
import { FlagReview, ProposalReview } from "../components/Review";
import { Card, ErrorText, FlagChip, PageHeader, PriorityBadge } from "../components/ui";
import { waitLabel } from "../lib";

export default function PatientPage() {
  const id = Number(useParams().patientId);
  const { data, error } = usePatient(id);
  const recheck = useCreateRecheck(id);
  const seen = useMarkSeen();
  const navigate = useNavigate();
  const me = useClinician();
  const [note, setNote] = useState("");

  if (error) return <ErrorText error={error} />;
  if (!data) return <p className="text-sm text-ink-3">Loading…</p>;
  const p = data.patient;
  const waiting = p.status === "WAITING" || p.status === "IN_CONSULT";
  const pending = data.proposals.filter((x) => x.status === "PENDING");
  const openFlags = data.flags.filter((f) => f.status === "PENDING");

  return (
    <>
      <PageHeader title={p.display_name} back="/queue"
        subtitle={`${p.is_synthetic ? "Synthetic patient · " : ""}${p.status.toLowerCase()} · waiting ${waitLabel(p.wait_minutes)}`}
        actions={waiting && (
          <button className="btn-secondary" disabled={seen.isPending} onClick={() => seen.mutate({ id, clinician_name: me.name, clinician_role: ROLE_CODE[me.role] })}>
            <CheckCircle2 size={16} /> Mark seen</button>
        )} />
      <ErrorText error={seen.error} />

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card title="Approved priority">
            <div className="flex items-center gap-3">
              <PriorityBadge priority={p.approved_priority} size="xl" />
              {p.approved_by && <span className="text-sm text-ink-2">by <b>{p.approved_by}</b>
                {p.approved_at && `, ${new Date(p.approved_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}</span>}
            </div>
          </Card>

          {pending.map((pr) => (
            <Card key={pr.id} title="Waiting for approval"><ProposalReview proposal={pr} /></Card>
          ))}
          {openFlags.map((f) => <Card key={f.id} title="Open flag"><FlagReview flag={f} /></Card>)}

          <Card title="Notes">
            <ul className="space-y-3">
              {data.intakes.map((i) => (
                <li key={i.id}>
                  <div className="mb-1 text-xs text-ink-3">{i.kind === "RECHECK" ? "Re-check" : "Intake"} · {new Date(i.created_at).toLocaleString()}</div>
                  <pre className="whitespace-pre-wrap rounded-lg bg-slate-100 p-3 font-mono text-xs">{i.note_text}</pre>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <div className="space-y-5">
          <Card title="Re-check while waiting" subtitle="If worse, a second-look flag is raised. The patient is never moved automatically.">
            {!waiting ? <p className="text-sm text-ink-3">Patient is no longer waiting.</p> : (
              <form className="space-y-3" onSubmit={(e) => {
                e.preventDefault();
                recheck.mutate({ note_text: note.trim() }, { onSuccess: (r) => navigate(`/runs/${r.run_id}`) });
              }}>
                <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={4} required className="input font-mono"
                  placeholder="now drowsy, RR 28 PR 128 BP 88/60 T 39.4C" />
                <button className="btn-primary w-full" disabled={recheck.isPending || note.trim().length < 3}>
                  <Activity size={16} /> Re-score</button>
                <ErrorText error={recheck.error} />
              </form>
            )}
          </Card>

          <Card title="History">
            <ul className="space-y-3 text-sm">
              {data.approvals.map((a) => (
                <li key={`a${a.id}`}>
                  <b>{a.clinician_name}</b>{a.clinician_role && <span className="text-ink-3"> ({a.clinician_role.replace("_", " ").toLowerCase()})</span>} {a.action === "APPROVE" ? "approved" : a.action === "OVERRIDE" ? "overrode to" : "acknowledged"}
                  {a.priority && <> <PriorityBadge priority={a.priority} size="sm" /></>}
                  {a.reason && <div className="text-ink-2">“{a.reason}”</div>}
                  <div className="text-[11px] text-ink-3">{new Date(a.created_at).toLocaleString()}</div>
                </li>
              ))}
              {data.flags.filter((f) => f.status !== "PENDING").map((f) => (
                <li key={`f${f.id}`}><FlagChip flag={f} /> <span className="text-xs text-ink-3">closed</span></li>
              ))}
              {data.approvals.length === 0 && <li className="text-ink-3">No decisions yet.</li>}
            </ul>
          </Card>

          <Card title="Assistant runs">
            <ul className="space-y-1.5 text-sm">
              {data.runs.map((r) => (
                <li key={r.id} className="flex items-center justify-between">
                  <Link to={`/runs/${r.id}`} className="font-mono text-xs text-brand hover:underline">{r.id.slice(0, 8)}</Link>
                  <span className="text-xs text-ink-3">{r.kind.toLowerCase()} · {r.status.toLowerCase()}
                    {r.latency_ms != null && ` · ${(r.latency_ms / 1000).toFixed(0)} s`}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
