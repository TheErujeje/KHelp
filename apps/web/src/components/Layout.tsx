import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { ClipboardCheck, DoorOpen, LayoutDashboard, LogOut, Menu, ScrollText, Stethoscope, UserPlus, X } from "lucide-react";
import { useHealth, usePendingFlags, usePendingProposals } from "../api";
import { useAuth } from "../auth";
import { RulesBanner } from "./ui";

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { user, signOut } = useAuth();
  const proposals = usePendingProposals();
  const flags = usePendingFlags();
  const health = useHealth();
  const pending = (proposals.data?.proposals.length ?? 0) + (flags.data?.flags.length ?? 0);

  const triage = { to: "/triage", label: "Triage desk", icon: UserPlus };
  const next = { to: "/next", label: "Next up", icon: DoorOpen };
  const queue = { to: "/queue", label: "Queue", icon: LayoutDashboard };
  const approvals = { to: "/approvals", label: "Approvals", icon: ClipboardCheck, badge: pending };
  const audit = { to: "/audit", label: "Audit log", icon: ScrollText };
  // Each role sees its own work first; every page stays reachable.
  const nav: { to: string; label: string; icon: typeof UserPlus; badge?: number; end?: boolean }[] =
    user?.role === "Triage nurse" ? [triage, queue, approvals, next, audit] : [next, queue, approvals, triage, audit];

  return (
    <div className="flex h-full w-64 flex-col bg-sidebar-bg">
      <div className="flex items-center gap-2.5 border-b border-white/10 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-white"><Stethoscope size={18} /></div>
        <div>
          <div className="text-sm font-bold text-white">Klaudesk</div>
          <div className="text-[11px] text-sidebar-text">Triage Desk · OPD</div>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
        {nav.map(({ to, label, icon: Icon, end, badge }) => (
          <NavLink key={to} to={to} end={end} onClick={onNavigate}
            className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
              isActive ? "bg-sidebar-active text-white" : "text-sidebar-text hover:bg-sidebar-hover hover:text-white"}`}>
            {({ isActive }) => (
              <>
                <Icon size={17} className={isActive ? "text-teal-300" : ""} />
                {label}
                {!!badge && <span className="ml-auto rounded-full bg-amber-400 px-1.5 text-[11px] font-bold text-amber-950">{badge}</span>}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-white/10 px-3 py-4">
        {health.data && (
          <div className="mx-3 mb-3 rounded-md bg-white/5 px-2 py-1.5 font-mono text-[10px] text-sidebar-text" title="Open-weights model">
            model {health.data.model}
          </div>
        )}
        {user && (
          <div className="flex items-center gap-2.5 px-3 py-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand/20 text-xs font-bold text-teal-200">
              {user.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold text-white">{user.name}</p>
              <p className="truncate text-[11px] text-sidebar-text">{user.role}</p>
            </div>
          </div>
        )}
        <button onClick={signOut}
          className="mt-1 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-sidebar-text transition-colors hover:bg-sidebar-hover hover:text-white">
          <LogOut size={16} /> Sign out
        </button>
      </div>
    </div>
  );
}

export default function Layout() {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex h-full">
      <div className="hidden shrink-0 lg:flex"><Sidebar /></div>
      {open && (
        <div className="fixed inset-0 z-40 flex lg:hidden">
          <div className="fixed inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <div className="relative z-50">
            <Sidebar onNavigate={() => setOpen(false)} />
            <button onClick={() => setOpen(false)} className="absolute right-3 top-5 text-sidebar-text" aria-label="Close menu"><X size={18} /></button>
          </div>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="flex items-center gap-3 border-b border-line bg-white px-4 py-3 lg:hidden">
          <button onClick={() => setOpen(true)} className="text-ink-2" aria-label="Open menu"><Menu size={20} /></button>
          <span className="text-sm font-bold">Klaudesk</span>
        </div>
        <RulesBanner />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6">
          <div className="mx-auto max-w-7xl"><Outlet /></div>
        </main>
      </div>
    </div>
  );
}
