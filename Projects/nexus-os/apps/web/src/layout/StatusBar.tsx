import { StatusDot, cn, type StatusTone } from "@nexus/ui";
import { PanelBottom, PanelRight } from "lucide-react";
import { Link } from "react-router";
import { useHealth } from "../lib/queries";
import { useEvents } from "../stores/events";
import { useUi } from "../stores/ui";

const STREAM: Record<string, { tone: StatusTone; label: string }> = {
  live: { tone: "ok", label: "Live" },
  connecting: { tone: "live", label: "Connecting…" },
  reconnecting: { tone: "warn", label: "Reconnecting…" },
  unauthorized: { tone: "bad", label: "Not authorised" },
  closed: { tone: "idle", label: "Disconnected" },
};

export function StatusBar() {
  const status = useEvents((s) => s.status);
  const count = useEvents((s) => s.events.length);
  const health = useHealth();
  const { rightOpen, bottomOpen, setRight, setBottom } = useUi();
  const s = STREAM[status] ?? { tone: "idle" as const, label: status };
  const h = health.data?.status;
  const hTone: StatusTone = health.isError ? "bad" : h === "ok" ? "ok" : h === "degraded" ? "warn" : h === "down" ? "bad" : "idle";
  const hLabel = health.isError ? "Backend unreachable" : h === "ok" ? "All systems normal" : h === "degraded" ? "Degraded" : h === "down" ? "System down" : "Checking…";

  return (
    <footer className="flex h-7 shrink-0 items-center gap-4 border-t border-line bg-surface px-3 text-[11px] text-fg-muted">
      <span className="inline-flex items-center gap-1.5">
        <StatusDot tone={s.tone} label={`Event stream: ${s.label}`} />
        {s.label}
      </span>
      <span className="hidden font-mono sm:inline">{count} events</span>
      <Link to="/settings/health" className="inline-flex items-center gap-1.5 rounded px-1 transition-colors hover:text-fg">
        <StatusDot tone={hTone} label={hLabel} />
        {hLabel}
      </Link>
      <span className="ml-auto flex items-center gap-1">
        <button
          type="button"
          aria-pressed={bottomOpen}
          aria-label="Toggle bottom panel"
          onClick={() => setBottom(!bottomOpen)}
          className={cn("rounded p-1 transition-colors hover:bg-raised hover:text-fg", bottomOpen && "text-accent-text")}
        >
          <PanelBottom className="size-3.5" />
        </button>
        <button
          type="button"
          aria-pressed={rightOpen}
          aria-label="Toggle activity panel"
          onClick={() => setRight(!rightOpen)}
          className={cn("hidden rounded p-1 transition-colors hover:bg-raised hover:text-fg lg:block", rightOpen && "text-accent-text")}
        >
          <PanelRight className="size-3.5" />
        </button>
      </span>
    </footer>
  );
}
