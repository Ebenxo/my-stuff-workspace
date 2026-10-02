import type { AgentRun } from "@nexus/schemas";
import { formatDuration, formatRelativeTime } from "@nexus/shared";
import { Badge, EmptyState, ErrorState, Skeleton } from "@nexus/ui";
import { Bot } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router";
import { useAgents, useRuns, type RunFilter } from "../../lib/agentQueries";
import { errorMessage } from "../../lib/queries";
import { RUN_STATUS, runDuration, totalTokens } from "./format";

export function RunRow({ run, agentName }: { run: AgentRun; agentName: string }) {
  const status = RUN_STATUS[run.status];
  return (
    <li>
      <Link to={`/runs/${run.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5 transition-colors hover:bg-raised/60">
        <Badge tone={status.tone}>{status.label}</Badge>
        <span className="min-w-0 flex-1 basis-56 truncate text-[13px]">
          <strong className="font-medium">{agentName}</strong>
          {run.prompt ? <span className="text-fg-muted"> · {run.prompt}</span> : null}
        </span>
        <span className="font-mono text-[11px] text-fg-subtle">
          {run.step_count} steps · {run.tool_call_count} tools · {totalTokens(run).toLocaleString()} tokens
          {run.finished_at ? ` · ${formatDuration(runDuration(run))}` : ""}
        </span>
        <span className="text-xs text-fg-subtle">{formatRelativeTime(run.started_at)}</span>
      </Link>
    </li>
  );
}

export function RunList({ filter, empty }: { filter?: RunFilter; empty?: string }) {
  const runs = useRuns(filter ?? {}, 5_000);
  const agents = useAgents();
  const names = useMemo(() => new Map((agents.data ?? []).map((a) => [a.id, a.name])), [agents.data]);

  if (runs.isPending) return <Skeleton className="m-3 h-24" />;
  if (runs.isError) return <ErrorState message={errorMessage(runs.error)} onRetry={() => void runs.refetch()} />;
  if (runs.data.length === 0) {
    return (
      <EmptyState
        icon={<Bot />}
        title="No runs yet"
        description={empty ?? "Run an agent and its work will be listed here, with every step it took."}
      />
    );
  }
  return (
    <ul className="divide-y divide-line" aria-label="Agent runs">
      {runs.data.map((r) => (
        <RunRow key={r.id} run={r} agentName={names.get(r.agent_id) ?? "Agent"} />
      ))}
    </ul>
  );
}
