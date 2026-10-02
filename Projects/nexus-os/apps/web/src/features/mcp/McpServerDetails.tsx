import type { McpTool, ResourceContent } from "@nexus/schemas";
import { Badge, Button, EmptyState, ErrorState, Skeleton, Switch, Tabs, TabsContent, TabsList, TabsTrigger, toast } from "@nexus/ui";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useToggleTool } from "../../lib/agentQueries";
import { useMcpLog, useMcpServer, useReadResource } from "../../lib/mcpQueries";
import { errorMessage } from "../../lib/queries";

function argumentsLine(tool: McpTool): string {
  const schema = tool.input_schema as { properties?: Record<string, unknown>; required?: string[] };
  const names = Object.keys(schema.properties ?? {});
  if (!names.length) return "No arguments";
  const required = new Set(schema.required ?? []);
  return `Arguments: ${names.map((n) => (required.has(n) ? `${n} (required)` : n)).join(", ")}`;
}

function ToolRow({ tool, running }: { tool: McpTool; running: boolean }) {
  const toggle = useToggleTool();
  return (
    <li className="flex items-start gap-3 px-3 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2">
          <code className="font-mono text-xs font-medium break-all">{tool.name}</code>
          {tool.title ? <span className="text-xs text-fg-muted">{tool.title}</span> : null}
        </p>
        <p className="mt-0.5 text-[13px] text-fg-muted">{tool.description}</p>
        <p className="mt-0.5 text-xs text-fg-subtle">{argumentsLine(tool)}</p>
        {tool.hints?.length ? <p className="mt-0.5 text-xs text-fg-subtle">{tool.hints.join(" ")} (A claim by the server, not a guarantee.)</p> : null}
        {tool.note ? (
          <p className="mt-1.5 flex gap-1.5 rounded-md border border-warning/40 bg-warning/10 px-2 py-1.5 text-xs text-fg">
            <AlertTriangle className="mt-px size-3.5 shrink-0 text-warning" aria-hidden="true" />
            {tool.note}
          </p>
        ) : null}
      </div>
      <Switch
        aria-label={`${tool.enabled ? "Turn off" : "Turn on"} ${tool.name}`}
        checked={tool.enabled ?? true}
        disabled={toggle.isPending}
        onCheckedChange={(enabled) =>
          toggle.mutate(
            { name: tool.name, enabled },
            { onError: (e) => toast.error(errorMessage(e)), onSuccess: () => (running ? undefined : toast.success("Saved for when the server runs")) },
          )
        }
      />
    </li>
  );
}

function ResourcePreview({ content }: { content: ResourceContent[] }) {
  return (
    <div className="mt-2 space-y-2">
      {content.map((c, i) => (
        <div key={i}>
          <p className="text-xs text-fg-subtle">
            {c.uri} {c.mime_type ? `· ${c.mime_type}` : ""}
          </p>
          {c.text != null ? (
            <pre className="mt-1 max-h-64 overflow-auto rounded-md bg-sunken p-2 font-mono text-xs whitespace-pre-wrap break-words">
              {c.text}
              {c.truncated ? "\n…" : ""}
            </pre>
          ) : (
            <p className="mt-1 text-xs text-fg-muted">{c.note}</p>
          )}
        </div>
      ))}
    </div>
  );
}

export function McpServerDetails({ serverId, running }: { serverId: string; running: boolean }) {
  const detail = useMcpServer(serverId);
  const [tab, setTab] = useState("tools");
  const log = useMcpLog(serverId, tab === "log");
  const read = useReadResource(serverId);
  const [opened, setOpened] = useState<{ uri: string; content: ResourceContent[] } | undefined>();

  if (detail.isPending) return <Skeleton className="m-3 h-24" />;
  if (detail.isError) return <ErrorState message={errorMessage(detail.error)} onRetry={() => void detail.refetch()} />;
  const d = detail.data;
  const tools = d.tools ?? [];
  const resources = d.resources ?? [];
  const prompts = d.prompts ?? [];

  return (
    <Tabs value={tab} onValueChange={setTab} className="border-t border-line px-3 pt-3 pb-3">
      <TabsList>
        <TabsTrigger value="tools">Tools ({tools.length})</TabsTrigger>
        <TabsTrigger value="resources">Resources ({resources.length})</TabsTrigger>
        <TabsTrigger value="prompts">Prompts ({prompts.length})</TabsTrigger>
        <TabsTrigger value="log">Log</TabsTrigger>
      </TabsList>
      <TabsContent value="tools">
        {!running && tools.length ? <p className="mb-2 text-xs text-fg-subtle">The server is not running: these are the tools it offered last time.</p> : null}
        {tools.length === 0 ? (
          <p className="py-3 text-[13px] text-fg-muted">{running ? "This server offers no tools." : "Start the server to see its tools."}</p>
        ) : (
          <ul className="divide-y divide-line rounded-md border border-line" aria-label="Tools from this server">
            {tools.map((t) => (
              <ToolRow key={t.name} tool={t} running={running} />
            ))}
          </ul>
        )}
        {d.skipped?.length ? (
          <div className="mt-3 text-xs text-fg-muted">
            <p className="font-medium text-fg">Not offered to agents</p>
            <ul className="mt-1 list-disc pl-5">
              {d.skipped.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {d.instructions ? (
          <details className="mt-3 text-xs text-fg-muted">
            <summary className="cursor-pointer">The server's own notes</summary>
            <p className="mt-1 whitespace-pre-wrap">{d.instructions}</p>
          </details>
        ) : null}
      </TabsContent>
      <TabsContent value="resources">
        {resources.length === 0 ? (
          <p className="py-3 text-[13px] text-fg-muted">No resources.</p>
        ) : (
          <ul className="divide-y divide-line rounded-md border border-line" aria-label="Resources from this server">
            {resources.map((r) => (
              <li key={r.uri} className="px-3 py-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[13px] font-medium">{r.name}</span>
                  {r.mime_type ? <Badge>{r.mime_type}</Badge> : null}
                  <Button
                    size="sm"
                    variant="ghost"
                    className="ml-auto"
                    loading={read.isPending && read.variables === r.uri}
                    onClick={() =>
                      read.mutate(r.uri, { onSuccess: (content) => setOpened({ uri: r.uri, content }), onError: (e) => toast.error(errorMessage(e)) })
                    }
                  >
                    Open
                  </Button>
                </div>
                <p className="font-mono text-xs break-all text-fg-subtle">{r.uri}</p>
                {r.description ? <p className="text-xs text-fg-muted">{r.description}</p> : null}
                {opened?.uri === r.uri ? <ResourcePreview content={opened.content} /> : null}
              </li>
            ))}
          </ul>
        )}
      </TabsContent>
      <TabsContent value="prompts">
        {prompts.length === 0 ? (
          <p className="py-3 text-[13px] text-fg-muted">No prompts.</p>
        ) : (
          <ul className="divide-y divide-line rounded-md border border-line" aria-label="Prompts from this server">
            {prompts.map((p) => (
              <li key={p.name} className="px-3 py-2.5">
                <p className="text-[13px] font-medium">{p.name}</p>
                {p.description ? <p className="text-xs text-fg-muted">{p.description}</p> : null}
                {p.arguments?.length ? (
                  <p className="mt-0.5 text-xs text-fg-subtle">
                    Takes: {p.arguments.map((a) => `${a.name}${a.required ? " (required)" : ""}`).join(", ")}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </TabsContent>
      <TabsContent value="log">
        <div className="mb-2 flex items-center gap-2">
          <p className="text-xs text-fg-subtle">What the server wrote about itself (secrets are masked).</p>
          <Button size="sm" variant="ghost" className="ml-auto" onClick={() => void log.refetch()} loading={log.isFetching}>
            <RefreshCw /> Refresh
          </Button>
        </div>
        {log.data?.lines.length ? (
          <pre className="max-h-72 overflow-auto rounded-md bg-sunken p-2 font-mono text-xs whitespace-pre-wrap break-words">{log.data.lines.join("\n")}</pre>
        ) : (
          <EmptyState title="Nothing logged yet" description="Messages appear here while the server runs." />
        )}
      </TabsContent>
    </Tabs>
  );
}
