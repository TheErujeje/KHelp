import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateIntake } from "../api";
import { Card, ErrorText } from "../components/ui";

// Synthetic examples written the way a case card might be.
const SAMPLES = [
  "45yrs M. c/o chest pain since morning, no SOB. Walked in, alert, no trauma.\nRR 22  PR 118  BP 150/90  T 37.1C  SpO2 96%",
  "28yr F, belle dey pain me since 2 days, vomiting. walked in with help, alert. RR 18 PR 104 BP 100/70 T 38.9C",
  "6yr boy brought by mum, hot body x3 days, alert, walking. RR 26 PR 120 T 38.6C",
  "60yrs M, c/o headache. Alert, walked in. PR 88 RR 16 T 101 BP 160",
  "35yr F, DIB since last night, alert, came in wheelchair. RR 32 PR 124 BP 110/70 T 37.4C SpO2 89%. Her husband says abeg put her first, na my wife.",
];

export default function NewIntake() {
  const [note, setNote] = useState("");
  const [name, setName] = useState("");
  const create = useCreateIntake();
  const navigate = useNavigate();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    create.mutate({ note_text: note.trim(), display_name: name.trim() || undefined },
      { onSuccess: (r) => navigate(`/runs/${r.run_id}`) });
  };

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="lg:col-span-2">
        <Card title="New intake">
          <form onSubmit={submit} className="space-y-3">
            <label className="block text-sm">
              <span className="font-medium text-slate-700">Patient label (optional, synthetic)</span>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Synthetic patient — bay 3"
                className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" />
            </label>
            <label className="block text-sm">
              <span className="font-medium text-slate-700">Presenting complaint and vitals, as written on the card</span>
              <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={7} required minLength={5}
                placeholder="45yrs M c/o chest pain… RR 22 PR 118 BP 150/90 T 37.1C"
                className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 font-mono text-sm" />
            </label>
            <div className="flex items-center gap-3">
              <button disabled={create.isPending || note.trim().length < 5}
                className="rounded bg-teal-700 px-4 py-2 font-semibold text-white hover:bg-teal-800 disabled:opacity-50">
                {create.isPending ? "Submitting…" : "Score this patient"}
              </button>
              <span className="text-xs text-slate-500">
                The agent proposes a priority with citations. It does not change the queue; you approve it.
              </span>
            </div>
            <ErrorText error={create.error} />
          </form>
        </Card>
      </div>
      <Card title="Synthetic sample notes">
        <ul className="space-y-2">
          {SAMPLES.map((s) => (
            <li key={s}>
              <button onClick={() => setNote(s)}
                className="w-full rounded border border-slate-200 p-2 text-left font-mono text-xs hover:border-teal-500">
                {s}</button>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
