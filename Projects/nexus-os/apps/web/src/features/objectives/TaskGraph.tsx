import "@xyflow/react/dist/base.css";
import type { TaskNode } from "@nexus/schemas";
import { cn } from "@nexus/ui";
import { Background, Controls, Handle, Position, ReactFlow, useReactFlow, useStore, type Edge, type Node, type NodeProps } from "@xyflow/react";
import { useEffect, useMemo } from "react";
import { KIND_LABEL, TASK_STATUS, layoutTasks } from "./format";

type TaskData = { task: TaskNode; selected: boolean };

const RING: Record<string, string> = {
  WAITING: "border-line-strong",
  QUEUED: "border-line-strong",
  RUNNING: "border-accent shadow-[0_0_0_3px_color-mix(in_oklab,var(--nx-accent)_25%,transparent)]",
  NEEDS_APPROVAL: "border-warning",
  BLOCKED: "border-warning",
  COMPLETED: "border-success/60",
  SKIPPED: "border-line-strong opacity-70",
  FAILED: "border-danger",
  CANCELLED: "border-line-strong opacity-60",
};

const DOT: Record<string, string> = {
  neutral: "bg-fg-subtle",
  accent: "bg-accent-text animate-pulse",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-info",
};

function TaskCard({ data }: NodeProps<Node<TaskData>>) {
  const { task, selected } = data;
  const status = TASK_STATUS[task.status];
  return (
    <div
      className={cn(
        "w-56 rounded-lg border bg-surface px-3 py-2 text-left transition-shadow",
        RING[task.status],
        selected && "outline outline-2 outline-offset-2 outline-ring",
      )}
    >
      <Handle type="target" position={Position.Left} className="!size-1.5 !border-0 !bg-line-strong" />
      <p className="flex items-center gap-1.5 text-[11px] text-fg-subtle">
        <span className={cn("size-1.5 rounded-full", DOT[status.tone])} aria-hidden="true" />
        <span className="font-mono">{task.key}</span>
        <span aria-hidden="true">·</span>
        <span>{KIND_LABEL[task.kind] ?? task.kind}</span>
        <span className="ml-auto">{status.label}</span>
      </p>
      <p className="mt-1 line-clamp-2 text-[13px] font-medium text-fg">{task.title}</p>
      <p className="mt-0.5 text-[11px] text-fg-muted">{task.assigned_agent.replaceAll("_", " ")}</p>
      <Handle type="source" position={Position.Right} className="!size-1.5 !border-0 !bg-line-strong" />
    </div>
  );
}

const nodeTypes = { task: TaskCard };
const FIT = { padding: 0.2, maxZoom: 1 };

/**
 * Reviews, revisions and the verification step join the graph mid-run, and the graph narrows when a
 * task's details open beside it: re-fit on either so every task stays in view.
 */
function KeepInView({ count }: { count: number }) {
  const { fitView } = useReactFlow();
  const width = useStore((s) => s.width);
  const height = useStore((s) => s.height);
  useEffect(() => {
    const frame = requestAnimationFrame(() => void fitView(FIT));
    return () => cancelAnimationFrame(frame);
  }, [count, width, height, fitView]);
  return null;
}

export function TaskGraph({ tasks, selectedId, onSelect }: { tasks: TaskNode[]; selectedId?: string | undefined; onSelect: (id: string) => void }) {
  const { nodes, edges } = useMemo(() => {
    const laid = layoutTasks(tasks);
    const ids = new Set(tasks.map((t) => t.id));
    const nodes: Node<TaskData>[] = laid.map(({ task, x, y }) => ({
      id: task.id,
      type: "task",
      position: { x, y },
      data: { task, selected: task.id === selectedId },
      draggable: false,
      connectable: false,
      ariaLabel: `${task.key}: ${task.title}, ${TASK_STATUS[task.status].label}`,
    }));
    const edges: Edge[] = tasks.flatMap((t) =>
      (t.depends_on ?? [])
        .filter((d) => ids.has(d))
        .map((d) => ({
          id: `${d}->${t.id}`,
          source: d,
          target: t.id,
          animated: t.status === "RUNNING",
          style: { stroke: "var(--nx-line-strong)", strokeWidth: 1.5 },
        })),
    );
    return { nodes, edges };
  }, [tasks, selectedId]);

  return (
    <div className="h-[420px] w-full overflow-hidden rounded-lg border border-line bg-canvas" aria-label="Task graph" role="figure">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={(_, n) => onSelect(n.id)}
        fitView
        fitViewOptions={FIT}
        minZoom={0.3}
        nodesConnectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <KeepInView count={nodes.length} />
        <Background color="var(--nx-line)" gap={20} />
        <Controls showInteractive={false} className="[&_button]:!border-line [&_button]:!bg-surface [&_button]:!text-fg" />
      </ReactFlow>
    </div>
  );
}

/** The same graph as an accessible, keyboard-friendly list (also used on small screens). */
export function TaskList({ tasks, selectedId, onSelect }: { tasks: TaskNode[]; selectedId?: string | undefined; onSelect: (id: string) => void }) {
  const laid = useMemo(() => layoutTasks(tasks), [tasks]);
  const byId = new Map(tasks.map((t) => [t.id, t]));
  return (
    <ol className="divide-y divide-line rounded-lg border border-line" aria-label="Tasks">
      {laid.map(({ task }) => {
        const status = TASK_STATUS[task.status];
        const deps = (task.depends_on ?? []).map((d) => byId.get(d)?.key).filter(Boolean);
        return (
          <li key={task.id}>
            <button
              type="button"
              onClick={() => onSelect(task.id)}
              aria-current={task.id === selectedId ? "true" : undefined}
              className="flex w-full items-center gap-3 px-3 py-2 text-left text-[13px] hover:bg-raised/60 aria-[current=true]:bg-raised"
            >
              <span className={cn("size-2 shrink-0 rounded-full", DOT[status.tone])} aria-hidden="true" />
              <span className="font-mono text-xs text-fg-subtle">{task.key}</span>
              <span className="min-w-0 flex-1 truncate">{task.title}</span>
              {deps.length ? <span className="hidden text-xs text-fg-subtle sm:inline">after {deps.join(", ")}</span> : null}
              <span className="text-xs text-fg-muted">{status.label}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
