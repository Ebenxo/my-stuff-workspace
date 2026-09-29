import { formatRelativeTime } from "@nexus/shared";
import { Badge, Button, Card, EmptyState, ErrorState, Skeleton, Switch, toast } from "@nexus/ui";
import { ShieldCheck } from "lucide-react";
import { useMemo } from "react";
import { RISK, RISK_ORDER } from "../agents/format";
import { useRevokeGrant, useSessionGrants, useToggleTool, useTools } from "../../lib/agentQueries";
import { errorMessage, useProjects } from "../../lib/queries";

export function ToolsSettings() {
  const tools = useTools();
  const toggle = useToggleTool();
  const grants = useSessionGrants();
  const revoke = useRevokeGrant();
  const projects = useProjects();
  const projectName = useMemo(() => new Map((projects.data ?? []).map((p) => [p.id, p.name])), [projects.data]);

  if (tools.isPending) return <Skeleton className="h-64" />;
  if (tools.isError) return <ErrorState message={errorMessage(tools.error)} onRetry={() => void tools.refetch()} />;

  return (
    <div className="space-y-8">
      <section>
        <h3 className="text-base font-semibold">Tools</h3>
        <p className="mt-0.5 max-w-xl text-[13px] text-fg-muted">
          Everything an agent can do goes through one of these. Turn a tool off and no agent can use it, whatever its instructions say.
        </p>
        <div className="mt-4 space-y-5">
          {RISK_ORDER.map((risk) => {
            const items = tools.data.filter((t) => t.risk_level === risk);
            if (!items.length) return null;
            return (
              <div key={risk}>
                <p className="mb-2 flex items-center gap-2 text-xs text-fg-subtle">
                  <Badge tone={RISK[risk].tone}>{RISK[risk].label}</Badge>
                  {RISK[risk].meaning}
                </p>
                <Card>
                  <ul className="divide-y divide-line">
                    {items.map((t) => (
                      <li key={t.name} className="flex items-start gap-3 px-3 py-2.5">
                        <div className="min-w-0 flex-1">
                          <p className="flex flex-wrap items-center gap-2">
                            <code className="font-mono text-xs font-medium">{t.name}</code>
                            {t.requires_approval ? <Badge tone="warning">Always asks</Badge> : null}
                          </p>
                          <p className="mt-0.5 text-[13px] text-fg-muted">{t.description}</p>
                        </div>
                        <Switch
                          aria-label={`${t.enabled ? "Disable" : "Enable"} ${t.name}`}
                          checked={t.enabled}
                          disabled={toggle.isPending}
                          onCheckedChange={(enabled) =>
                            toggle.mutate({ name: t.name, enabled }, { onError: (e) => toast.error(errorMessage(e)) })
                          }
                        />
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>
            );
          })}
        </div>
      </section>

      <section>
        <h3 className="text-base font-semibold">Approved for this session</h3>
        <p className="mt-0.5 max-w-xl text-[13px] text-fg-muted">
          Tools you chose not to be asked about again. These end when NEXUS restarts, and never apply to runs that have read outside content.
        </p>
        <Card className="mt-3">
          {grants.isPending ? (
            <Skeleton className="m-3 h-12" />
          ) : grants.isError ? (
            <ErrorState message={errorMessage(grants.error)} onRetry={() => void grants.refetch()} />
          ) : grants.data.length === 0 ? (
            <EmptyState icon={<ShieldCheck />} title="Nothing is pre-approved" description="Every action that needs approval will ask." />
          ) : (
            <ul className="divide-y divide-line">
              {grants.data.map((g) => (
                <li key={g.id} className="flex flex-wrap items-center gap-3 px-3 py-2.5 text-[13px]">
                  <code className="font-mono text-xs">{g.tool_name}</code>
                  <span className="text-fg-muted">in {g.project_id ? (projectName.get(g.project_id) ?? "a project") : "all projects"}</span>
                  <span className="text-xs text-fg-subtle">since {formatRelativeTime(g.created_at)}</span>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="ml-auto"
                    loading={revoke.isPending}
                    onClick={() => revoke.mutate(g.id, { onSuccess: () => toast.success("Approval withdrawn"), onError: (e) => toast.error(errorMessage(e)) })}
                  >
                    Withdraw
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>
    </div>
  );
}
