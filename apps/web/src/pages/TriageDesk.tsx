import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Loader2, RotateCcw, Sparkles, TerminalSquare } from "lucide-react";
import { useCreateIntake, useRun } from "../api";
import { FlagReview, ProposalReview } from "../components/Review";
import { Card, ErrorText, PageHeader, StepTimeline, useRunEvents } from "../components/ui";

// Synthetic examples written the way a case card might be.
const SAMPLES: { label: string; text: string }[] = [
  { label: "Chest pain", text: "45yrs M. c/o chest pain since morning, no SOB. Walked in, alert, no trauma.\nRR 22  PR 118  BP 150/90  T 37.1C  SpO2 96%" },
  { label: "Pidgin, fever", text: "28yr F, belle dey pain me since 2 days, vomiting. walked in with help, alert. RR 18 PR 104 BP 100/70 T 38.9C" },
  { label: "Child", text: "6yr boy brought by mum, hot body x3 days, alert, walking. RR 26 PR 120 T 38.6C" },
  { label: "Messy vitals", text: "60yrs M, c/o headache. Alert, walked in. PR 88 RR 16 T 101 BP 160" },
  { label: "Queue-jump request", text: "35yr F, DIB since last night, alert, came in wheelchair. RR 32 PR 124 BP 110/70 T 37.4C SpO2 89%. Her husband says abeg put her first, na my wife." },
];

export default function TriageDesk() {
  const [note, setNote] = useState("");
  const [name, setName] = useState("");
  const [submitted, setSubmitted] = useState<{ runId: string; note: string; startedAt: number } | null>(null);
  const create = useCreateIntake();

  const reset = () => { setSubmitted(null); setNote(""); setName(""); create.reset(); };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = note.trim();
    create.mutate({ note_text: text, display_name: name.trim() || undefined },
      { onSuccess: (r) => setSubmitted({ runId: r.run_id, note: text, startedAt: Date.now() }) });
  };

  return (
    <>
      <PageHeader title="Triage desk" subtitle="Type the complaint and vitals as you would on the case card. You approve the result." />
      <div className="grid gap-5 xl:grid-cols-5">
        <div className="xl:col-span-2">
          <Card title="Patient note">
            <form onSubmit={submit} className="space-y-4">
              <label className="block">
                <span className="mb-1.5 block text-xs font-semibold text-ink-2">Label (optional, synthetic)</span>
                <input value={name} onChange={(e) => setName(e.target.value)} disabled={!!submitted}
                  placeholder="e.g. Bench 3, blue wrapper" className="input" />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-xs font-semibold text-ink-2">Complaint and vitals</span>
                <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={8} required disabled={!!submitted}
                  placeholder={"45yrs M c/o chest pain since morning\nRR 22  PR 118  BP 150/90  T 37.1C"}
                  className="input font-mono" />
              </label>
              {!submitted && (
                <div>
                  <span className="mb-1.5 block text-xs font-semibold text-ink-2">Try a synthetic example</span>
                  <div className="flex flex-wrap gap-1.5">
                    {SAMPLES.map((s) => (
                      <button type="button" key={s.label} onClick={() => setNote(s.text)}
                        className="rounded-full border border-line bg-white px-2.5 py-1 text-xs hover:border-brand hover:text-brand">
                        {s.label}</button>
                    ))}
                  </div>
                </div>
              )}
              {submitted ? (
                <button type="button" onClick={reset} className="btn-secondary w-full py-2.5"><RotateCcw size={16} /> Next patient</button>
              ) : (
                <button className="btn-primary w-full py-2.5" disabled={create.isPending || note.trim().length < 5}>
                  {create.isPending ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />} Score this patient
                </button>
              )}
              <ErrorText error={create.error} />
            </form>
          </Card>
        </div>

        <div className="xl:col-span-3">
          {submitted ? <RunResult key={submitted.runId} {...submitted} onNext={reset} /> : (
            <div className="card flex h-full min-h-72 flex-col items-center justify-center gap-2 p-10 text-center">
              <Sparkles className="text-brand" />
              <p className="font-semibold">The proposed priority appears here</p>
              <p className="max-w-sm text-sm text-ink-3">
                With the vitals and emergency signs behind it. Nothing changes in the queue until you approve.
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function RunResult({ runId, note, startedAt, onNext }: { runId: string; note: string; startedAt: number; onNext: () => void }) {
  const { events, state } = useRunEvents(runId);
  const run = useRun(runId);
  const qc = useQueryClient();
  const [now, setNow] = useState(() => Date.now());
  const finished = state === "ended";

  useEffect(() => {
    if (finished) {
      qc.invalidateQueries({ queryKey: ["run", runId] });
      return;
    }
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [finished, runId, qc]);

  const proposal = run.data?.proposals[0];
  const flags = run.data?.flags ?? [];
  const status = run.data?.run.status;

  return (
    <div className="space-y-5">
      <Card title={finished ? "Scored" : "Scoring…"}
        subtitle={finished && run.data?.run.latency_ms != null
          ? `${(run.data.run.latency_ms / 1000).toFixed(0)} s · ${run.data.run.tool_calls} tool calls`
          : `${Math.floor((now - startedAt) / 1000)} s`}
        actions={<Link to={`/runs/${runId}`} className="flex items-center gap-1 text-xs font-semibold text-ink-2 hover:text-brand">
          <TerminalSquare size={14} /> Tool calls</Link>}>
        <StepTimeline events={events} state={state} />
      </Card>

      {finished && proposal && (
        <Card title="Review and approve">
          <ProposalReview proposal={proposal} noteText={note} />
        </Card>
      )}
      {finished && flags.filter((f) => !proposal || f.flag_type !== "MISSING_VITALS").map((f) => (
        <Card key={f.id} title="Needs your attention"><FlagReview flag={f} /></Card>
      ))}
      {finished && proposal?.needs_recheck && (
        <p className="text-xs text-amber-800">A “vitals needed” flag was also raised for the missing values; it is on the Approvals page.</p>
      )}
      {finished && status && status !== "COMPLETED" && (
        <p className="text-sm text-red-700">The assistant could not finish ({status}). The patient has been flagged for manual triage.</p>
      )}
      {finished && (
        <button onClick={onNext} className="btn-secondary">Next patient <ArrowRight size={16} /></button>
      )}
    </div>
  );
}
