import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useCreateRecheck, useMarkSeen, usePatient } from "../api";
import {
  Card, CitationList, ClinicianField, ErrorText, FlagChip, PriorityBadge,
} from "../components/ui";
import { waitLabel, useClinicianName } from "../lib";

export default function PatientPage() {
  const id = Number(useParams().patientId);
  const { data, error } = usePatient(id);
  const recheck = useCreateRecheck(id);
  const seen = useMarkSeen();
  const navigate = useNavigate();
  const [clinician, setClinician] = useClinicianName();
  const [note, setNote] = useState("");

  if (error) return <ErrorText error={error} />;
  if (!data) return <p className="text-sm text-slate-500">Loading…</p>;
  const p = data.patient;
  const waiting = p.status === "WAITING";

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        <Card title={<>{p.display_name} {p.is_synthetic && <span className="ml-1 rounded bg-slate-100 px-1.5 text-xs font-normal">synthetic</span>}</>}>
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <PriorityBadge priority={p.approved_priority} size="lg" />
            <span>status <b>{p.status}</b></span>
            <span>waiting {waitLabel(p.wait_minutes)}</span>
            {p.approved_by && <span>approved by <b>{p.approved_by}</b></span>}
          </div>
        </Card>

        <Card title="Notes">
          <ul className="space-y-2">
            {data.intakes.map((i) => (
              <li key={i.id}>
                <div className="text-xs text-slate-500">{i.kind} · {new Date(i.created_at).toLocaleString()}</div>
                <pre className="whitespace-pre-wrap rounded bg-slate-50 p-2 font-mono text-xs">{i.note_text}</pre>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Proposals">
          {data.proposals.length === 0 && <p className="text-sm text-slate-500">None yet.</p>}
          <div className="space-y-4">
            {data.proposals.map((pr) => (
              <div key={pr.id} className="rounded border border-slate-200 p-3">
                <div className="mb-2 flex items-center gap-2"><PriorityBadge priority={pr.priority} />
                  <span className="text-sm text-slate-600">{pr.status} · #{pr.id}</span></div>
                <p className="mb-2 text-sm">{pr.rationale}</p>
                <CitationList citations={pr.citations} />
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="space-y-4">
        <Card title="Re-check while waiting">
          {!waiting ? <p className="text-sm text-slate-500">Patient is no longer waiting.</p> : (
            <form className="space-y-2" onSubmit={(e) => {
              e.preventDefault();
              recheck.mutate({ note_text: note.trim() }, { onSuccess: (r) => navigate(`/runs/${r.run_id}`) });
            }}>
              <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={4} required minLength={3}
                placeholder="New vitals / change, e.g. now drowsy, RR 28 PR 128 BP 88/60 T 39.4C"
                className="w-full rounded border border-slate-300 px-2 py-1.5 font-mono text-sm" />
              <button disabled={recheck.isPending || note.trim().length < 3}
                className="rounded bg-teal-700 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50">
                Re-score</button>
              <p className="text-xs text-slate-500">If worse, the agent raises a second-look flag. It never moves the patient.</p>
              <ErrorText error={recheck.error} />
            </form>
          )}
        </Card>

        <Card title="Flags">
          {data.flags.length === 0 && <p className="text-sm text-slate-500">None.</p>}
          <ul className="space-y-2">
            {data.flags.map((f) => (
              <li key={f.id} className="text-sm"><FlagChip flag={f} /> <span className="text-xs text-slate-500">{f.status}</span>
                <p className="mt-1">{f.reason}</p></li>
            ))}
          </ul>
        </Card>

        <Card title="Decisions">
          {data.approvals.length === 0 && <p className="text-sm text-slate-500">No human decisions yet.</p>}
          <ul className="space-y-2 text-sm">
            {data.approvals.map((a) => (
              <li key={a.id}><b>{a.clinician_name}</b> {a.action.toLowerCase()}
                {a.priority && <> <PriorityBadge priority={a.priority} size="sm" /></>}
                {a.reason && <span className="text-slate-600">: “{a.reason}”</span>}
                <div className="text-xs text-slate-500">{new Date(a.created_at).toLocaleString()}</div></li>
            ))}
          </ul>
        </Card>

        <Card title="Agent runs">
          <ul className="space-y-1 text-sm">
            {data.runs.map((r) => (
              <li key={r.id}><Link to={`/runs/${r.id}`} className="font-mono text-teal-800 hover:underline">{r.id.slice(0, 8)}</Link>
                {" "}{r.kind} · {r.status}{r.latency_ms != null && ` · ${(r.latency_ms / 1000).toFixed(0)} s`}</li>
            ))}
          </ul>
        </Card>

        {waiting && (
          <Card title="Seen by clinician">
            <ClinicianField value={clinician} onChange={setClinician} />
            <button disabled={clinician.trim().length < 2 || seen.isPending}
              onClick={() => seen.mutate({ id, clinician_name: clinician.trim() })}
              className="mt-2 rounded border border-slate-300 px-3 py-1.5 text-sm font-semibold disabled:opacity-50">
              Mark as seen (leaves queue)</button>
            <ErrorText error={seen.error} />
          </Card>
        )}
      </div>
    </div>
  );
}
