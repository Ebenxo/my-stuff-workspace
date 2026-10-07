import { formatRelativeTime } from "@nexus/shared";
import { Badge, EmptyState, ErrorState, Skeleton } from "@nexus/ui";
import { Workflow as WorkflowIcon } from "lucide-react";
import { Link } from "react-router";
import { errorMessage } from "../../lib/queries";
import { useWorkflowRuns } from "../../lib/workflowQueries";
import { RUN_STATUS } from "./model";

export function WorkflowRunList({ workflowId, projectId, names }: { workflowId?: string; projectId?: string; names?: Map<string, string> }) {
  const runs = useWorkflowRuns({ ...(workflowId ? { workflowId } : {}), ...(projectId ? { projectId } : {}) });
  if (runs.isPending) return <Skeleton className="m-3 h-16" />;
  if (runs.isError) return <ErrorState message={errorMessage(runs.error)} onRetry={() => void runs.refetch()} />;
  if (runs.data.length === 0) return <EmptyState icon={<WorkflowIcon />} title="No runs yet" description="Run the workflow, or give it a schedule." />;
  return (
    <ul className="divide-y divide-line" aria-label="Workflow runs">
      {runs.data.map((r) => {
        const status = RUN_STATUS[r.status];
        const steps = Object.values(r.node_states);
        const done = steps.filter((s) => s.status === "COMPLETED" || s.status === "SKIPPED").length;
        return (
          <li key={r.id}>
            <Link to={`/workflow-runs/${r.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5 hover:bg-raised/60">
              <Badge tone={status.tone}>{status.label}</Badge>
              <span className="min-w-0 flex-1 basis-40 truncate text-[13px]">
                {names?.get(r.workflow_id) ? <strong className="font-medium">{names.get(r.workflow_id)} · </strong> : null}
                <span className="text-fg-muted">
                  {done} of {steps.length} steps · v{r.workflow_version}
                </span>
              </span>
              {r.unattended ? <Badge>Scheduled</Badge> : null}
              <span className="text-xs text-fg-subtle">{formatRelativeTime(r.started_at)}</span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
