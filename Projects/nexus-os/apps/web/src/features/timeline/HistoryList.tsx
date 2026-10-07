import type { EventRecord } from "@nexus/schemas";
import { cn } from "@nexus/ui";
import { ChevronRight } from "lucide-react";
import { Link } from "react-router";
import { describeEvent, formatClock, type Tone } from "../events/describe";
import { eventHref, groupByDay } from "../ideas/format";

const dot: Record<Tone, string> = {
  neutral: "bg-fg-subtle",
  accent: "bg-accent-text",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-info",
};

function Row({ e }: { e: EventRecord }) {
  const view = describeEvent(e);
  const href = eventHref(e);
  const body = (
    <>
      <span className={cn("mt-[7px] size-1.5 shrink-0 rounded-full", dot[view.tone])} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="break-words text-fg">{view.text}</p>
        <p className="font-mono text-[11px] text-fg-subtle">
          <time dateTime={e.ts} title={new Date(e.ts).toLocaleString()}>
            {formatClock(e.ts)}
          </time>
          <span className="mx-1.5" aria-hidden="true">
            ·
          </span>
          {e.actor}
        </p>
      </div>
      {href ? <ChevronRight className="mt-1 size-3.5 shrink-0 text-fg-subtle" aria-hidden="true" /> : null}
    </>
  );
  return (
    <li>
      {href ? (
        <Link to={href} className="flex items-start gap-2.5 px-3 py-2 text-[13px] transition-colors hover:bg-raised">
          {body}
        </Link>
      ) : (
        <div className="flex items-start gap-2.5 px-3 py-2 text-[13px]">{body}</div>
      )}
    </li>
  );
}

/** The event log as a history: newest first, grouped by day, each entry linking to what it is about. */
export function HistoryList({ events, now = new Date() }: { events: EventRecord[]; now?: Date }) {
  return (
    <div>
      {groupByDay(events, now).map((g) => (
        <section key={g.day} aria-label={g.day}>
          <h4 className="sticky top-0 z-[1] border-y border-line bg-surface/95 px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider text-fg-subtle backdrop-blur first:border-t-0">
            {g.day}
          </h4>
          <ol className="divide-y divide-line">
            {g.events.map((e) => (
              <Row key={e.seq} e={e} />
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}
