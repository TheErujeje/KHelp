import { NavLink, Route, Routes } from "react-router-dom";
import { useHealth, usePendingFlags, usePendingProposals } from "./api";
import { RulesBanner } from "./components/ui";
import Approvals from "./pages/Approvals";
import AuditPage from "./pages/AuditPage";
import NewIntake from "./pages/NewIntake";
import PatientPage from "./pages/PatientPage";
import QueueBoard from "./pages/QueueBoard";
import RunPage from "./pages/RunPage";

function Nav() {
  const proposals = usePendingProposals();
  const flags = usePendingFlags();
  const pending = (proposals.data?.proposals.length ?? 0) + (flags.data?.flags.length ?? 0);
  const link = ({ isActive }: { isActive: boolean }) =>
    `rounded px-3 py-1.5 text-sm font-semibold ${isActive ? "bg-teal-800 text-white" : "text-teal-50 hover:bg-teal-600"}`;
  return (
    <nav className="flex flex-wrap items-center gap-1">
      <NavLink to="/" end className={link}>Queue</NavLink>
      <NavLink to="/intake" className={link}>New intake</NavLink>
      <NavLink to="/approvals" className={link}>
        Approvals{pending > 0 && <span className="ml-1.5 rounded-full bg-amber-400 px-1.5 text-xs text-amber-950">{pending}</span>}
      </NavLink>
      <NavLink to="/audit" className={link}>Audit log</NavLink>
    </nav>
  );
}

export default function App() {
  const health = useHealth();
  return (
    <div className="min-h-screen">
      <RulesBanner />
      <header className="bg-teal-700">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="text-white">
            <div className="text-lg font-bold">KHelp · Triage Desk</div>
            <div className="text-xs text-teal-100">Scores and cites. Never diagnoses. A named clinician approves every priority.</div>
          </div>
          <Nav />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-5">
        <Routes>
          <Route path="/" element={<QueueBoard />} />
          <Route path="/intake" element={<NewIntake />} />
          <Route path="/approvals" element={<Approvals />} />
          <Route path="/patients/:patientId" element={<PatientPage />} />
          <Route path="/runs/:runId" element={<RunPage />} />
          <Route path="/audit" element={<AuditPage />} />
        </Routes>
      </main>
      <footer className="mx-auto max-w-6xl px-4 pb-6 text-xs text-slate-500">
        Synthetic patient data only. SATS adult scale (age 12+); paediatric triage is out of scope.
        {health.data && <> · Model: <span className="font-mono">{health.data.model}</span></>}
      </footer>
    </div>
  );
}
