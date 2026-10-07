import type { NodeState, WorkflowNode } from "@nexus/schemas";
import { formatRelativeTime } from "@nexus/shared";
import { Badge, Button, Card, CardContent, EmptyState, ErrorState, Skeleton, Textarea, toast } from "@nexus/ui";
import { Ban, Check, ChevronLeft, ExternalLink, RotateCcw, X } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { WorkflowCanvas } from "../features/workflows/WorkflowCanvas";
import { NODE_META, NODE_STATUS, RUN_STATUS, formatValue } from "../features/workflows/model";
import { isNotFound } from "../lib/agentQueries";
import { errorMessage } from "../lib/queries";
import { useNodeDecision, useRunAction, useWorkflowRun } from "../lib/workflowQueries";
import { Page, PageHeader, Section } from "./Page";

function Decision({ runId, node, state }: { runId: string; node: WorkflowNode; state: NodeState }) {
  const decide = useNodeDecision(runId);
  const [text, setText] = useState("");
  const onError = (e: unknown) => toast.error(errorMessage(e));
  const out = (state.output ?? {}) as Record<string, unknown>;
  const err = (state.error ?? {}) as Record<string, unknown>;

  if (node.type === "approval") {
    return (
      <div role="region" aria-label="Your decision" className="space-y-2 rounded-lg border border-warning/40 bg-warning/10 p-3">
        <p className="text-sm text-fg">{String(out["message"] ?? "Approve to continue.")}</p>
        <label htmlFor="decision-note" className="sr-only">
          Note
        </label>
        <Textarea id="decision-note" rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Optional note" />
        <div className="flex gap-2">
          <Button size="sm" variant="primary" loading={decide.isPending} onClick={() => decide.mutate({ node: node.id, action: "approve", text }, { onSuccess: () => toast.success("Approved"), onError })}>
            <Check /> Approve
          </Button>
          <Button size="sm" disabled={decide.isPending} onClick={() => decide.mutate({ node: node.id, action: "reject", text }, { onSuccess: () => toast.success("Rejected"), onError })}>
            <X /> Reject
          </Button>
        </div>
      </div>
    );
  }
  if (err["code"] === "needs_input") {
    const options = Array.isArray(err["options"]) ? (err["options"] as unknown[]).filter((o): o is string => typeof o === "string") : [];
    const send = (answer: string) => decide.mutate({ node: node.id, action: "answer", text: answer }, { onSuccess: () => toast.success("Sent. The agent is continuing."), onError });
    return (
      <div role="region" aria-label="Question for you" className="space-y-2 rounded-lg border border-warning/40 bg-warning/10 p-3">
        <p className="text-sm text-fg">{String(err["message"] ?? "")}</p>
        {options.length ? (
          <div className="flex flex-wrap gap-2">
            {options.map((o) => (
              <Button key={o} size="sm" disabled={decide.isPending} onClick={() => send(o)}>
                {o}
              </Button>
            ))}
          </div>
        ) : null}
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim()) send(text.trim());
          }}
        >
          <label htmlFor="answer-text" className="sr-only">
            Your answer
          </label>
          <Textarea id="answer-text" rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Type your answer…" />
          <Button type="submit" size="sm" variant="primary" disabled={!text.trim()} loading={decide.isPending} className="self-start">
            Send answer
          </Button>
        </form>
      </div>
    );
  }
  if (state.approval_id || state.run_id) {
    return (
      <p className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-[13px]">
        {node.type === "tool" ? "This tool action is waiting for your approval." : "The agent is waiting for your approval of an action."}{" "}
        <Link to="/approvals" className="text-accent-text underline">
          Review it
        </Link>
      </p>
    );
  }
  return null;
}

function StepDetails({ runId, node, state }: { runId: string; node: WorkflowNode; state: NodeState | undefined }) {
  const status = state?.status ? NODE_STATUS[state.status] : NODE_STATUS.PENDING;
  const err = (state?.error ?? null) as Record<string, unknown> | null;
  return (
    <Card>
      <CardContent className="space-y-3 pt-4 text-[13px]">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs text-fg-subtle">{node.id}</span>
          <Badge>{NODE_META[node.type].label}</Badge>
          <Badge tone={status.tone}>{status.label}</Badge>
        </div>
        <h3 className="text-sm font-semibold">{node.label || NODE_META[node.type].label}</h3>
        {state?.started_at ? (
          <p className="text-xs text-fg-subtle">
            Started {formatRelativeTime(state.started_at)}
            {state.finished_at ? ` · finished ${formatRelativeTime(state.finished_at)}` : ""}
            {(state.attempts ?? 0) > 1 ? ` · attempt ${state.attempts}` : ""}
          </p>
        ) : null}
        {state?.status === "WAITING" ? <Decision runId={runId} node={node} state={state} /> : null}
        {err && state?.status !== "WAITING" ? (
          <p role="alert" className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-fg">
            {String(err["message"] ?? "This step failed.")}
          </p>
        ) : null}
        {state?.output != null && state.status !== "WAITING" ? (
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-fg-subtle">Output</p>
            <pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md bg-canvas p-2 font-mono text-xs">{formatValue(state.output)}</pre>
          </div>
        ) : null}
        {state?.run_id ? (
          <Link to={`/runs/${state.run_id}`} className="inline-flex items-center gap-1 text-accent-text hover:underline">
            See every step the agent took <ExternalLink className="size-3.5" aria-hidden="true" />
          </Link>
        ) : null}
        {state?.child_run_id ? (
          <Link to={`/workflow-runs/${state.child_run_id}`} className="inline-flex items-center gap-1 text-accent-text hover:underline">
            Open the sub-workflow run <ExternalLink className="size-3.5" aria-hidden="true" />
          </Link>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function WorkflowRunRoute() {
  const { runId = "" } = useParams();
  const detail = useWorkflowRun(runId);
  const act = useRunAction(runId);
  const [picked, setPicked] = useState<string | undefined>();

  if (detail.isPending) {
    return (
      <Page className="max-w-7xl">
        <Skeleton className="mb-3 h-8 w-72" />
        <Skeleton className="h-[520px]" />
      </Page>
    );
  }
  if (detail.isError) {
    return (
      <Page>
        {isNotFound(detail.error) ? (
          <EmptyState title="Run not found" description="The link may be wrong." />
        ) : (
          <ErrorState message={errorMessage(detail.error)} onRetry={() => void detail.refetch()} />
        )}
      </Page>
    );
  }

  const { run, definition, name } = detail.data;
  const status = RUN_STATUS[run.status];
  const nodes = definition.nodes ?? [];
  const waiting = nodes.find((n) => run.node_states[n.id]?.status === "WAITING");
  const failed = nodes.find((n) => run.node_states[n.id]?.status === "FAILED");
  const selected = nodes.find((n) => n.id === picked) ?? waiting ?? failed;
  const settled = Object.values(run.node_states).filter((s) => s.status === "COMPLETED" || s.status === "SKIPPED").length;
  const onError = (e: unknown) => toast.error(errorMessage(e));

  return (
    <Page className="max-w-7xl">
      <p className="mb-3">
        <Link to={`/workflows/${run.workflow_id}`} className="inline-flex items-center gap-1 text-[13px] text-fg-muted hover:text-fg">
          <ChevronLeft className="size-4" aria-hidden="true" />
          {name}
        </Link>
      </p>
      <PageHeader
        title={`${name} · run`}
        description={`Version ${run.workflow_version} · started ${formatRelativeTime(run.started_at)} · ${settled} of ${nodes.length} steps done`}
        badges={
          <>
            <Badge tone={status.tone}>{status.label}</Badge>
            {run.unattended ? <Badge>Scheduled</Badge> : null}
          </>
        }
        actions={
          <>
            {run.status === "RUNNING" || run.status === "WAITING" ? (
              <Button size="sm" variant="danger" loading={act.isPending} onClick={() => act.mutate("cancel", { onSuccess: () => toast.success("Cancelled"), onError })}>
                <Ban /> Cancel
              </Button>
            ) : null}
            {run.status === "FAILED" ? (
              <Button size="sm" variant="primary" loading={act.isPending} onClick={() => act.mutate("retry", { onSuccess: () => toast.success("Retrying the failed steps"), onError })}>
                <RotateCcw /> Retry failed steps
              </Button>
            ) : null}
          </>
        }
      />
      {run.error && run.status !== "CANCELLED" ? (
        <div role="alert" className="mb-4 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-[13px]">
          {run.error["node"] ? <span className="font-mono text-xs">{String(run.error["node"])}: </span> : null}
          {String(run.error["message"] ?? "The run failed.")}
        </div>
      ) : null}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <WorkflowCanvas definition={definition} states={run.node_states} selectedId={selected?.id} onSelect={setPicked} />
        {selected ? (
          <StepDetails runId={run.id} node={selected} state={run.node_states[selected.id]} />
        ) : (
          <p className="text-[13px] text-fg-muted">Select a step to see what it did.</p>
        )}
      </div>
      {Object.keys(run.outputs).length ? (
        <Section title="Outputs">
          <Card>
            <CardContent className="pt-4">
              <pre className="whitespace-pre-wrap break-words font-mono text-xs">{formatValue(run.outputs)}</pre>
            </CardContent>
          </Card>
        </Section>
      ) : null}
    </Page>
  );
}
