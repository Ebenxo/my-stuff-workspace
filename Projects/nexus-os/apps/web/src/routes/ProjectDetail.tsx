import { ApiError } from "@nexus/shared";
import { formatRelativeTime } from "@nexus/shared";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Dialog, DialogContent, EmptyState, ErrorState, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger, toast } from "@nexus/ui";
import { Archive, ArchiveRestore, Pencil, Play } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { RunAgentDialog } from "../features/agents/RunAgentDialog";
import { RunList } from "../features/agents/RunList";
import { ApprovalsPanel } from "../features/approvals/ApprovalsPanel";
import { ActivityList } from "../features/events/ActivityList";
import { isActivityEvent } from "../features/events/describe";
import { ArtifactsTab } from "../features/files/ArtifactsTab";
import { ObjectiveComposer } from "../features/objectives/ObjectiveComposer";
import { ObjectiveList } from "../features/objectives/ObjectiveList";
import { FilesTab } from "../features/files/FilesTab";
import { MemoryBrowser } from "../features/memory/MemoryBrowser";
import { ProjectForm } from "../features/projects/ProjectForm";
import { PERMISSION_COPY } from "../features/projects/permissions";
import { ToolCallList } from "../features/tools/ToolCallList";
import { useApprovals } from "../lib/agentQueries";
import { errorMessage, useProject, useSetProjectArchived, useSettings, useUpdateProject } from "../lib/queries";
import { useEvents } from "../stores/events";
import { Page, PageHeader, Section } from "./Page";

const TABS = ["overview", "objectives", "files", "artifacts", "memory", "runs", "tools", "approvals"] as const;
type ProjectTab = (typeof TABS)[number];

export function ProjectDetailRoute() {
  const { projectId = "" } = useParams();
  const project = useProject(projectId);
  const settings = useSettings();
  const update = useUpdateProject(projectId);
  const archive = useSetProjectArchived();
  const [editing, setEditing] = useState(false);
  const [running, setRunning] = useState(false);
  const [params, setParams] = useSearchParams();
  const tabParam = params.get("tab");
  const tab: ProjectTab = (TABS as readonly string[]).includes(tabParam ?? "") ? (tabParam as ProjectTab) : "overview";
  const pending = useApprovals("PENDING", projectId);
  const events = useEvents((s) => s.events);
  const projectEvents = useMemo(
    () => events.filter((e) => e.project_id === projectId && isActivityEvent(e)).slice(-30).reverse(),
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
            <Button size="sm" variant="primary" disabled={archived} onClick={() => setRunning(true)}>
              <Play /> Run an agent
            </Button>
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

      <Tabs
        value={tab}
        onValueChange={(v) => {
          const next = new URLSearchParams(params);
          if (v === "overview") next.delete("tab");
          else next.set("tab", v);
          setParams(next, { replace: true });
        }}
      >
        <TabsList className="mb-5 overflow-x-auto">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="objectives">Objectives</TabsTrigger>
          <TabsTrigger value="files">Files</TabsTrigger>
          <TabsTrigger value="artifacts">Deliverables</TabsTrigger>
          <TabsTrigger value="memory">Memory</TabsTrigger>
          <TabsTrigger value="runs">Runs</TabsTrigger>
          <TabsTrigger value="tools">Tool activity</TabsTrigger>
          <TabsTrigger value="approvals">
            Approvals
            {pending.data && pending.data.length > 0 ? (
              <Badge tone="warning" className="ml-1.5">
                {pending.data.length}
              </Badge>
            ) : null}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
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
        </TabsContent>

        <TabsContent value="objectives">
          {archived ? null : (
            <div className="mb-4">
              <ObjectiveComposer projectId={projectId} />
            </div>
          )}
          <Card>
            <ObjectiveList projectId={projectId} limit={50} empty="Give this project an objective and NEXUS will plan it, assign agents, and check the result." />
          </Card>
        </TabsContent>
        <TabsContent value="files">
          <FilesTab projectId={projectId} />
        </TabsContent>
        <TabsContent value="artifacts">
          <ArtifactsTab projectId={projectId} />
        </TabsContent>
        <TabsContent value="memory">
          <MemoryBrowser projectId={projectId} focusId={params.get("memory")} />
        </TabsContent>
        <TabsContent value="runs">
          <Card>
            <RunList filter={{ projectId, limit: 30 }} empty="Run an agent in this project and its work will be listed here." />
          </Card>
        </TabsContent>
        <TabsContent value="tools">
          <Card>
            <ToolCallList projectId={projectId} limit={100} />
          </Card>
        </TabsContent>
        <TabsContent value="approvals">
          <Card>
            <ApprovalsPanel projectId={projectId} />
          </Card>
        </TabsContent>
      </Tabs>

      <RunAgentDialog open={running} onOpenChange={setRunning} projectId={projectId} />

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
