import type { MemoryItem } from "@nexus/schemas";
import { Badge, Button, Card, EmptyState, ErrorState, Input, Select, Skeleton, cn, toast } from "@nexus/ui";
import { Archive, Brain, Plus, Search } from "lucide-react";
import { useEffect, useState } from "react";
import {
  useCompressMemory,
  useMemories,
  useMemorySearch,
  useMemoryStats,
  type MemoryFilter,
  type MemoryStatusFilter,
} from "../../lib/memoryQueries";
import { errorMessage } from "../../lib/queries";
import { MemoryCard } from "./MemoryCard";
import { MemoryDialog } from "./MemoryDialog";

const TABS: { value: MemoryStatusFilter; label: string }[] = [
  { value: "active", label: "Remembered" },
  { value: "pending", label: "Suggestions" },
  { value: "deleted", label: "Deleted" },
];

const EMPTY: Record<MemoryStatusFilter, { title: string; description: string }> = {
  active: {
    title: "Nothing remembered yet",
    description: "Add facts, decisions and preferences you want agents to know. Agents can propose memories too, and you can see and change all of them here.",
  },
  pending: { title: "No suggestions", description: "When an objective finishes, or an agent proposes a memory for all projects, it waits here for you." },
  deleted: { title: "Nothing deleted", description: "Deleted memories stay here until you erase them, so you can change your mind." },
};

export function MemoryBrowser({ projectId, focusId }: { projectId?: string | undefined; focusId?: string | null }) {
  const [status, setStatus] = useState<MemoryStatusFilter>("active");
  const [scope, setScope] = useState<MemoryFilter["scope"]>(undefined);
  const [source, setSource] = useState<MemoryFilter["source"]>(undefined);
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"browse" | "recall">("browse");
  const [editing, setEditing] = useState<MemoryItem | undefined>();
  const [adding, setAdding] = useState(false);
  const stats = useMemoryStats(projectId);
  const list = useMemories({ projectId, status, scope, source, q: mode === "browse" ? text : undefined });
  const recall = useMemorySearch(mode === "recall" ? text : "", projectId);
  const compress = useCompressMemory();

  useEffect(() => {
    if (focusId && list.data?.some((i) => i.id === focusId)) {
      document.getElementById(`memory-${focusId}`)?.scrollIntoView({ block: "center" });
    }
  }, [focusId, list.data]);

  const counts: Partial<Record<MemoryStatusFilter, number>> = stats.data ?? {};

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-md border border-line p-0.5" role="tablist" aria-label="Memory status">
          {TABS.map((t) => (
            <button
              key={t.value}
              type="button"
              role="tab"
              aria-selected={status === t.value && mode === "browse"}
              onClick={() => {
                setStatus(t.value);
                setMode("browse");
              }}
              className={cn(
                "flex items-center gap-1.5 rounded px-2.5 py-1 text-xs text-fg-muted",
                status === t.value && mode === "browse" && "bg-raised text-fg",
              )}
            >
              {t.label}
              {t.value === "pending" && counts.pending ? <Badge tone="warning">{counts.pending}</Badge> : null}
            </button>
          ))}
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          {projectId ? (
            <Button
              size="sm"
              variant="ghost"
              loading={compress.isPending}
              onClick={() =>
                compress.mutate(projectId, {
                  onSuccess: (r) =>
                    toast.success(
                      r.compressed
                        ? `Folded ${r.compressed} older notes into ${r.groups} ${r.groups === 1 ? "summary" : "summaries"}. You can restore them.`
                        : "Nothing to tidy: no old, rarely used notes that belong together.",
                    ),
                  onError: (e) => toast.error(errorMessage(e)),
                })
              }
            >
              <Archive /> Tidy old notes
            </Button>
          ) : null}
          <Button size="sm" variant="primary" onClick={() => setAdding(true)}>
            <Plus /> Add a memory
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-0 flex-1 basis-60">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-fg-subtle" aria-hidden="true" />
          <label htmlFor="memory-filter" className="sr-only">
            {mode === "recall" ? "What would agents recall for…" : "Filter memories"}
          </label>
          <Input
            id="memory-filter"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={mode === "recall" ? "Describe a task to see what agents would recall…" : "Filter by text…"}
            className="pl-8"
          />
        </div>
        <label className="flex items-center gap-2 text-xs text-fg-muted">
          <input type="checkbox" checked={mode === "recall"} onChange={(e) => setMode(e.target.checked ? "recall" : "browse")} />
          Rank as agents would
        </label>
        {mode === "browse" ? (
          <>
            <label htmlFor="memory-scope-filter" className="sr-only">
              Scope
            </label>
            <Select
              id="memory-scope-filter"
              value={scope ?? ""}
              onChange={(e) => setScope((e.target.value || undefined) as MemoryFilter["scope"])}
              className="h-8 w-36 text-[13px]"
            >
              <option value="">{projectId ? "This project + all" : "Every scope"}</option>
              <option value="project">Project only</option>
              <option value="global">All-project only</option>
            </Select>
            <label htmlFor="memory-source-filter" className="sr-only">
              Source
            </label>
            <Select
              id="memory-source-filter"
              value={source ?? ""}
              onChange={(e) => setSource((e.target.value || undefined) as MemoryFilter["source"])}
              className="h-8 w-36 text-[13px]"
            >
              <option value="">Any source</option>
              <option value="user">Written by you</option>
              <option value="agent">From agents</option>
              <option value="objective">From objectives</option>
              <option value="summary">Summaries</option>
            </Select>
          </>
        ) : null}
      </div>

      <Card>
        {mode === "recall" ? (
          text.trim().length < 2 ? (
            <EmptyState icon={<Brain />} title="See what agents would recall" description="Type a task. Memories are ranked by meaning, words, recency, importance and relation to the work, the same way agents get them." />
          ) : recall.isPending ? (
            <Skeleton className="m-3 h-20" />
          ) : recall.isError ? (
            <ErrorState message={errorMessage(recall.error)} onRetry={() => void recall.refetch()} />
          ) : recall.data.length === 0 ? (
            <EmptyState title="Nothing would be recalled" description="No remembered item is about this." />
          ) : (
            <ol className="divide-y divide-line" aria-label="Recalled memories">
              {recall.data.map((h) => (
                <MemoryCard key={h.item.id} item={h.item} score={h.score} onEdit={setEditing} />
              ))}
            </ol>
          )
        ) : list.isPending ? (
          <Skeleton className="m-3 h-24" />
        ) : list.isError ? (
          <ErrorState message={errorMessage(list.error)} onRetry={() => void list.refetch()} />
        ) : list.data.length === 0 ? (
          <EmptyState icon={<Brain />} title={text ? "No matches" : EMPTY[status].title} description={text ? "Try other words, or rank as agents would." : EMPTY[status].description} />
        ) : (
          <ul className="divide-y divide-line" aria-label="Memories">
            {list.data.map((m) => (
              <MemoryCard key={m.id} item={m} highlighted={m.id === focusId} onEdit={setEditing} />
            ))}
          </ul>
        )}
      </Card>

      <MemoryDialog open={adding} onOpenChange={setAdding} projectId={projectId} />
      <MemoryDialog open={!!editing} onOpenChange={(o) => !o && setEditing(undefined)} item={editing} />
    </div>
  );
}
