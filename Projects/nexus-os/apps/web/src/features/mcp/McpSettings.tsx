import type { McpServer } from "@nexus/schemas";
import { Button, EmptyState, ErrorState, Skeleton } from "@nexus/ui";
import { Plug, Plus } from "lucide-react";
import { useState } from "react";
import { useMcpServers } from "../../lib/mcpQueries";
import { useParamFlag } from "../../lib/useParamFlag";
import { errorMessage } from "../../lib/queries";
import { McpServerCard } from "./McpServerCard";
import { McpServerDialog } from "./McpServerDialog";

export function McpSettings() {
  const servers = useMcpServers();
  const [editing, setEditing] = useState<McpServer | undefined>();
  const [adding, setAdding] = useParamFlag("add");

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1 basis-72">
          <h3 className="text-base font-semibold">MCP servers</h3>
          <p className="mt-0.5 max-w-2xl text-[13px] text-fg-muted">
            Connect tools from other programs through the Model Context Protocol. A server's tools appear under Tools &amp; approvals, at high risk unless you
            choose otherwise. Agents use them only if you add them to an agent, every call is checked and logged like any other tool, their results are
            treated as outside content, and they are never available to runs kept on this device.
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={() => setAdding(true)}>
          <Plus /> Add server
        </Button>
      </div>
      {servers.isPending ? (
        <Skeleton className="h-32" />
      ) : servers.isError ? (
        <ErrorState message={errorMessage(servers.error)} onRetry={() => void servers.refetch()} />
      ) : servers.data.length === 0 ? (
        <EmptyState
          icon={<Plug />}
          title="No MCP servers yet"
          description="Add a program on this computer (for example one started with npx or uvx) or a server's web address."
          action={
            <Button variant="primary" onClick={() => setAdding(true)}>
              <Plus /> Add server
            </Button>
          }
        />
      ) : (
        <div className="space-y-3">
          {servers.data.map((s) => (
            <McpServerCard key={s.id} server={s} onEdit={() => setEditing(s)} />
          ))}
        </div>
      )}
      <McpServerDialog
        open={adding || editing !== undefined}
        server={editing}
        onOpenChange={(o) => {
          if (o) return;
          setAdding(false);
          setEditing(undefined);
        }}
      />
    </section>
  );
}
