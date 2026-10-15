// Demo sign-in. There are no real accounts: the session only records who is at
// the desk, so every approval and override is attributed to a named clinician.
// A real deployment would put the hospital's identity provider here.

import { createContext, useContext, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

export type Role = "Triage nurse" | "Doctor" | "Senior nurse";
export const ROLES: Role[] = ["Triage nurse", "Doctor", "Senior nurse"];
export type RoleCode = "TRIAGE_NURSE" | "DOCTOR" | "SENIOR_NURSE";
export const ROLE_CODE: Record<Role, RoleCode> = {
  "Triage nurse": "TRIAGE_NURSE", Doctor: "DOCTOR", "Senior nurse": "SENIOR_NURSE",
};
/** SATS p.6: lowering a priority or setting a manual-triage priority is a senior decision. */
export const isSenior = (role: Role) => role === "Doctor" || role === "Senior nurse";
/** Where each role starts after sign-in. */
export const HOME: Record<Role, string> = { "Triage nurse": "/triage", Doctor: "/next", "Senior nurse": "/next" };

export interface Clinician { name: string; role: Role; signedInAt: string }

function validRole(value: unknown): value is Role {
  return typeof value === "string" && (ROLES as string[]).includes(value);
}

interface AuthValue {
  user: Clinician | null;
  signIn: (name: string, role: Role) => void;
  signOut: () => void;
}

const KEY = "khelp.session";
const AuthContext = createContext<AuthValue | null>(null);

function readSession(): Clinician | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    const parsed = raw ? (JSON.parse(raw) as Clinician) : null;
    return parsed && validRole(parsed.role) ? parsed : null;  // old sessions with retired roles sign in again
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Clinician | null>(readSession);

  const signIn = (name: string, role: Role) => {
    const next = { name: name.trim(), role, signedInAt: new Date().toISOString() };
    setUser(next);
    try { sessionStorage.setItem(KEY, JSON.stringify(next)); } catch { /* storage unavailable */ }
  };
  const signOut = () => {
    setUser(null);
    try { sessionStorage.removeItem(KEY); } catch { /* storage unavailable */ }
  };

  return <AuthContext.Provider value={{ user, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth outside AuthProvider");
  return value;
}

/** The signed-in clinician. Only use inside <RequireAuth>. */
export function useClinician(): Clinician {
  const { user } = useAuth();
  if (!user) throw new Error("not signed in");
  return user;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/sign-in" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}
