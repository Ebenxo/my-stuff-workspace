import { Button, Card, EmptyState, ErrorState, Skeleton } from "@nexus/ui";
import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { AgentCard } from "../features/agents/AgentCard";
import { AgentDialog } from "../features/agents/AgentDialog";
import { normalizeAgent, type AgentView } from "../features/agents/format";
import { RunAgentDialog } from "../features/agents/RunAgentDialog";
import { RunList } from "../features/agents/RunList";
import { useAgents } from "../lib/agentQueries";
import { errorMessage } from "../lib/queries";
import { Page, PageHeader, Section } from "./Page";

export function AgentsRoute() {
  const agents = useAgents();
  const views = useMemo(() => (agents.data ?? []).map(normalizeAgent), [agents.data]);
  const [running, setRunning] = useState<string | undefined>();
  const [runOpen, setRunOpen] = useState(false);
  const [editing, setEditing] = useState<AgentView | undefined>();
  const [editOpen, setEditOpen] = useState(false);

  return (
    <Page>
      <PageHeader
        title="Agents"
        description="Specialists that work step by step inside a project. Each has its own tools, limits and instructions, and every action goes through your permissions."
        actions={
          <>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                setRunning(undefined);
                setRunOpen(true);
              }}
            >
              Run an agent
            </Button>
            <Button
              size="sm"
              onClick={() => {
                setEditing(undefined);
                setEditOpen(true);
              }}
            >
              <Plus /> New agent
            </Button>
          </>
        }
      />

      <Section title="Team">
        {agents.isPending ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <Skeleton className="h-44" />
            <Skeleton className="h-44" />
          </div>
        ) : agents.isError ? (
          <ErrorState message={errorMessage(agents.error)} onRetry={() => void agents.refetch()} />
        ) : views.length === 0 ? (
          <EmptyState title="No agents" description="Built-in agents are created when NEXUS starts. Restart the app if they are missing." />
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {views.map((a) => (
              <li key={a.id}>
                <AgentCard
                  agent={a}
                  onRun={() => {
                    setRunning(a.slug);
                    setRunOpen(true);
                  }}
                  onEdit={() => {
                    setEditing(a);
                    setEditOpen(true);
                  }}
                />
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Recent runs">
        <Card>
          <RunList filter={{ limit: 15 }} />
        </Card>
      </Section>

      <RunAgentDialog open={runOpen} onOpenChange={setRunOpen} agentId={running} />
      <AgentDialog open={editOpen} onOpenChange={setEditOpen} agent={editing} />
    </Page>
  );
}
