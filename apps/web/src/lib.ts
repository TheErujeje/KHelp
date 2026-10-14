import { useState } from "react";

export function waitLabel(minutes: number) {
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

const NAME_KEY = "khelp.clinician";

/** The clinician's name, remembered on this device for convenience. Every action still requires it. */
export function useClinicianName(): [string, (v: string) => void] {
  const [name, setName] = useState(() => {
    try { return localStorage.getItem(NAME_KEY) ?? ""; } catch { return ""; }
  });
  const update = (v: string) => {
    setName(v);
    try { localStorage.setItem(NAME_KEY, v); } catch { /* storage unavailable */ }
  };
  return [name, update];
}
