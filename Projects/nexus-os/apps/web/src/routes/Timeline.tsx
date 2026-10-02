import type { EventRecord } from "@nexus/schemas";
import { Button, Card, EmptyState, ErrorState, Label, Select, Skeleton, Switch } from "@nexus/ui";
import { Activity, ArrowRight, CalendarClock, Hand, Lightbulb, Pin } from "lucide-react";
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router";
import { timelineHref } from "../features/ideas/format";
import { HistoryList } from "../features/timeline/HistoryList";
import { Lane } from "../features/timeline/Lane";
import { historyExcludes, useHistory, useTimeline } from "../lib/ideaQueries";
import { errorMessage, useProjects } from "../lib/queries";
import { useNow } from "../lib/useNow";
import { useEvents } from "../stores/events";
import { Page, PageHeader, Section } from "./Page";

/**
 * One place for everything: what needs the person, what is running, what is coming up, what they
 * pinned, and (below) the full history of what happened, newest first.
 */
export function TimelineRoute() {
  const [params, setParams] = useSearchParams();
  const projectId = params.get("project") || undefined;
  const detailed = params.get("detail") === "1";
  const projects = useProjects("active");
  const timeline = useTimeline(projectId);
  const history = useHistory(projectId, detailed);
  const live = useEvents((s) => s.events);
  const now = useNow();

  function setParam(name: string, value: string | undefined) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(name, value);
        else next.delete(name);
        return next;
      },
      { replace: true },
    );
  }

  // Loaded pages, plus anything that arrived live since the first page was fetched.
  const events = useMemo(() => {
    const loaded = history.data?.pages.flat() ?? [];
    const newest = loaded[0]?.seq ?? 0;
    const excluded = new Set(historyExcludes(detailed));
    const fresh: EventRecord[] = history.data
      ? live.filter((e) => e.seq > newest && !excluded.has(e.type) && (!projectId || e.project_id === projectId)).reverse()
      : [];
    return [...fresh, ...loaded];
  }, [history.data, live, detailed, projectId]);

  const t = timeline.data;
  const loading = timeline.isPending;

  return (
    <Page className="max-w-6xl">
      <PageHeader
        title="Timeline"
        description="What needs you, what is happening now, what is coming up, and everything that has happened, in one place."
        actions={
          <div className="w-48">
            <Label htmlFor="timeline-project" className="sr-only">
              Project
            </Label>
            <Select id="timeline-project" value={projectId ?? ""} onChange={(e) => setParam("project", e.target.value || undefined)}>
              <option value="">All projects</option>
              {(projects.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </div>
        }
      />

      {timeline.isError ? (
        <div className="mb-8">
          <ErrorState message={errorMessage(timeline.error)} onRetry={() => void timeline.refetch()} />
        </div>
      ) : (
        <div className="mb-6 grid gap-3 lg:grid-cols-3">
          <Lane
            title="Needs you"
            icon={Hand}
            tone="warning"
            lane="waiting"
            items={t?.waiting}
            loading={loading}
            empty="Nothing is waiting for you."
            now={now}
          />
          <Lane
            title="Happening now"
            icon={Activity}
            tone="accent"
            lane="now"
            items={t?.now}
            loading={loading}
            empty="Nothing is running right now."
            now={now}
          />
          <Lane
            title="Coming up"
            icon={CalendarClock}
            tone="info"
            lane="next"
            items={t?.next}
            loading={loading}
            empty="Nothing scheduled. Schedule a workflow, or give a to-do a due time."
            now={now}
          />
        </div>
      )}

      {t && t.pinned.length > 0 ? (
        <Section
          title="Keep in mind"
          action={
            <Button asChild variant="ghost" size="sm">
              <Link to="/ideas">
                Ideas & notes <ArrowRight />
              </Link>
            </Button>
          }
        >
          <ul className="flex flex-wrap gap-2">
            {t.pinned.map((item) => (
              <li key={item.id}>
                <Link
                  to={timelineHref(item)}
                  className="flex max-w-xs items-center gap-1.5 rounded-full border border-line-strong bg-surface px-3 py-1 text-[13px] text-fg transition-colors hover:bg-raised"
                >
                  <Pin className="size-3.5 shrink-0 text-accent-text" aria-hidden="true" />
                  <span className="truncate">{item.title}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section
        title="Earlier"
        action={
          <label className="flex items-center gap-2 text-xs text-fg-muted">
            <Switch checked={detailed} onCheckedChange={(on) => setParam("detail", on ? "1" : undefined)} aria-label="Show every step" />
            Show every step
          </label>
        }
      >
        <Card className="overflow-hidden">
          {history.isPending ? (
            <div className="space-y-2 p-3">
              <Skeleton className="h-8" />
              <Skeleton className="h-8" />
              <Skeleton className="h-8" />
            </div>
          ) : history.isError ? (
            <ErrorState message={errorMessage(history.error)} onRetry={() => void history.refetch()} />
          ) : events.length === 0 ? (
            <EmptyState
              icon={<Lightbulb />}
              title="Nothing has happened yet"
              description="Everything NEXUS and you do is recorded here: objectives, agents, approvals, workflows, ideas."
            />
          ) : (
            <>
              <HistoryList events={events} now={now} />
              <div className="flex items-center justify-between gap-3 border-t border-line px-3 py-2">
                <p className="text-xs text-fg-subtle">
                  {events.length} {events.length === 1 ? "entry" : "entries"} shown
                </p>
                {history.hasNextPage ? (
                  <Button size="sm" variant="ghost" loading={history.isFetchingNextPage} onClick={() => void history.fetchNextPage()}>
                    Load older
                  </Button>
                ) : (
                  <p className="text-xs text-fg-subtle">That is everything.</p>
                )}
              </div>
            </>
          )}
        </Card>
      </Section>
    </Page>
  );
}
