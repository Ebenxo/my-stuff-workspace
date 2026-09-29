import type { MemoryItem, Objective } from "@nexus/schemas";
import { Button, Card, CardContent, toast } from "@nexus/ui";
import { Brain, Check, Pencil, X } from "lucide-react";
import { useState } from "react";
import { useMemories, useMemoryAction } from "../../lib/memoryQueries";
import { errorMessage } from "../../lib/queries";
import { MemoryDialog } from "./MemoryDialog";

/** After an objective, NEXUS suggests remembering its outcome. Nothing is kept until the person says so. */
export function MemorySuggestion({ objective }: { objective: Objective }) {
  const pending = useMemories({ projectId: objective.project_id, status: "pending", source: "objective" });
  const act = useMemoryAction();
  const [editing, setEditing] = useState<MemoryItem | undefined>();
  const item = pending.data?.find((m) => m.source.objective_id === objective.id);
  if (!item) return null;
  const run = (action: "confirm" | "dismiss") =>
    act.mutate(
      { id: item.id, action },
      {
        onSuccess: () => toast.success(action === "confirm" ? "Remembered for future work in this project" : "Not remembered"),
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  return (
    <Card className="mb-8 border-accent/40">
      <CardContent className="pt-4 text-[13px]">
        <p className="flex items-center gap-2 font-medium text-fg">
          <Brain className="size-4 text-accent-text" aria-hidden="true" />
          Remember this for next time?
        </p>
        <p className="mt-1 text-fg-muted">Agents in this project would be given it when it is relevant. You can edit or delete it later in Memory.</p>
        <blockquote className="mt-2 rounded-md border-l-2 border-line-strong bg-raised px-3 py-2 text-fg">{item.content}</blockquote>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" variant="primary" disabled={act.isPending} onClick={() => run("confirm")}>
            <Check /> Remember
          </Button>
          <Button size="sm" disabled={act.isPending} onClick={() => setEditing(item)}>
            <Pencil /> Edit first
          </Button>
          <Button size="sm" variant="ghost" disabled={act.isPending} onClick={() => run("dismiss")}>
            <X /> No thanks
          </Button>
        </div>
      </CardContent>
      <MemoryDialog open={!!editing} onOpenChange={(o) => !o && setEditing(undefined)} item={editing} />
    </Card>
  );
}
