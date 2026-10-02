import { EmptyState, ErrorState, Skeleton } from "@nexus/ui";
import { ShieldCheck } from "lucide-react";
import { useMemo } from "react";
import { useAgents, useApprovals } from "../../lib/agentQueries";
import { errorMessage } from "../../lib/queries";
import { ApprovalCard } from "./ApprovalCard";

/** Pending requests first (they block work), then the latest decisions for context. */
export function ApprovalsPanel({ projectId, showHistory = true }: { projectId?: string; showHistory?: boolean }) {
  const pending = useApprovals("PENDING", projectId);
  const all = useApprovals(undefined, projectId, 30);
  const agents = useAgents();
  const names = useMemo(() => new Map((agents.data ?? []).map((a) => [a.id, a.name])), [agents.data]);
  const history = useMemo(() => (all.data ?? []).filter((a) => a.status !== "PENDING").slice(0, 10), [all.data]);

  if (pending.isPending) return <Skeleton className="m-3 h-40" />;
  if (pending.isError) return <ErrorState message={errorMessage(pending.error)} onRetry={() => void pending.refetch()} />;

  return (
    <div className="space-y-4 p-3">
      {pending.data.length === 0 ? (
        <EmptyState
          icon={<ShieldCheck />}
          title="Nothing needs your approval"
          description="When an agent wants to do something that needs your say-so, it will wait here."
        />
      ) : (
        <ul className="space-y-3" aria-label="Waiting for your approval">
          {pending.data.map((a) => (
            <li key={a.id}>
              <ApprovalCard approval={a} agentName={a.agent_id ? names.get(a.agent_id) : undefined} />
            </li>
          ))}
        </ul>
      )}
      {showHistory && history.length > 0 ? (
        <section aria-label="Recent decisions">
          <h3 className="mb-2 text-[11px] font-medium uppercase tracking-wider text-fg-subtle">Recent decisions</h3>
          <ul className="space-y-2">
            {history.map((a) => (
              <li key={a.id}>
                <ApprovalCard approval={a} agentName={a.agent_id ? names.get(a.agent_id) : undefined} readOnly />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
