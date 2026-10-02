import { Badge, Button, Card, CardContent } from "@nexus/ui";
import { Play, Settings2 } from "lucide-react";
import { RISK, type AgentView } from "./format";
import { AgentIcon } from "./icons";

export function AgentCard({
  agent,
  onRun,
  onEdit,
}: {
  agent: AgentView;
  onRun: () => void;
  onEdit: () => void;
}) {
  const risk = RISK[agent.maxRisk];
  const disabled = agent.status === "disabled";
  return (
    <Card className={disabled ? "opacity-70" : undefined}>
      <CardContent className="pt-4">
        <div className="flex items-start gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-raised text-accent-text">
            <AgentIcon name={agent.icon} className="size-5" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold">{agent.name}</h3>
              {agent.builtin ? <Badge>Built-in</Badge> : <Badge tone="accent">Custom</Badge>}
              {disabled ? <Badge tone="warning">Disabled</Badge> : null}
            </div>
            <p className="mt-0.5 text-[13px] text-fg-muted">{agent.role}</p>
          </div>
        </div>
        {agent.description ? <p className="mt-3 text-[13px] text-fg-muted">{agent.description}</p> : null}
        <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-fg-subtle">
          <div className="flex gap-1.5">
            <dt>Can use</dt>
            <dd className="font-medium text-fg-muted">{agent.tools.length} tools</dd>
          </div>
          <div className="flex gap-1.5">
            <dt>Reach</dt>
            <dd>
              <Badge tone={risk.tone}>{risk.label}</Badge>
            </dd>
          </div>
          <div className="flex gap-1.5">
            <dt>Limit</dt>
            <dd className="font-medium text-fg-muted">{agent.maxSteps} steps</dd>
          </div>
        </dl>
        <div className="mt-4 flex gap-2">
          <Button size="sm" variant="primary" onClick={onRun} disabled={disabled}>
            <Play /> Run
          </Button>
          <Button size="sm" onClick={onEdit}>
            <Settings2 /> {agent.builtin ? "Tune" : "Edit"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
