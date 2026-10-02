import type { EventRecord } from "@nexus/schemas";
import { cn } from "@nexus/ui";
import { describeEvent, formatClock, type Tone } from "./describe";

const dot: Record<Tone, string> = {
  neutral: "bg-fg-subtle",
  accent: "bg-accent-text",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-info",
};

export function ActivityList({ events, className }: { events: EventRecord[]; className?: string }) {
  return (
    <ol className={cn("divide-y divide-line", className)} aria-label="Activity">
      {events.map((e) => {
        const view = describeEvent(e);
        return (
          <li key={e.seq} className="flex items-start gap-2.5 px-3 py-2 text-[13px]">
            <span className={cn("mt-[7px] size-1.5 shrink-0 rounded-full", dot[view.tone])} aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="break-words text-fg">{view.text}</p>
              <p className="font-mono text-[11px] text-fg-subtle">
                <time dateTime={e.ts}>{formatClock(e.ts)}</time>
                <span className="mx-1.5" aria-hidden="true">
                  ·
                </span>
                {e.actor}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
