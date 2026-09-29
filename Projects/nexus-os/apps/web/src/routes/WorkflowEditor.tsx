import type { Workflow, WorkflowDefinition, WorkflowNodeType } from "@nexus/schemas";
import { formatRelativeTime } from "@nexus/shared";
import { Badge, Button, Card, CardContent, EmptyState, ErrorState, Input, Label, Skeleton, Switch, Tabs, TabsContent, TabsList, TabsTrigger, Textarea, toast } from "@nexus/ui";
import { AlertTriangle, CheckCircle2, ChevronLeft, Play, Save, Trash2 } from "lucide-react";
import { useDeferredValue, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { InputsEditor } from "../features/workflows/InputsEditor";
import { NodeInspector } from "../features/workflows/NodeInspector";
import { RunWorkflowDialog } from "../features/workflows/RunWorkflowDialog";
import { SchedulePanel } from "../features/workflows/SchedulePanel";
import { NODE_ICON } from "../features/workflows/icons";
import { WorkflowCanvas } from "../features/workflows/WorkflowCanvas";
import { WorkflowRunList } from "../features/workflows/WorkflowRunList";
import { ADDABLE, NODE_META, addAfter, issuesByNode, removeNode, updateNode } from "../features/workflows/model";
import { isNotFound } from "../lib/agentQueries";
import { errorMessage, useProject } from "../lib/queries";
import { useDeleteWorkflow, useSaveWorkflow, useValidation, useWorkflow, useWorkflowVersions } from "../lib/workflowQueries";
import { Page } from "./Page";

export function WorkflowEditorRoute() {
  const { workflowId = "" } = useParams();
  const workflow = useWorkflow(workflowId);
  if (workflow.isPending) {
    return (
      <Page className="max-w-7xl">
        <Skeleton className="mb-3 h-8 w-72" />
        <Skeleton className="h-[520px]" />
      </Page>
    );
  }
  if (workflow.isError) {
    return (
      <Page>
        {isNotFound(workflow.error) ? (
          <EmptyState
            title="Workflow not found"
            description="It may have been deleted."
            action={
              <Button asChild variant="primary">
                <Link to="/workflows">All workflows</Link>
              </Button>
            }
          />
        ) : (
          <ErrorState message={errorMessage(workflow.error)} onRetry={() => void workflow.refetch()} />
        )}
      </Page>
    );
  }
  // A saved version resets the draft; edits in progress survive refetches of the same version.
  return <Editor key={`${workflow.data.id}:${workflow.data.version}`} workflow={workflow.data} />;
}

function Versions({ workflowId }: { workflowId: string }) {
  const versions = useWorkflowVersions(workflowId);
  if (!versions.data) return <Skeleton className="h-16" />;
  return (
    <ul className="divide-y divide-line text-[13px]" aria-label="Versions">
      {versions.data.map((v) => (
        <li key={v.version} className="flex items-center gap-3 px-3 py-2">
          <span className="font-mono">v{v.version}</span>
          <span className="text-fg-muted">{(v.definition.nodes ?? []).length} steps</span>
          <span className="ml-auto text-xs text-fg-subtle">{formatRelativeTime(v.created_at)}</span>
        </li>
      ))}
    </ul>
  );
}

function Editor({ workflow }: { workflow: Workflow }) {
  const [draft, setDraft] = useState<WorkflowDefinition>(workflow.definition);
  const [name, setName] = useState(workflow.name);
  const [description, setDescription] = useState(workflow.description);
  const [selected, setSelected] = useState<string | undefined>();
  const [running, setRunning] = useState(false);
  const save = useSaveWorkflow(workflow.id);
  const remove = useDeleteWorkflow();
  const project = useProject(workflow.project_id);
  const navigate = useNavigate();
  const deferred = useDeferredValue(draft);
  const validation = useValidation(workflow.project_id, workflow.id, deferred);
  const { byNode, general } = useMemo(() => issuesByNode(validation.data), [validation.data]);

  const dirty = JSON.stringify(draft) !== JSON.stringify(workflow.definition) || name !== workflow.name || description !== workflow.description;
  const node = (draft.nodes ?? []).find((n) => n.id === selected);
  const valid = validation.data?.ok === true;

  function add(type: WorkflowNodeType) {
    // The new step follows the selected one (connected), so a sequence is built by clicking.
    const { def, id } = addAfter(draft, type, selected);
    setDraft(def);
    setSelected(id);
  }

  function persist() {
    save.mutate(
      { definition: draft, name: name.trim() || workflow.name, description },
      {
        onSuccess: (wf) => toast.success(wf.version !== workflow.version ? `Saved as version ${wf.version}` : "Saved"),
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  }

  return (
    <Page className="max-w-7xl">
      <p className="mb-3">
        <Link to="/workflows" className="inline-flex items-center gap-1 text-[13px] text-fg-muted hover:text-fg">
          <ChevronLeft className="size-4" aria-hidden="true" />
          Workflows{project.data ? ` · ${project.data.name}` : ""}
        </Link>
      </p>
      <header className="mb-4 flex flex-wrap items-center gap-3">
        <label htmlFor="wf-title" className="sr-only">
          Workflow name
        </label>
        <input
          id="wf-title"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={120}
          className="min-w-0 flex-1 basis-60 rounded-md bg-transparent px-1 text-xl font-semibold tracking-tight text-fg hover:bg-raised/50 focus-visible:outline-2 focus-visible:outline-ring"
        />
        <Badge>v{workflow.version}</Badge>
        {dirty ? <Badge tone="warning">Unsaved changes</Badge> : null}
        <label className="flex items-center gap-2 text-xs text-fg-muted">
          <Switch
            checked={workflow.enabled}
            onCheckedChange={(enabled) => save.mutate({ enabled }, { onError: (e) => toast.error(errorMessage(e)) })}
            aria-label="Workflow is on"
          />
          {workflow.enabled ? "On" : "Off"}
        </label>
        <Button size="sm" variant="primary" loading={save.isPending} disabled={!dirty} onClick={persist}>
          <Save /> Save
        </Button>
        <Button size="sm" disabled={dirty || !valid || !workflow.enabled} onClick={() => setRunning(true)} title={dirty ? "Save first" : !valid ? "Fix the problems first" : undefined}>
          <Play /> Run
        </Button>
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label="Delete workflow"
          onClick={() => {
            if (!window.confirm(`Delete “${workflow.name}”? Its run history is kept.`)) return;
            remove.mutate(workflow.id, { onSuccess: () => void navigate("/workflows"), onError: (e) => toast.error(errorMessage(e)) });
          }}
        >
          <Trash2 />
        </Button>
      </header>

      <div className="mb-3 flex flex-wrap items-center gap-1.5" role="toolbar" aria-label="Add a step">
        <span className="mr-1 text-xs text-fg-subtle">Add:</span>
        {ADDABLE.map((type) => {
          const Icon = NODE_ICON[type];
          return (
            <Button key={type} size="sm" variant="ghost" onClick={() => add(type)} title={NODE_META[type].description}>
              <Icon /> {NODE_META[type].label}
            </Button>
          );
        })}
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-3">
          <WorkflowCanvas definition={draft} selectedId={selected} onSelect={setSelected} onChange={setDraft} issues={byNode} />
          <p className="text-xs text-fg-subtle">
            A new step follows the selected one. To connect steps yourself, drag from the bottom of a step to the top of another. Select a
            connection or step and press Delete to remove it.
          </p>
          <div role="status" aria-live="polite" className="text-[13px]">
            {validation.data?.ok ? (
              <p className="flex items-center gap-1.5 text-success">
                <CheckCircle2 className="size-4" aria-hidden="true" /> Ready to run.
              </p>
            ) : validation.data ? (
              <div className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2">
                <p className="flex items-center gap-1.5 font-medium text-fg">
                  <AlertTriangle className="size-4 text-warning" aria-hidden="true" />
                  {validation.data.issues.length} {validation.data.issues.length === 1 ? "thing needs" : "things need"} fixing before this can run
                </p>
                <ul className="mt-1 list-disc pl-5 text-xs text-fg-muted">
                  {general.map((g) => (
                    <li key={g}>{g}</li>
                  ))}
                  {[...byNode.entries()].map(([id, msgs]) => (
                    <li key={id}>
                      <button type="button" className="font-mono text-accent-text hover:underline" onClick={() => setSelected(id)}>
                        {id}
                      </button>
                      : {msgs.join(" ")}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </div>
        <Card>
          <CardContent className="pt-4">
            {node ? (
              <NodeInspector
                key={node.id}
                node={node}
                projectId={workflow.project_id}
                workflowId={workflow.id}
                issues={byNode.get(node.id) ?? []}
                onChange={(patch) => setDraft(updateNode(draft, node.id, patch))}
                onDelete={() => {
                  setDraft(removeNode(draft, node.id));
                  setSelected(undefined);
                }}
              />
            ) : (
              <div className="space-y-4">
                <div>
                  <Label htmlFor="wf-description">What it is for</Label>
                  <Textarea id="wf-description" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
                </div>
                <div>
                  <p className="mb-1.5 text-[13px] font-medium">Inputs</p>
                  <InputsEditor inputs={draft.inputs ?? []} onChange={(inputs) => setDraft({ ...draft, inputs })} />
                </div>
                <p className="text-xs text-fg-subtle">Select a step on the canvas to configure it.</p>
                <label htmlFor="wf-id" className="sr-only">
                  Workflow id
                </label>
                <Input id="wf-id" readOnly value={workflow.id} className="font-mono text-xs text-fg-subtle" />
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="runs" className="mt-8">
        <TabsList>
          <TabsTrigger value="runs">Runs</TabsTrigger>
          <TabsTrigger value="schedules">Schedules</TabsTrigger>
          <TabsTrigger value="versions">Versions</TabsTrigger>
        </TabsList>
        <TabsContent value="runs">
          <Card>
            <WorkflowRunList workflowId={workflow.id} />
          </Card>
        </TabsContent>
        <TabsContent value="schedules">
          <SchedulePanel workflow={workflow} />
        </TabsContent>
        <TabsContent value="versions">
          <Card>
            <Versions workflowId={workflow.id} />
          </Card>
        </TabsContent>
      </Tabs>

      <RunWorkflowDialog workflow={workflow} open={running} onOpenChange={setRunning} />
    </Page>
  );
}
