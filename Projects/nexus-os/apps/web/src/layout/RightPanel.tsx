import { EmptyState } from "@nexus/ui";
import { Activity } from "lucide-react";
import { useMemo } from "react";
import { ActivityList } from "../features/events/ActivityList";
import { useEvents } from "../stores/events";

export function RightPanel() {
  const events = useEvents((s) => s.events);
  const newestFirst = useMemo(() => [...events].reverse().slice(0, 100), [events]);
  return (
    <aside aria-label="Activity panel" className="hidden w-80 shrink-0 flex-col border-l border-line bg-surface lg:flex">
      <header className="flex h-10 items-center gap-2 border-b border-line px-3">
        <Activity className="size-4 text-fg-subtle" aria-hidden="true" />
        <h2 className="text-[13px] font-medium">Activity</h2>
        <span className="ml-auto font-mono text-[11px] text-fg-subtle">{events.length} recent</span>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {newestFirst.length === 0 ? (
          <EmptyState
            icon={<Activity />}
            title="Nothing has happened yet"
            description="Everything NEXUS does is recorded here as it happens."
          />
        ) : (
          <ActivityList events={newestFirst} />
        )}
      </div>
    </aside>
  );
}
