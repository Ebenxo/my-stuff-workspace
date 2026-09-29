import type { TaskNode } from "@nexus/schemas";
import { formatRelativeTime } from "@nexus/shared";
import { Badge, Button, Card, CardContent, EmptyState, ErrorState, Skeleton, Spinner, cn, toast } from "@nexus/ui";
import { Ban, ChevronLeft, List, Pencil, Play, RotateCcw, ShieldCheck, Waypoints } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { ApprovalCard } from "../features/approvals/ApprovalCard";
import { ActivityList } from "../features/events/ActivityList";
import { isActivityEvent } from "../features/events/describe";
import { MemorySuggestion } from "../features/memory/MemorySuggestion";
import { MessageFeed } from "../features/objectives/MessageFeed";
import { PlanEditorDialog } from "../features/objectives/PlanEditorDialog";
import { PlanView } from "../features/objectives/PlanView";
import { ResultCard } from "../features/objectives/ResultCard";
import { TaskGraph, TaskList } from "../features/objectives/TaskGraph";
import { TaskPanel } from "../features/objectives/TaskPanel";
import { OBJECTIVE_STATUS, isFinal, isLive, needsOf, progress } from "../features/objectives/format";
import { isNotFound, useApprovals } from "../lib/agentQueries";
import { useObjective, useObjectiveAction, useRunObjective } from "../lib/objectiveQueries";
import { errorMessage, useProject } from "../lib/queries";
import { useEvents } from "../stores/events";
import { Page, PageHeader, Section } from "./Page";

const wide = () => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(min-width: 768px)").matches;

/** The task to show first: one that needs the person, else one that is running, else nothing. */
function focusTask(tasks: TaskNode[]): TaskNode | undefined {
  return tasks.find((t) => needsOf(t).kind) ?? tasks.find((t) => t.status === "NEEDS_APPROVAL") ?? tasks.find((t) => t.status === "RUNNING");
}

function titleOf(text: string): { title: string; rest: string | undefined } {
  const first = text.split("\n")[0]!.trim();
  if (first.length <= 110 && first === text.trim()) return { title: first, rest: undefined };
  return { title: first.length > 110 ? `${first.slice(0, 107)}…` : first, rest: text };
}

export function ObjectiveRoute() {
  const { objectiveId = "" } = useParams();
  const detail = useObjective(objectiveId);
  const obj = detail.data?.objective;
  const project = useProject(obj?.project_id ?? "");
  const approvals = useApprovals("PENDING", obj?.project_id ?? undefined);
  const run = useRunObjective(objectiveId);
  const action = useObjectiveAction(objectiveId);
  const [editing, setEditing] = useState(false);
  const [view, setView] = useState<"graph" | "list">(() => (wide() ? "graph" : "list"));
  const [picked, setPicked] = useState<string | undefined>();
  const events = useEvents((s) => s.events);
  const tasks = useMemo(() => detail.data?.tasks ?? [], [detail.data]);
  const runIds = useMemo(() => new Set(tasks.map((t) => t.run_id).filter(Boolean)), [tasks]);
  const activity = useMemo(
    () => events.filter((e) => isActivityEvent(e) && (e.objective_id === objectiveId || (e.run_id && runIds.has(e.run_id)))).slice(-40).reverse(),
    [events, objectiveId, runIds],
  );

  if (detail.isPending) {
    return (
      <Page>
        <Skeleton className="mb-3 h-8 w-80" />
        <Skeleton className="h-64" />
      </Page>
    );
  }
  if (detail.isError) {
    return (
      <Page>
        {isNotFound(detail.error) ? (
          <EmptyState
            title="Objective not found"
            description="It may have been removed with its project, or the link is wrong."
            action={
              <Button asChild variant="primary">
                <Link to="/">Back to the Command Center</Link>
              </Button>
            }
          />
        ) : (
          <ErrorState message={errorMessage(detail.error)} onRetry={() => void detail.refetch()} />
        )}
      </Page>
    );
  }

  const { objective: o, messages } = detail.data;
  const status = OBJECTIVE_STATUS[o.status];
  const selected = tasks.find((t) => t.id === picked) ?? focusTask(tasks);
  const { done, total } = progress(tasks);
  const mine = (approvals.data ?? []).filter((a) => a.run_id && runIds.has(a.run_id));
  const awaiting = o.status === "AWAITING_PLAN_APPROVAL";
  const planning = o.status === "RECEIVED" || o.status === "PLANNING";
  const { title, rest } = titleOf(o.text);
  const failure = o.error && (o.status === "PAUSED" || o.status === "FAILED") ? o.error : null;

  const onError = (e: unknown) => toast.error(errorMessage(e));
  const start = (mode: "normal" | "safe_only") =>
    run.mutate(mode, { onSuccess: () => toast.success(mode === "safe_only" ? "Running the safe steps; anything riskier will wait for you" : "Running the plan"), onError });

  return (
    <Page className="max-w-6xl">
      <p className="mb-3">
        <Link to={`/projects/${o.project_id}?tab=objectives`} className="inline-flex items-center gap-1 text-[13px] text-fg-muted hover:text-fg">
          <ChevronLeft className="size-4" aria-hidden="true" />
          {project.data?.name ?? "Project"}
        </Link>
      </p>
      <PageHeader
        title={title}
        description={rest}
        badges={
          <>
            <Badge tone={status.tone}>{status.label}</Badge>
            {o.private ? <Badge>On this device</Badge> : null}
            {project.data?.is_demo ? <Badge tone="info">Demo</Badge> : null}
          </>
        }
        actions={
          <>
            {awaiting ? (
              <>
                <Button size="sm" onClick={() => setEditing(true)}>
                  <Pencil /> Edit plan
                </Button>
                <Button size="sm" loading={run.isPending && run.variables === "safe_only"} disabled={run.isPending} onClick={() => start("safe_only")}>
                  <ShieldCheck /> Run safe steps only
                </Button>
                <Button size="sm" variant="primary" loading={run.isPending && run.variables === "normal"} disabled={run.isPending} onClick={() => start("normal")}>
                  <Play /> Run plan
                </Button>
              </>
            ) : null}
            {o.status === "PAUSED" ? (
              <Button
                size="sm"
                variant="primary"
                loading={action.isPending && action.variables === "resume"}
                onClick={() => action.mutate("resume", { onSuccess: () => toast.success("Continuing"), onError })}
              >
                <RotateCcw /> Continue
              </Button>
            ) : null}
            {!isFinal(o.status) ? (
              <Button
                size="sm"
                variant={awaiting ? "ghost" : "danger"}
                loading={action.isPending && action.variables === "cancel"}
                onClick={() => action.mutate("cancel", { onSuccess: () => toast.success("Objective cancelled"), onError })}
              >
                <Ban /> Cancel
              </Button>
            ) : null}
          </>
        }
      />

      <p className="-mt-3 mb-6 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-fg-subtle">
        <span className="flex items-center gap-1.5">
          {isLive(o.status) ? <Spinner className="size-3" /> : null}
          {status.hint}
        </span>
        {total ? (
          <span>
            {done} of {total} tasks done
          </span>
        ) : null}
        <span>Started {formatRelativeTime(o.created_at)}</span>
        {o.replan_count ? <span>Re-planned once after verification</span> : null}
      </p>

      {failure ? (
        <div
          role="alert"
          className={cn("mb-6 rounded-lg border px-4 py-3 text-[13px]", o.status === "FAILED" ? "border-danger/40 bg-danger/10" : "border-warning/40 bg-warning/10")}
        >
          <p className="text-fg">{String(failure["message"] ?? "Something needs your attention.")}</p>
          {o.status === "PAUSED" ? (
            <p className="mt-1 text-xs text-fg-muted">Decide on the highlighted task below, then press Continue.</p>
          ) : null}
        </div>
      ) : null}

      {mine.length ? (
        <Section title="Waiting for your approval">
          <ul className="space-y-3">
            {mine.map((a) => (
              <li key={a.id}>
                <ApprovalCard approval={a} agentName={tasks.find((t) => t.run_id === a.run_id)?.assigned_agent.replaceAll("_", " ")} />
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {o.result ? (
        <div className="mb-8">
          <ResultCard objective={o} />
        </div>
      ) : null}

      {isFinal(o.status) ? <MemorySuggestion objective={o} /> : null}

      {planning && !o.plan ? (
        <Card className="mb-8">
          <CardContent className="flex items-center gap-3 py-8 text-sm text-fg-muted">
            <Spinner />
            The Planner is reading your objective and breaking it into tasks. You’ll see the plan before anything runs
            {o.run_mode === "auto" ? " (it starts right away, as you asked)" : ""}.
          </CardContent>
        </Card>
      ) : null}

      {awaiting ? (
        <Section title="Review the plan">
          <PlanView objective={o} />
        </Section>
      ) : null}

      {tasks.length ? (
        <Section
          title={awaiting ? "How the tasks connect" : "Tasks"}
          action={
            <div className="flex rounded-md border border-line p-0.5" role="group" aria-label="Task view">
              {(
                [
                  ["graph", Waypoints, "Graph"],
                  ["list", List, "List"],
                ] as const
              ).map(([v, Icon, label]) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={view === v}
                  onClick={() => setView(v)}
                  className={cn("flex items-center gap-1 rounded px-2 py-1 text-xs text-fg-muted", view === v && "bg-raised text-fg")}
                >
                  <Icon className="size-3.5" aria-hidden="true" /> {label}
                </button>
              ))}
            </div>
          }
        >
          <div className={cn("grid grid-cols-[minmax(0,1fr)] gap-3", selected && "lg:grid-cols-[minmax(0,1fr)_22rem]")}>
            {view === "graph" ? (
              <TaskGraph tasks={tasks} selectedId={selected?.id} onSelect={setPicked} />
            ) : (
              <TaskList tasks={tasks} selectedId={selected?.id} onSelect={setPicked} />
            )}
            {selected ? <TaskPanel task={selected} objectiveId={o.id} /> : null}
          </div>
          {!selected ? <p className="mt-2 text-xs text-fg-subtle">Select a task to see what it did.</p> : null}
        </Section>
      ) : null}

      {!awaiting && o.plan ? (
        <details className="mb-8">
          <summary className="cursor-pointer select-none text-[13px] font-medium uppercase tracking-wider text-fg-subtle hover:text-fg">
            The plan
          </summary>
          <div className="mt-3">
            <PlanView objective={o} />
          </div>
        </details>
      ) : null}

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-2">
        <Section title="Hand-offs between agents">
          <Card>
            <MessageFeed messages={messages} onSelectTask={setPicked} />
          </Card>
        </Section>
        <Section title="Activity">
          <Card>
            {activity.length ? (
              <ActivityList events={activity} className="max-h-[28rem] overflow-y-auto" />
            ) : (
              <p className="px-3 py-4 text-[13px] text-fg-muted">Activity appears here as it happens.</p>
            )}
          </Card>
        </Section>
      </div>

      {awaiting ? <PlanEditorDialog objective={o} open={editing} onOpenChange={setEditing} /> : null}
    </Page>
  );
}
