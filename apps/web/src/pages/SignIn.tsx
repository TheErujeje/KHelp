import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Activity, BadgeCheck, FileSearch, ShieldCheck, Stethoscope } from "lucide-react";
import { ROLES, useAuth, type Role } from "../auth";

const POINTS = [
  { icon: Activity, title: "Scores with SATS", text: "TEWS and emergency signs from the vitals and complaint you already wrote." },
  { icon: FileSearch, title: "Every priority cited", text: "Each number traces to a vital, a band and a line in the SATS manual." },
  { icon: BadgeCheck, title: "You decide", text: "Nothing moves in the queue until a named nurse or doctor approves it." },
];

export default function SignIn() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/";
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("Triage nurse");
  const [staffId, setStaffId] = useState("");
  const [password, setPassword] = useState("");
  const valid = name.trim().length >= 2;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    signIn(name, role);
    navigate(from, { replace: true });
  };

  return (
    <div className="grid min-h-full lg:grid-cols-2">
      {/* Brand panel */}
      <div className="relative hidden flex-col justify-between overflow-hidden bg-sidebar-bg p-10 text-white lg:flex">
        <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-brand/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 -left-16 h-96 w-96 rounded-full bg-brand/10 blur-3xl" />
        <div className="relative flex items-center gap-2.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand">
            <Stethoscope size={22} />
          </div>
          <div>
            <div className="text-lg font-bold">KHelp</div>
            <div className="text-xs text-sidebar-text">Triage Desk</div>
          </div>
        </div>

        <div className="relative max-w-md">
          <h1 className="text-3xl font-bold leading-tight">
            Get the sickest patient seen first, <span className="text-teal-300">with the evidence on screen.</span>
          </h1>
          <ul className="mt-8 space-y-5">
            {POINTS.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-3">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/10">
                  <Icon size={16} className="text-teal-300" />
                </div>
                <div>
                  <div className="font-semibold">{title}</div>
                  <div className="text-sm text-sidebar-text">{text}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-sidebar-text">
          South African Triage Scale, adult (age 12+). Synthetic patient data only. Never a diagnosis.
        </p>
      </div>

      {/* Form panel */}
      <div className="flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand text-white"><Stethoscope size={20} /></div>
            <span className="text-lg font-bold">KHelp Triage Desk</span>
          </div>
          <h2 className="text-2xl font-bold">Sign in to the desk</h2>
          <p className="mt-1 text-sm text-ink-2">Your name is recorded on every priority you approve.</p>

          <form onSubmit={submit} className="mt-8 space-y-4">
            <Field label="Full name">
              <input value={name} onChange={(e) => setName(e.target.value)} autoFocus required placeholder="e.g. Adaeze Okafor"
                className="input" autoComplete="name" />
            </Field>
            <Field label="Role">
              <div className="grid grid-cols-3 gap-1.5 rounded-lg bg-slate-100 p-1">
                {ROLES.map((r) => (
                  <button type="button" key={r} onClick={() => setRole(r)}
                    className={`rounded-md px-2 py-1.5 text-xs font-semibold transition ${
                      role === r ? "bg-white text-ink shadow-card" : "text-ink-2 hover:text-ink"}`}>{r}</button>
                ))}
              </div>
            </Field>
            <Field label="Staff ID (optional)">
              <input value={staffId} onChange={(e) => setStaffId(e.target.value)} placeholder="e.g. OPD-0142" className="input" />
            </Field>
            <Field label="Password">
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Any value (demo)"
                className="input" autoComplete="current-password" />
            </Field>
            <button disabled={!valid}
              className="w-full rounded-lg bg-brand py-2.5 font-semibold text-white transition hover:bg-brand-hover disabled:opacity-50">
              Sign in
            </button>
          </form>

          <div className="mt-6 flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
            <ShieldCheck size={16} className="shrink-0" />
            Demo sign-in: there are no real accounts and the password is not checked. A hospital deployment would use
            its own staff login.
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold text-ink-2">{label}</span>
      {children}
    </label>
  );
}
