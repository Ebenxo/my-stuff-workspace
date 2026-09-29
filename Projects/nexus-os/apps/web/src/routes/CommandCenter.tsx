import { formatRelativeTime, greeting } from "@nexus/shared";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton } from "@nexus/ui";
import { ArrowRight, FolderPlus, Plus, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { ActivityList } from "../features/events/ActivityList";
import { NewProjectDialog } from "../features/projects/NewProjectDialog";
import { ProjectCard } from "../features/projects/ProjectCard";
import { errorMessage, useHealth, useProjects, useSettings, useUnreadCount } from "../lib/queries";
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
  const health = useHealth();
  const eventCount = useEvents((s) => s.events.length);
  const events = useEvents((s) => s.events);
  const recent = useMemo(() => [...events].reverse().slice(0, 8), [events]);
  const [creating, setCreating] = useState(false);
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

      <div className="mb-8 rounded-xl border border-line-strong bg-surface p-3 shadow-sm">
        <label htmlFor="objective" className="sr-only">
          Objective
        </label>
        <textarea
          id="objective"
          disabled
          rows={2}
          placeholder="Describe an objective…"
          className="w-full resize-none bg-transparent px-2 py-1.5 text-[15px] text-fg placeholder:text-fg-subtle focus-visible:outline-none disabled:cursor-not-allowed"
        />
        <div className="flex items-center justify-between gap-3 px-2 pt-1">
          <p className="flex items-center gap-1.5 text-xs text-fg-muted">
            <Sparkles className="size-3.5" aria-hidden="true" />
            Objectives arrive with the planner and agent runtime, in the next build phases.
          </p>
          <Button variant="primary" size="sm" disabled>
            Start
          </Button>
        </div>
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
    </Page>
  );
}
