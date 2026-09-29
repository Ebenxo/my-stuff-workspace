import { formatRelativeTime } from "@nexus/shared";
import { Badge, Button, Card, Dialog, DialogContent, DialogFooter, EmptyState, ErrorState, FieldError, Input, Label, Select, Skeleton, Textarea } from "@nexus/ui";
import { Plus, Workflow as WorkflowIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { WorkflowRunList } from "../features/workflows/WorkflowRunList";
import { errorMessage, useProjects } from "../lib/queries";
import { useCreateWorkflow, useWorkflows } from "../lib/workflowQueries";
import { Page, PageHeader, Section } from "./Page";

function NewWorkflowDialog({ open, onOpenChange, projectId }: { open: boolean; onOpenChange: (o: boolean) => void; projectId?: string | undefined }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New workflow" description="It starts with a simple draft you can change: a start step, an agent, and an output.">
        <NewWorkflowForm projectId={projectId} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function NewWorkflowForm({ projectId, onDone }: { projectId: string | undefined; onDone: () => void }) {
  const projects = useProjects("active");
  const create = useCreateWorkflow();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [project, setProject] = useState(projectId ?? "");
  const chosen = project || projects.data?.[0]?.id || "";
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (!name.trim() || !chosen) return;
        create.mutate(
          { name: name.trim(), description: description.trim(), project_id: chosen },
          {
            onSuccess: (wf) => {
              onDone();
              void navigate(`/workflows/${wf.id}`);
            },
          },
        );
      }}
    >
      <div>
        <Label htmlFor="wf-name">Name</Label>
        <Input id="wf-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder="Weekly competitor digest" />
      </div>
      <div>
        <Label htmlFor="wf-desc">What it is for</Label>
        <Textarea id="wf-desc" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
      <div>
        <Label htmlFor="wf-project">Project</Label>
        <Select id="wf-project" value={chosen} onChange={(e) => setProject(e.target.value)}>
          {(projects.data ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
      </div>
      <FieldError>{create.isError ? errorMessage(create.error) : undefined}</FieldError>
      <DialogFooter>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" loading={create.isPending} disabled={!name.trim() || !chosen}>
          Create
        </Button>
      </DialogFooter>
    </form>
  );
}

export function WorkflowList({ projectId }: { projectId?: string | undefined }) {
  const workflows = useWorkflows(projectId);
  const [creating, setCreating] = useState(false);
  if (workflows.isPending) return <Skeleton className="h-24" />;
  if (workflows.isError) return <ErrorState message={errorMessage(workflows.error)} onRetry={() => void workflows.refetch()} />;
  return (
    <>
      {workflows.data.length === 0 ? (
        <Card>
          <EmptyState
            icon={<WorkflowIcon />}
            title="No workflows yet"
            description="A workflow is a repeatable sequence of agent and tool steps, with conditions and approvals, that you can run on demand or on a schedule."
            action={
              <Button variant="primary" onClick={() => setCreating(true)}>
                <Plus /> New workflow
              </Button>
            }
          />
        </Card>
      ) : (
        <Card>
          <ul className="divide-y divide-line" aria-label="Workflows">
            {workflows.data.map((w) => (
              <li key={w.id}>
                <Link to={`/workflows/${w.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5 hover:bg-raised/60">
                  <WorkflowIcon className="size-4 text-fg-subtle" aria-hidden="true" />
                  <span className="min-w-0 flex-1 basis-48 truncate text-[13px]">
                    <strong className="font-medium">{w.name}</strong>
                    {w.description ? <span className="text-fg-muted"> · {w.description}</span> : null}
                  </span>
                  {!w.enabled ? <Badge>Off</Badge> : null}
                  <span className="font-mono text-[11px] text-fg-subtle">
                    {(w.definition.nodes ?? []).length} steps · v{w.version}
                  </span>
                  <span className="text-xs text-fg-subtle">{formatRelativeTime(w.updated_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {workflows.data.length ? (
        <Button className="mt-3" size="sm" onClick={() => setCreating(true)}>
          <Plus /> New workflow
        </Button>
      ) : null}
      <NewWorkflowDialog open={creating} onOpenChange={setCreating} projectId={projectId} />
    </>
  );
}

export function WorkflowsRoute() {
  const workflows = useWorkflows();
  const names = useMemo(() => new Map((workflows.data ?? []).map((w) => [w.id, w.name])), [workflows.data]);
  return (
    <Page>
      <PageHeader
        title="Workflows"
        description="Repeatable automations built from agents, tools, conditions and approvals. Every step goes through the same permissions and approvals as everything else."
      />
      <Section title="Workflows">
        <WorkflowList />
      </Section>
      <Section title="Recent runs">
        <Card>
          <WorkflowRunList names={names} />
        </Card>
      </Section>
    </Page>
  );
}
