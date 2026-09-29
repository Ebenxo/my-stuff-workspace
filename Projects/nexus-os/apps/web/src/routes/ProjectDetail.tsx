import { ApiError } from "@nexus/shared";
import { formatRelativeTime } from "@nexus/shared";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Dialog, DialogContent, EmptyState, ErrorState, Skeleton, toast } from "@nexus/ui";
import { Archive, ArchiveRestore, Pencil } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { ActivityList } from "../features/events/ActivityList";
import { ProjectForm } from "../features/projects/ProjectForm";
import { PERMISSION_COPY } from "../features/projects/permissions";
import { errorMessage, useProject, useSetProjectArchived, useSettings, useUpdateProject } from "../lib/queries";
import { useEvents } from "../stores/events";
import { Page, PageHeader, Section } from "./Page";

export function ProjectDetailRoute() {
  const { projectId = "" } = useParams();
  const project = useProject(projectId);
  const settings = useSettings();
  const update = useUpdateProject(projectId);
  const archive = useSetProjectArchived();
  const [editing, setEditing] = useState(false);
  const events = useEvents((s) => s.events);
  const projectEvents = useMemo(
    () => events.filter((e) => e.project_id === projectId).slice(-30).reverse(),
    [events, projectId],
  );

  if (project.isPending) {
    return (
      <Page>
        <Skeleton className="mb-3 h-8 w-64" />
        <Skeleton className="h-40" />
      </Page>
    );
  }
  if (project.isError) {
    const notFound = project.error instanceof ApiError && project.error.status === 404;
    return (
      <Page>
        {notFound ? (
          <EmptyState
            title="Project not found"
            description="It may have been removed, or the link is wrong."
            action={
              <Button asChild variant="primary">
                <Link to="/projects">Back to projects</Link>
              </Button>
            }
          />
        ) : (
          <ErrorState message={errorMessage(project.error)} onRetry={() => void project.refetch()} />
        )}
      </Page>
    );
  }

  const p = project.data;
  const effective = p.settings.permission_level ?? settings.data?.default_permission_level ?? "balanced";
  const archived = p.status === "archived";

  return (
    <Page>
      <PageHeader
        title={p.name}
        description={p.description || "No description yet."}
        badges={
          <>
            {archived ? <Badge tone="warning">Archived</Badge> : null}
            {p.is_demo ? <Badge tone="info">Demo</Badge> : null}
          </>
        }
        actions={
          <>
            <Button size="sm" onClick={() => setEditing(true)}>
              <Pencil /> Edit
            </Button>
            <Button
              size="sm"
              variant="ghost"
              loading={archive.isPending}
              onClick={() =>
                archive.mutate(
                  { id: p.id, archived: !archived },
                  {
                    onSuccess: () => toast.success(archived ? "Project restored" : "Project archived"),
                    onError: (e) => toast.error(errorMessage(e)),
                  },
                )
              }
            >
              {archived ? <ArchiveRestore /> : <Archive />}
              {archived ? "Restore" : "Archive"}
            </Button>
          </>
        }
      />

      <div className="mb-8 grid gap-3 sm:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Permissions</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm font-medium">{PERMISSION_COPY[effective].label}</p>
            <p className="mt-1 text-xs text-fg-muted">
              {p.settings.permission_level ? "Set for this project." : "Following your default."}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Created</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm font-medium">{formatRelativeTime(p.created_at)}</p>
            <p className="mt-1 text-xs text-fg-muted">{new Date(p.created_at).toLocaleString()}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Last change</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm font-medium">{formatRelativeTime(p.updated_at)}</p>
            <p className="mt-1 text-xs text-fg-muted">{new Date(p.updated_at).toLocaleString()}</p>
          </CardContent>
        </Card>
      </div>

      <Section title="Activity">
        <Card>
          {projectEvents.length === 0 ? (
            <EmptyState title="No activity yet" description="Work on this project will be recorded here as it happens." />
          ) : (
            <ActivityList events={projectEvents} />
          )}
        </Card>
      </Section>

      <Dialog
        open={editing}
        onOpenChange={(o) => {
          if (!o) update.reset();
          setEditing(o);
        }}
      >
        <DialogContent title="Edit project">
          <ProjectForm
            initial={p}
            submitLabel="Save changes"
            pending={update.isPending}
            error={update.isError ? errorMessage(update.error) : undefined}
            onCancel={() => setEditing(false)}
            onSubmit={(v) =>
              update.mutate(
                { name: v.name, description: v.description, settings: { ...p.settings, permission_level: v.permission_level, monthly_budget_usd: v.monthly_budget_usd } },
                {
                  onSuccess: () => {
                    toast.success("Project updated");
                    setEditing(false);
                  },
                },
              )
            }
          />
        </DialogContent>
      </Dialog>
    </Page>
  );
}
