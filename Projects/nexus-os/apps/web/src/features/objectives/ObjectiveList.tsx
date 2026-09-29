import type { Objective } from "@nexus/schemas";
import { formatRelativeTime } from "@nexus/shared";
import { Badge, EmptyState, ErrorState, Skeleton } from "@nexus/ui";
import { Target } from "lucide-react";
import { Link } from "react-router";
import { useObjectives } from "../../lib/objectiveQueries";
import { errorMessage } from "../../lib/queries";
import { OBJECTIVE_STATUS, planOf } from "./format";

export function ObjectiveRow({ objective: o }: { objective: Objective }) {
  const status = OBJECTIVE_STATUS[o.status];
  const tasks = planOf(o)?.tasks.length ?? 0;
  return (
    <li>
      <Link to={`/objectives/${o.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5 transition-colors hover:bg-raised/60">
        <Badge tone={status.tone}>{status.label}</Badge>
        <span className="min-w-0 flex-1 basis-56 truncate text-[13px]">{o.text}</span>
        {o.private ? <Badge>On this device</Badge> : null}
        {tasks ? <span className="font-mono text-[11px] text-fg-subtle">{tasks} tasks</span> : null}
        <span className="text-xs text-fg-subtle">{formatRelativeTime(o.updated_at)}</span>
      </Link>
    </li>
  );
}

export function ObjectiveList({ projectId, limit = 20, empty }: { projectId?: string; limit?: number; empty?: string }) {
  const objectives = useObjectives({ ...(projectId ? { projectId } : {}), limit });
  if (objectives.isPending) return <Skeleton className="m-3 h-20" />;
  if (objectives.isError) return <ErrorState message={errorMessage(objectives.error)} onRetry={() => void objectives.refetch()} />;
  if (objectives.data.length === 0) {
    return (
      <EmptyState
        icon={<Target />}
        title="No objectives yet"
        description={empty ?? "Describe what you want done. NEXUS plans it, assigns agents, and checks the result."}
      />
    );
  }
  return (
    <ul className="divide-y divide-line" aria-label="Objectives">
      {objectives.data.map((o) => (
        <ObjectiveRow key={o.id} objective={o} />
      ))}
    </ul>
  );
}
