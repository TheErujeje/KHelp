import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./auth";
import Layout from "./components/Layout";
import Approvals from "./pages/Approvals";
import AuditPage from "./pages/AuditPage";
import Dashboard from "./pages/Dashboard";
import PatientPage from "./pages/PatientPage";
import RunPage from "./pages/RunPage";
import SignIn from "./pages/SignIn";
import TriageDesk from "./pages/TriageDesk";

export default function App() {
  return (
    <Routes>
      <Route path="/sign-in" element={<SignIn />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<Dashboard />} />
        <Route path="triage" element={<TriageDesk />} />
        <Route path="approvals" element={<Approvals />} />
        <Route path="patients/:patientId" element={<PatientPage />} />
        <Route path="runs/:runId" element={<RunPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
