import { useSearchParams } from "react-router-dom";
import { usePendingFlags, usePendingProposals } from "../api";
import { FlagReview, ProposalReview } from "../components/Review";
import { Card, ErrorText, PageHeader, PatientLink, PriorityBadge } from "../components/ui";
import { waitLabel } from "../lib";

export default function Approvals() {
  const proposals = usePendingProposals();
  const flags = usePendingFlags();
  const [params, setParams] = useSearchParams();
  const tab: "proposals" | "flags" = params.get("tab") === "flags" ? "flags" : "proposals";
  const setTab = (t: "proposals" | "flags") => setParams(t === "flags" ? { tab: "flags" } : {});
  const pList = proposals.data?.proposals ?? [];
  const fList = flags.data?.flags ?? [];

  return (
    <>
      <PageHeader title="Approvals" subtitle="Nothing moves in the queue until it is approved here or from the queue." />
      <div className="mb-4 inline-flex rounded-lg bg-slate-200/60 p-1">
        {([["proposals", `Priority proposals (${pList.length})`], ["flags", `Re-check flags (${fList.length})`]] as const).map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`rounded-md px-3 py-1.5 text-sm font-semibold ${tab === k ? "bg-white shadow-card" : "text-ink-2"}`}>{label}</button>
        ))}
      </div>

      {tab === "proposals" && (
        <div className="space-y-4">
          <ErrorText error={proposals.error} />
          {pList.length === 0 && <Empty text="No proposals waiting." />}
          {pList.map((p) => (
            <Card key={p.id}
              title={<span className="flex items-center gap-2"><PatientLink id={p.patient.id} name={p.patient.display_name} />
                <PriorityBadge priority={p.patient.approved_priority} size="sm" /></span>}
              subtitle={`Waiting ${waitLabel(p.patient.wait_minutes)} · proposal #${p.id}`}>
              <ProposalReview proposal={p} noteText={p.note_text} />
            </Card>
          ))}
        </div>
      )}

      {tab === "flags" && (
        <div className="space-y-4">
          <ErrorText error={flags.error} />
          {fList.length === 0 && <Empty text="No open flags." />}
          {fList.map((f) => (
            <Card key={f.id}
              title={<span className="flex items-center gap-2"><PatientLink id={f.patient.id} name={f.patient.display_name} />
                <span className="text-xs font-normal text-ink-3">current</span><PriorityBadge priority={f.patient.approved_priority} size="sm" /></span>}
              subtitle={`Raised ${new Date(f.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}>
              <FlagReview flag={f} />
            </Card>
          ))}
        </div>
      )}
    </>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="card p-10 text-center text-sm text-ink-3">{text}</div>;
}
