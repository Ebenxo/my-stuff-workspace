import { formatRelativeTime } from "@nexus/shared";
import type { TimelineItem } from "@nexus/schemas";
import { Card, cn, Skeleton } from "@nexus/ui";
import { Bot, CalendarClock, Lightbulb, ShieldAlert, Target, Workflow, type LucideIcon } from "lucide-react";
import { Link } from "react-router";
import { dueLabel, timelineHref } from "../ideas/format";
import { KIND_ICON } from "../ideas/icons";

const ICON: Record<TimelineItem["kind"], LucideIcon> = {
  objective: Target,
  agent_run: Bot,
  workflow_run: Workflow,
  schedule: CalendarClock,
  approval: ShieldAlert,
  idea: Lightbulb,
};

export type LaneTone = "warning" | "accent" | "info";

const toneRing: Record<LaneTone, string> = {
  warning: "text-warning",
  accent: "text-accent-text",
  info: "text-info",
};

function when(item: TimelineItem, lane: "now" | "waiting" | "next", now: Date): string {
  if (!item.at) return "";
  if (lane === "next") return `${formatRelativeTime(item.at, now)} · ${dueLabel(item.at, now).text.replace(/^Overdue · /, "")}`;
  if (item.kind === "idea") return dueLabel(item.at, now).text;
  return `${lane === "now" ? "Started" : "Asked"} ${formatRelativeTime(item.at, now)}`;
}

export function Lane({
  title,
  icon: Icon,
  tone,
  lane,
  items,
  loading,
  empty,
  now = new Date(),
}: {
  title: string;
  icon: LucideIcon;
  tone: LaneTone;
  lane: "now" | "waiting" | "next";
  items: TimelineItem[] | undefined;
  loading?: boolean;
  empty: string;
  now?: Date;
}) {
  const id = `lane-${lane}`;
  return (
    <Card className="flex min-w-0 flex-col">
      <header className="flex items-center gap-2 border-b border-line px-3 py-2.5">
        <Icon className={cn("size-4", toneRing[tone])} aria-hidden="true" />
        <h3 id={id} className="text-[13px] font-medium text-fg">
          {title}
        </h3>
        {items && items.length > 0 ? (
          <span className="ml-auto rounded-full bg-raised px-2 text-xs font-medium text-fg-muted">{items.length}</span>
        ) : null}
      </header>
      {loading ? (
        <div className="space-y-2 p-3">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      ) : !items || items.length === 0 ? (
        <p className="px-3 py-6 text-center text-[13px] text-fg-subtle">{empty}</p>
      ) : (
        <ul aria-labelledby={id} className="divide-y divide-line">
          {items.map((item) => {
            const KindIcon = item.kind === "idea" && item.idea_kind ? KIND_ICON[item.idea_kind] : ICON[item.kind];
            const overdue = item.status === "OVERDUE";
            return (
              <li key={`${item.kind}-${item.id}`}>
                <Link to={timelineHref(item)} className="flex items-start gap-2.5 px-3 py-2.5 transition-colors hover:bg-raised">
                  <KindIcon className={cn("mt-0.5 size-4 shrink-0", overdue ? "text-danger" : "text-fg-subtle")} aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium text-fg">{item.title}</p>
                    {item.detail ? <p className="line-clamp-2 text-xs text-fg-muted">{item.detail}</p> : null}
                    {item.at ? (
                      <p className={cn("mt-0.5 text-[11px]", overdue ? "text-danger" : "text-fg-subtle")}>
                        <time dateTime={item.at} title={new Date(item.at).toLocaleString()}>
                          {when(item, lane, now)}
                        </time>
                      </p>
                    ) : null}
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
