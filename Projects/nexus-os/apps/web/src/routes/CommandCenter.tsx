import { formatRelativeTime, greeting } from "@nexus/shared";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton } from "@nexus/ui";
import { ArrowRight, FolderPlus, Plus, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { RunAgentDialog } from "../features/agents/RunAgentDialog";
import { RunList } from "../features/agents/RunList";
import { usePendingApprovalCount } from "../lib/agentQueries";
import { ActivityList } from "../features/events/ActivityList";
import { isActivityEvent } from "../features/events/describe";
import { ObjectiveComposer } from "../features/objectives/ObjectiveComposer";
import { ObjectiveList } from "../features/objectives/ObjectiveList";
import { NewProjectDialog } from "../features/projects/NewProjectDialog";
import { ProjectCard } from "../features/projects/ProjectCard";
import { errorMessage, useHealth, useHasRealProvider, useProjects, useSettings, useUnreadCount } from "../lib/queries";
import { useEvents } from "../stores/events";
import { Page, Section } from "./Page";

function Stat({ label, value, hint, loading }: { label: string; value: React.ReactNode; hint?: string; loading?: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{label}</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? <Skeleton className="h-8 w-16" /> : <p className="text-2xl font-semibold tracking-tight">{value}</p>}
        {hint ? <p className="mt-1 text-xs text-fg-muted">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

export function CommandCenterRoute() {
  const settings = useSettings();
  const projects = useProjects("active");
  const unread = useUnreadCount();
  const hasProvider = useHasRealProvider();
  const health = useHealth();
  const eventCount = useEvents((s) => s.events.length);
  const events = useEvents((s) => s.events);
  const recent = useMemo(() => events.filter(isActivityEvent).reverse().slice(0, 8), [events]);
  const [creating, setCreating] = useState(false);
  const [running, setRunning] = useState(false);
  const pendingApprovals = usePendingApprovalCount();
  const name = settings.data?.display_name?.trim();

  const status = health.data?.status;
  const tone = status === "ok" ? "success" : status === "degraded" ? "warning" : status === "down" ? "danger" : "neutral";

  return (
    <Page>
      <header className="mb-6">
        <h2 className="text-2xl font-semibold tracking-tight">
          {greeting()}
          {name ? `, ${name}` : ""}
        </h2>
        <p className="mt-1 text-sm text-fg-muted">What should NEXUS work on?</p>
      </header>

      {hasProvider === false ? (
        <div role="note" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-accent/40 bg-accent/10 px-4 py-3">
          <p className="text-[13px] text-fg">
            <strong className="font-medium">Connect an AI provider to get started.</strong>{" "}
            <span className="text-fg-muted">NEXUS needs a model to plan and work. A local model keeps everything on this machine.</span>
          </p>
          <Button asChild variant="primary" size="sm">
            <Link to="/settings/providers">Connect a provider</Link>
          </Button>
        </div>
      ) : null}

      {pendingApprovals > 0 ? (
        <div role="status" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3">
          <p className="flex items-center gap-2 text-[13px] text-fg">
            <ShieldAlert className="size-4 text-warning" aria-hidden="true" />
            <span>
              <strong className="font-medium">
                {pendingApprovals} {pendingApprovals === 1 ? "action is" : "actions are"} waiting for your approval.
              </strong>{" "}
              <span className="text-fg-muted">The agents will wait until you decide.</span>
            </span>
          </p>
          <Button asChild size="sm" variant="primary">
            <Link to="/approvals">Review</Link>
          </Button>
        </div>
      ) : null}

      <div className="mb-8">
        <ObjectiveComposer onNewProject={() => setCreating(true)} />
        <p className="mt-2 px-1 text-xs text-fg-subtle">
          For a single, focused job you can also{" "}
          <button type="button" onClick={() => setRunning(true)} className="text-accent-text hover:underline">
            run one agent directly
          </button>
          .
        </p>
      </div>

      <div className="mb-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Projects" value={projects.data?.length ?? "—"} loading={projects.isPending} hint="Active workspaces" />
        <Stat label="Unread notifications" value={unread.data?.count ?? "—"} loading={unread.isPending} />
        <Stat label="Events recorded" value={eventCount} hint="Live in this session" />
        <Card>
          <CardHeader>
            <CardTitle>System health</CardTitle>
          </CardHeader>
          <CardContent>
            {health.isPending ? (
              <Skeleton className="h-8 w-20" />
            ) : health.isError ? (
              <Badge tone="danger">Unreachable</Badge>
            ) : (
              <Badge tone={tone}>{status}</Badge>
            )}
            <p className="mt-2 text-xs">
              <Link to="/settings/health" className="text-accent-text hover:underline">
                View details
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>

      <Section title="Objectives">
        <Card>
          <ObjectiveList limit={6} />
        </Card>
      </Section>

      <Section
        title="Recent projects"
        action={
          <Button asChild variant="ghost" size="sm">
            <Link to="/projects">
              All projects <ArrowRight />
            </Link>
          </Button>
        }
      >
        {projects.isPending ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
          </div>
        ) : projects.isError ? (
          <ErrorState message={errorMessage(projects.error)} onRetry={() => void projects.refetch()} />
        ) : projects.data.length === 0 ? (
          <Card>
            <EmptyState
              icon={<FolderPlus />}
              title="No projects yet"
              description="Create a project to give NEXUS a place to work."
              action={
                <Button variant="primary" onClick={() => setCreating(true)}>
                  <Plus /> New project
                </Button>
              }
            />
          </Card>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {projects.data.slice(0, 4).map((p) => (
              <li key={p.id}>
                <ProjectCard project={p} />
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="Recent agent runs"
        action={
          <Button asChild variant="ghost" size="sm">
            <Link to="/agents">
              Agents <ArrowRight />
            </Link>
          </Button>
        }
      >
        <Card>
          <RunList filter={{ limit: 5 }} />
        </Card>
      </Section>

      <Section title="Recent activity">
        <Card>
          {recent.length === 0 ? (
            <EmptyState title="Nothing yet" description="Activity from every project shows up here." />
          ) : (
            <>
              <ActivityList events={recent} />
              <p className="border-t border-line px-3 py-2 text-xs text-fg-subtle">
                Latest {formatRelativeTime(recent[0]?.ts ?? new Date())}
              </p>
            </>
          )}
        </Card>
      </Section>
      <NewProjectDialog open={creating} onOpenChange={setCreating} />
      <RunAgentDialog open={running} onOpenChange={setRunning} />
    </Page>
  );
}
