import type { Objective } from "@nexus/schemas";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@nexus/ui";
import { ShieldAlert } from "lucide-react";
import { planOf, strategyOf } from "./format";

function Bullets({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <p className="text-[11px] font-medium uppercase tracking-wider text-fg-subtle">{title}</p>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[13px]">
        {items.map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
    </div>
  );
}

/** The plan as the person reviews it before anything runs. */
export function PlanView({ objective }: { objective: Objective }) {
  const plan = planOf(objective);
  const strategy = strategyOf(objective);
  if (!plan) return null;
  const approvals = plan.tasks.filter((t) => t.approvalRequired);
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-3 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <Card>
        <CardHeader>
          <CardTitle>Plan · {plan.tasks.length} {plan.tasks.length === 1 ? "task" : "tasks"}</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-2">
            {plan.tasks.map((t) => (
              <li key={t.key} className="rounded-md border border-line px-3 py-2 text-[13px]">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-fg-subtle">{t.key}</span>
                  <strong className="font-medium">{t.title}</strong>
                  <Badge>{t.agent.replaceAll("_", " ")}</Badge>
                  {t.review ? <Badge tone="info">Reviewed by the Critic</Badge> : null}
                  {t.approvalRequired ? <Badge tone="warning">Will ask for approval</Badge> : null}
                  {t.optional ? <Badge>Optional</Badge> : null}
                </div>
                {t.description ? <p className="mt-1 text-fg-muted">{t.description}</p> : null}
                <p className="mt-1 text-xs text-fg-subtle">
                  {t.dependsOn.length ? `After ${t.dependsOn.join(", ")}` : "Can start immediately"}
                  {t.tools.length ? ` · tools: ${t.tools.join(", ")}` : ""}
                </p>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
      <div className="space-y-3">
        {strategy ? (
          <Card>
            <CardHeader>
              <CardTitle>Approach</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-[13px]">
              <p className="font-medium capitalize">{strategy.name}</p>
              <p className="text-fg-muted">{strategy.rationale}</p>
              <p className="text-xs text-fg-subtle">About {Math.round(strategy.tokens / 1000)}k tokens, estimated</p>
            </CardContent>
          </Card>
        ) : null}
        <Card>
          <CardContent className="space-y-3 pt-4">
            <Bullets title="Done when" items={plan.criteria} />
            <Bullets title="Assumptions" items={plan.assumptions} />
            <Bullets title="Risks" items={plan.risks} />
            {approvals.length ? (
              <p className="flex gap-2 text-[13px] text-warning">
                <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                {approvals.length} {approvals.length === 1 ? "task" : "tasks"} will ask for your approval before acting.
              </p>
            ) : null}
            {plan.warnings.length ? <Bullets title="Adjusted by NEXUS" items={plan.warnings} /> : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
