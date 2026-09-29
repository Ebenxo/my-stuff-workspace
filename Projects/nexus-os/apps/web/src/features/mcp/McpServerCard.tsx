import type { McpServer } from "@nexus/schemas";
import { formatRelativeTime } from "@nexus/shared";
import { Badge, Button, Card, toast } from "@nexus/ui";
import { ChevronDown, Pencil, Play, Square, Stethoscope, Trash2 } from "lucide-react";
import { useState } from "react";
import { useDeleteMcpServer, useMcpAction, type McpAction } from "../../lib/mcpQueries";
import { errorMessage } from "../../lib/queries";
import { RISK } from "../agents/format";
import { McpServerDetails } from "./McpServerDetails";
import { MCP_STATUS, countLine, launchLine } from "./model";

export function McpServerCard({ server, onEdit }: { server: McpServer; onEdit: () => void }) {
  const [open, setOpen] = useState(false);
  const action = useMcpAction();
  const remove = useDeleteMcpServer();
  const status = MCP_STATUS[server.status];
  const running = server.status === "running";
  const health = server.last_health;

  function run(a: McpAction) {
    action.mutate(
      { id: server.id, action: a },
      {
        onSuccess: (s) => {
          if (a === "check") {
            if (s.last_health?.ok) toast.success(`${s.name} answered in ${s.last_health.latency_ms ?? "?"} ms`);
            else toast.error(`${s.name}: ${s.last_health?.message ?? "no answer"}`);
          } else if (s.status === "error") toast.error(`${s.name} did not start: ${s.error ?? "unknown problem"}`);
          else toast.success(a === "start" ? `${s.name} is running` : `${s.name} stopped`);
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  }

  return (
    <Card>
      <div className="flex flex-wrap items-start gap-3 p-4">
        <div className="min-w-0 flex-1 basis-64">
          <p className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{server.name}</span>
            <Badge tone={status.tone}>{status.label}</Badge>
            <Badge tone={RISK[server.risk_level].tone}>{RISK[server.risk_level].label} risk</Badge>
            <Badge>{server.transport === "http" ? "Web address" : "Program"}</Badge>
          </p>
          {server.description ? <p className="mt-0.5 text-[13px] text-fg-muted">{server.description}</p> : null}
          <p className="mt-1 truncate font-mono text-xs text-fg-subtle" title={launchLine(server)}>
            {launchLine(server)}
          </p>
          {running ? (
            <p className="mt-1 text-xs text-fg-muted">
              {countLine(server)}
              {server.server_name ? ` · reports itself as ${server.server_name}${server.server_version ? ` ${server.server_version}` : ""}` : ""}
            </p>
          ) : null}
          {server.error ? (
            <p role="alert" className="mt-2 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-fg">
              {server.error}
            </p>
          ) : null}
          {health ? (
            <p className="mt-1 text-xs text-fg-subtle">
              Last check {formatRelativeTime(health.checked_at)}: {health.ok ? (health.latency_ms != null ? `answered in ${health.latency_ms} ms` : health.message) : health.message}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {running || server.status === "starting" ? (
            <>
              <Button size="sm" variant="ghost" onClick={() => run("check")} loading={action.isPending && action.variables?.action === "check"}>
                <Stethoscope /> Check
              </Button>
              <Button size="sm" onClick={() => run("stop")} loading={action.isPending && action.variables?.action === "stop"}>
                <Square /> Stop
              </Button>
            </>
          ) : (
            <Button size="sm" variant="primary" onClick={() => run("start")} loading={action.isPending && action.variables?.action === "start"}>
              <Play /> Start
            </Button>
          )}
          <Button size="icon-sm" variant="ghost" aria-label={`Edit ${server.name}`} onClick={onEdit}>
            <Pencil />
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label={`Remove ${server.name}`}
            onClick={() => {
              if (!window.confirm(`Remove “${server.name}”? Its tools disappear from every agent, and its saved secrets are deleted.`)) return;
              remove.mutate(server.id, { onSuccess: () => toast.success(`${server.name} removed`), onError: (e) => toast.error(errorMessage(e)) });
            }}
          >
            <Trash2 />
          </Button>
        </div>
      </div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1 border-t border-line px-4 py-2 text-left text-xs text-fg-muted hover:bg-raised/50 hover:text-fg"
      >
        <ChevronDown className={`size-4 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true" />
        {open ? "Hide" : "Show"} tools, resources, prompts and log
      </button>
      {open ? <McpServerDetails serverId={server.id} running={running} /> : null}
    </Card>
  );
}
