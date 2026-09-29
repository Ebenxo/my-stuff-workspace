import "@xyflow/react/dist/base.css";
import type { NodeState, WorkflowDefinition, WorkflowNode } from "@nexus/schemas";
import { cn, toast } from "@nexus/ui";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  useReactFlow,
  useStore,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
  type NodeProps,
} from "@xyflow/react";
import { AlertCircle } from "lucide-react";
import { useEffect, useMemo } from "react";
import { NODE_ICON } from "./icons";
import { NODE_META, NODE_STATUS, connect, removeEdge, removeNode, summarize } from "./model";


const STATUS_RING: Record<string, string> = {
  RUNNING: "border-accent shadow-[0_0_0_3px_color-mix(in_oklab,var(--nx-accent)_25%,transparent)]",
  WAITING: "border-warning",
  COMPLETED: "border-success/60",
  FAILED: "border-danger",
  SKIPPED: "opacity-60",
  CANCELLED: "opacity-60",
};
const DOT: Record<string, string> = {
  neutral: "bg-fg-subtle",
  accent: "bg-accent-text animate-pulse",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-info",
};

type StepData = { node: WorkflowNode; state?: NodeState | undefined; issues: string[]; selected: boolean };

function StepCard({ data }: NodeProps<Node<StepData>>) {
  const { node, state, issues, selected } = data;
  const Icon = NODE_ICON[node.type];
  const status = state?.status ? NODE_STATUS[state.status] : undefined;
  const branches = NODE_META[node.type].branches;
  return (
    <div
      className={cn(
        "w-56 rounded-lg border border-line-strong bg-surface px-3 py-2 text-left",
        state?.status ? STATUS_RING[state.status] : undefined,
        issues.length > 0 && "border-danger/70",
        selected && "outline outline-2 outline-offset-2 outline-ring",
      )}
    >
      {node.type !== "trigger" ? <Handle type="target" position={Position.Top} className="!size-3 !border-2 !border-surface !bg-line-strong" /> : null}
      <p className="flex items-center gap-1.5 text-[11px] text-fg-subtle">
        <Icon className="size-3.5" aria-hidden="true" />
        <span>{NODE_META[node.type].label}</span>
        <span className="font-mono">· {node.id}</span>
        {status ? (
          <span className="ml-auto flex items-center gap-1">
            <span className={cn("size-1.5 rounded-full", DOT[status.tone])} aria-hidden="true" />
            {status.label}
          </span>
        ) : issues.length ? (
          <AlertCircle className="ml-auto size-3.5 text-danger" aria-label={`${issues.length} problem${issues.length === 1 ? "" : "s"}`} />
        ) : null}
      </p>
      <p className="mt-0.5 truncate text-[13px] font-medium text-fg">{node.label || NODE_META[node.type].label}</p>
      <p className="line-clamp-2 text-[11px] text-fg-muted">{summarize(node)}</p>
      {branches ? (
        <>
          <Handle id="true" type="source" position={Position.Bottom} style={{ left: "30%" }} className="!size-3 !border-2 !border-surface !bg-success" />
          <Handle id="false" type="source" position={Position.Bottom} style={{ left: "70%" }} className="!size-3 !border-2 !border-surface !bg-danger" />
          <span className="pointer-events-none absolute -bottom-5 left-[30%] -translate-x-1/2 text-[10px] text-success">Yes</span>
          <span className="pointer-events-none absolute -bottom-5 left-[70%] -translate-x-1/2 text-[10px] text-danger">No</span>
        </>
      ) : (
        <Handle type="source" position={Position.Bottom} className="!size-3 !border-2 !border-surface !bg-line-strong" />
      )}
    </div>
  );
}

const nodeTypes = { step: StepCard };
const FIT = { padding: 0.2, maxZoom: 1 };

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

interface Props {
  definition: WorkflowDefinition;
  selectedId?: string | undefined;
  onSelect: (id: string | undefined) => void;
  /** Editing when given; read-only otherwise. */
  onChange?: ((def: WorkflowDefinition) => void) | undefined;
  states?: Record<string, NodeState> | undefined;
  issues?: Map<string, string[]> | undefined;
  className?: string;
}

export function WorkflowCanvas({ definition, selectedId, onSelect, onChange, states, issues, className }: Props) {
  const editable = !!onChange;
  const { nodes, edges } = useMemo(() => {
    const wfNodes = definition.nodes ?? [];
    const nodes: Node<StepData>[] = wfNodes.map((n) => ({
      id: n.id,
      type: "step",
      position: { x: n.position?.x ?? 0, y: n.position?.y ?? 0 },
      data: { node: n, state: states?.[n.id], issues: issues?.get(n.id) ?? [], selected: n.id === selectedId },
      deletable: editable && n.type !== "trigger",
      ariaLabel: `${NODE_META[n.type].label} ${n.label || n.id}${states?.[n.id]?.status ? `, ${NODE_STATUS[states[n.id]!.status!].label}` : ""}`,
    }));
    const edges: Edge[] = (definition.edges ?? []).map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.branch ?? null,
      label: e.branch === "true" ? "Yes" : e.branch === "false" ? "No" : undefined,
      animated: states?.[e.target]?.status === "RUNNING",
      deletable: editable,
      style: { stroke: e.branch === "false" ? "var(--nx-danger)" : "var(--nx-line-strong)", strokeWidth: 1.5 },
      labelStyle: { fill: "var(--nx-fg-muted)", fontSize: 11 },
      labelBgStyle: { fill: "var(--nx-canvas)" },
    }));
    return { nodes, edges };
  }, [definition, states, issues, selectedId, editable]);

  function onNodesChange(changes: NodeChange<Node<StepData>>[]) {
    if (!onChange) return;
    const moved = new Map<string, { x: number; y: number }>();
    for (const c of changes) if (c.type === "position" && c.position) moved.set(c.id, c.position);
    if (moved.size) {
      onChange({
        ...definition,
        nodes: (definition.nodes ?? []).map((n) => (moved.has(n.id) ? { ...n, position: moved.get(n.id)! } : n)),
      });
    }
  }

  function onConnect(c: Connection) {
    if (!onChange || !c.source || !c.target) return;
    const result = connect(definition, c.source, c.target, (c.sourceHandle as "true" | "false" | null) ?? null);
    if ("error" in result) toast.error(result.error);
    else onChange(result.def);
  }

  return (
    <div className={cn("h-[520px] w-full overflow-hidden rounded-lg border border-line bg-canvas", className)} role="figure" aria-label="Workflow graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onConnect={onConnect}
        onNodeClick={(_, n) => onSelect(n.id)}
        onPaneClick={() => onSelect(undefined)}
        onNodesDelete={(del) => {
          if (!onChange) return;
          let next = definition;
          for (const n of del) next = removeNode(next, n.id);
          onChange(next);
          onSelect(undefined);
        }}
        onEdgesDelete={(del) => {
          if (!onChange) return;
          let next = definition;
          for (const e of del) next = removeEdge(next, e.id);
          onChange(next);
        }}
        nodesDraggable={editable}
        nodesConnectable={editable}
        deleteKeyCode={editable ? ["Backspace", "Delete"] : null}
        fitView
        fitViewOptions={FIT}
        minZoom={0.3}
        proOptions={{ hideAttribution: true }}
      >
        <KeepInView count={nodes.length} />
        <Background color="var(--nx-line)" gap={20} />
        <Controls showInteractive={false} className="[&_button]:!border-line [&_button]:!bg-surface [&_button]:!text-fg" />
      </ReactFlow>
    </div>
  );
}
