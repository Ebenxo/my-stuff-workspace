import { formatRelativeTime } from "@nexus/shared";
import { Badge, EmptyState, ErrorState, Skeleton } from "@nexus/ui";
import { Wrench } from "lucide-react";
import { Link } from "react-router";
import { RISK, TOOL_STATUS } from "../agents/format";
import { useToolCalls } from "../../lib/agentQueries";
import { errorMessage } from "../../lib/queries";

export function ToolCallList({ projectId, runId, limit = 50 }: { projectId?: string; runId?: string; limit?: number }) {
  const calls = useToolCalls({ ...(projectId ? { projectId } : {}), ...(runId ? { runId } : {}), limit });
  if (calls.isPending) return <Skeleton className="m-3 h-20" />;
  if (calls.isError) return <ErrorState message={errorMessage(calls.error)} onRetry={() => void calls.refetch()} />;
  if (calls.data.length === 0) {
    return <EmptyState icon={<Wrench />} title="No tool activity yet" description="Every tool an agent uses is listed here with its risk, outcome and timing." />;
  }
  return (
    <ul className="divide-y divide-line" aria-label="Tool calls">
      {calls.data.map((c) => {
        const status = TOOL_STATUS[c.status];
        const risk = RISK[c.risk_level];
        return (
          <li key={c.id} className="px-3 py-2 text-[13px]">
            <div className="flex flex-wrap items-center gap-2">
              <code className="font-mono text-xs">{c.tool_name}</code>
              <Badge tone={status.tone}>{status.label}</Badge>
              <Badge tone={risk.tone}>{risk.label}</Badge>
              {c.duration_ms != null ? <span className="font-mono text-[11px] text-fg-subtle">{c.duration_ms} ms</span> : null}
              <span className="ml-auto text-xs text-fg-subtle">{formatRelativeTime(c.started_at)}</span>
            </div>
            {c.summary ? <p className="mt-0.5 text-fg-muted">{c.summary}</p> : null}
            {c.error ? <p className="mt-0.5 text-xs text-danger">{String(c.error["message"] ?? c.error["code"] ?? "")}</p> : null}
            {c.run_id ? (
              <Link to={`/runs/${c.run_id}`} className="mt-0.5 inline-block text-xs text-accent-text hover:underline">
                View run
              </Link>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
