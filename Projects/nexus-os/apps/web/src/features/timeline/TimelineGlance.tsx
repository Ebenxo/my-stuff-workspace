import { formatRelativeTime } from "@nexus/shared";
import type { TimelineItem } from "@nexus/schemas";
import { Button, Card, cn, ErrorState, Skeleton } from "@nexus/ui";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router";
import { useTimeline } from "../../lib/ideaQueries";
import { errorMessage } from "../../lib/queries";
import { timelineHref } from "../ideas/format";

const MAX = 5;

/** The Command Center's slice of the timeline: what needs the person first, then what is coming up. */
export function TimelineGlance() {
  const timeline = useTimeline();
  const t = timeline.data;
  const items: { item: TimelineItem; waiting: boolean }[] = t
    ? [...t.waiting.map((item) => ({ item, waiting: true })), ...t.next.map((item) => ({ item, waiting: false }))].slice(0, MAX)
    : [];
  const running = t?.now.length ?? 0;

  return (
    <Card className="flex flex-col">
      <header className="flex items-center justify-between gap-2 border-b border-line px-3 py-2">
        <h3 className="text-[13px] font-medium text-fg">Needs you & coming up</h3>
        <Button asChild variant="ghost" size="sm">
          <Link to="/timeline">
            Timeline <ArrowRight />
          </Link>
        </Button>
      </header>
      {timeline.isPending ? (
        <div className="space-y-2 p-3">
          <Skeleton className="h-8" />
          <Skeleton className="h-8" />
        </div>
      ) : timeline.isError ? (
        <ErrorState message={errorMessage(timeline.error)} onRetry={() => void timeline.refetch()} />
      ) : items.length === 0 ? (
        <p className="flex-1 px-3 py-6 text-center text-[13px] text-fg-subtle">Nothing is waiting for you and nothing is scheduled.</p>
      ) : (
        <ul className="divide-y divide-line">
          {items.map(({ item, waiting }) => (
            <li key={`${item.kind}-${item.id}`}>
              <Link to={timelineHref(item)} className="flex items-center gap-2.5 px-3 py-2 transition-colors hover:bg-raised">
                <span
                  className={cn("size-1.5 shrink-0 rounded-full", waiting ? (item.status === "OVERDUE" ? "bg-danger" : "bg-warning") : "bg-info")}
                  aria-hidden="true"
                />
                <span className="min-w-0 flex-1 truncate text-[13px] text-fg">{item.title}</span>
                {item.at ? (
                  <time dateTime={item.at} className="shrink-0 text-[11px] text-fg-subtle">
                    {formatRelativeTime(item.at)}
                  </time>
                ) : null}
              </Link>
            </li>
          ))}
        </ul>
      )}
      {running > 0 ? (
        <p className="border-t border-line px-3 py-2 text-xs text-fg-muted">
          {running} {running === 1 ? "thing is" : "things are"} running now.
        </p>
      ) : null}
    </Card>
  );
}
