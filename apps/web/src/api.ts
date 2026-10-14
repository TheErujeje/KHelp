// Typed client for the Klaudesk API, plus TanStack Query hooks.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export type Priority = "RED" | "ORANGE" | "YELLOW" | "GREEN";
export const PRIORITIES: Priority[] = ["RED", "ORANGE", "YELLOW", "GREEN"];

export interface Source { document: string; edition: string; location: string }

export interface Patient {
  id: number;
  display_name: string;
  age_years: number | null;
  arrived_at: string;
  wait_minutes: number;
  status: string;
  approved_priority: Priority | null;
  approved_by: string | null;
  approved_at: string | null;
  is_synthetic: boolean;
}

export interface Flag {
  id: number;
  patient_id: number;
  run_id: string | null;
  flag_type: "MISSING_VITALS" | "DETERIORATION" | "MANUAL_TRIAGE" | "OTHER";
  reason: string;
  details: Record<string, unknown>;
  status: string;
  created_at: string;
}

export interface QueueRow extends Patient {
  pending_proposal: { id: number; priority: Priority } | null;
  pending_flags: Flag[];
  latest_run: { id: string; status: string; kind: string } | null;
}

export type Citation =
  | { type: "vital"; parameter: string; label: string; value: string | number; unit: string | null;
      band_id: string; band: string; points: number; source: Source; verified: boolean }
  | { type: "tews_rule"; rule_id: string; priority: Priority; range: [number, number | null];
      tews_total: number | null; tews_min: number; tews_max: number; source: Source; verified: boolean }
  | { type: "discriminator"; discriminator_id: string; name: string; priority: Priority;
      matched_phrase: string; clause: string; source: Source; verified: boolean }
  | { type: "missing_inputs_rule"; rule_id: string; outstanding_inputs: string[];
      priority_low: Priority; priority_high: Priority; source: Source; verified: boolean };

export interface Proposal {
  id: number;
  patient_id: number;
  run_id: string | null;
  priority: Priority;
  status: string;
  citations: Citation[];
  decision: { outcome: string; reasons: string[]; outstanding_inputs: string[]; age_years?: number | null };
  rationale: string;
  needs_recheck: boolean;
  created_at: string;
}

export interface PendingProposal extends Proposal { patient: Patient; note_text: string | null }
export interface PendingFlag extends Flag { patient: Patient }

export interface Run {
  id: string;
  patient_id: number;
  kind: string;
  status: string;
  model: string;
  started_at: string;
  finished_at: string | null;
  tool_calls: number;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_ms: number | null;
  final_message: string | null;
  error: string | null;
}

export interface AuditEntry {
  id: number;
  created_at: string;
  run_id: string | null;
  patient_id: number | null;
  event_type: string;
  source: string;
  tool_name: string | null;
  inputs: Record<string, unknown> | null;
  outputs: Record<string, unknown> | null;
  is_error: boolean;
  model: string | null;
  latency_ms: number | null;
  actor: string | null;
}

export interface PatientDetail {
  patient: Patient;
  intakes: { id: number; kind: string; note_text: string; created_at: string }[];
  vitals: { id: number; raw: Record<string, unknown>; tews_total: number | null; tews_min: number; tews_max: number; created_at: string }[];
  proposals: Proposal[];
  flags: Flag[];
  approvals: { id: number; clinician_name: string; action: string; priority: Priority | null; reason: string | null; created_at: string }[];
  runs: Run[];
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      const detail = body.detail;
      message = Array.isArray(detail) ? detail.map((d: { msg: string }) => d.msg).join("; ") : String(detail);
    } catch { /* keep statusText */ }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

// ---------------------------------------------------------------- queries

export const useQueue = () =>
  useQuery({ queryKey: ["queue"], queryFn: () => request<{ patients: QueueRow[] }>("/queue"),
             refetchInterval: 5000 });

export const usePendingProposals = () =>
  useQuery({ queryKey: ["proposals", "PENDING"],
             queryFn: () => request<{ proposals: PendingProposal[] }>("/proposals?status=PENDING"),
             refetchInterval: 5000 });

export const usePendingFlags = () =>
  useQuery({ queryKey: ["flags", "PENDING"], queryFn: () => request<{ flags: PendingFlag[] }>("/flags?status=PENDING"),
             refetchInterval: 5000 });

export const usePatient = (id: number) =>
  useQuery({ queryKey: ["patient", id], queryFn: () => request<PatientDetail>(`/patients/${id}`),
             refetchInterval: 5000 });

export const useRun = (id: string) =>
  useQuery({ queryKey: ["run", id], queryFn: () => request<{ run: Run; proposals: Proposal[]; flags: Flag[] }>(`/runs/${id}`) });

export const useRulesStatus = () =>
  useQuery({ queryKey: ["rules"], queryFn: () => request<{ unverified_count: number; total: number; all_verified: boolean }>("/rules/status"),
             staleTime: 60_000 });

export const useHealth = () =>
  useQuery({ queryKey: ["health"], queryFn: () => request<{ ok: boolean; model: string }>("/health"), staleTime: 60_000 });

export function auditQueryString(filters: Record<string, string>) {
  const params = new URLSearchParams(Object.entries(filters).filter(([, v]) => v !== ""));
  return params.toString();
}

export const useAudit = (filters: Record<string, string>) =>
  useQuery({ queryKey: ["audit", filters],
             queryFn: () => request<{ entries: AuditEntry[] }>(`/audit?${auditQueryString({ limit: "500", ...filters })}`) });

// ---------------------------------------------------------------- mutations

function useInvalidateAll() {
  const qc = useQueryClient();
  return () => {
    for (const key of ["queue", "proposals", "flags", "patient", "audit"]) qc.invalidateQueries({ queryKey: [key] });
  };
}

export function useCreateIntake() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (body: { note_text: string; display_name?: string }) =>
      post<{ patient_id: number; intake_id: number; run_id: string }>("/intakes", body),
    onSuccess: invalidate,
  });
}

export function useCreateRecheck(patientId: number) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (body: { note_text: string }) =>
      post<{ patient_id: number; run_id: string }>(`/patients/${patientId}/recheck`, body),
    onSuccess: invalidate,
  });
}

export function useApprove() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, clinician_name }: { id: number; clinician_name: string }) =>
      post(`/proposals/${id}/approve`, { clinician_name }),
    onSuccess: invalidate,
  });
}

export function useOverride() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; clinician_name: string; priority: Priority; reason: string }) =>
      post(`/proposals/${id}/override`, body),
    onSuccess: invalidate,
  });
}

export function useAcknowledge() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; clinician_name: string; note?: string; priority?: Priority }) =>
      post(`/flags/${id}/acknowledge`, body),
    onSuccess: invalidate,
  });
}

export function useScorePatient() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (id: number) => post<{ patient_id: number; run_id: string }>(`/patients/${id}/score`, {}),
    onSuccess: invalidate,
  });
}

export function useMarkSeen() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, clinician_name }: { id: number; clinician_name: string }) =>
      post(`/patients/${id}/seen`, { clinician_name }),
    onSuccess: invalidate,
  });
}
