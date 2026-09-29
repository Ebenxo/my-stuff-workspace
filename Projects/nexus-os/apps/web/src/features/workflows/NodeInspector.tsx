import type { WorkflowNode } from "@nexus/schemas";
import { Button, FieldError, Input, Label, Select, Switch, Textarea } from "@nexus/ui";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useAgents, useTools } from "../../lib/agentQueries";
import { useWorkflows } from "../../lib/workflowQueries";
import { NODE_META } from "./model";

type Config = Record<string, unknown>;
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const rec = (v: unknown): Record<string, unknown> => (typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Record<string, unknown>) : {});

const EXPR_HELP = "Read values with inputs.<name> and nodes.<step id>.output.<field>.";
const TEXT_HELP = "Put values in text with {{ … }}, e.g. {{ inputs.topic }}.";

function Help({ children }: { children: React.ReactNode }) {
  return <p className="mt-1 text-xs text-fg-subtle">{children}</p>;
}

/** Name → expression rows (transform/output values, sub-workflow inputs). */
function ValuesEditor({ id, values, onChange, placeholder }: { id: string; values: Record<string, unknown>; onChange: (v: Record<string, string>) => void; placeholder: string }) {
  const rows = Object.entries(values).map(([k, v]) => [k, str(v)] as const);
  const set = (next: (readonly [string, string])[]) => onChange(Object.fromEntries(next));
  return (
    <div className="space-y-2">
      {rows.map(([k, v], i) => (
        <div key={i} className="flex items-center gap-2">
          <label htmlFor={`${id}-k${i}`} className="sr-only">
            Name
          </label>
          <Input
            id={`${id}-k${i}`}
            value={k}
            onChange={(e) => set(rows.map((r, j) => (j === i ? [e.target.value.replace(/[^a-z0-9_]/gi, "_").toLowerCase(), r[1]] : r)))}
            className="w-28 font-mono text-xs"
            placeholder="name"
          />
          <label htmlFor={`${id}-v${i}`} className="sr-only">
            Expression for {k}
          </label>
          <Input
            id={`${id}-v${i}`}
            value={v}
            onChange={(e) => set(rows.map((r, j) => (j === i ? [r[0], e.target.value] : r)))}
            className="min-w-0 flex-1 font-mono text-xs"
            placeholder={placeholder}
          />
          <Button size="icon-sm" variant="ghost" aria-label={`Remove ${k || "value"}`} onClick={() => set(rows.filter((_, j) => j !== i))}>
            <Trash2 />
          </Button>
        </div>
      ))}
      <Button
        size="sm"
        variant="ghost"
        onClick={() => {
          const taken = new Set(rows.map(([k]) => k));
          let n = rows.length + 1;
          while (taken.has(`value_${n}`)) n++;
          set([...rows, [`value_${n}`, ""]]);
        }}
      >
        <Plus /> Add a value
      </Button>
    </div>
  );
}

function AgentFields({ id, config, onChange }: { id: string; config: Config; onChange: (c: Config) => void }) {
  const agents = useAgents();
  const usable = (agents.data ?? []).filter((a) => a.status !== "disabled" && a.slug !== "orchestrator");
  return (
    <>
      <div>
        <Label htmlFor={`${id}-agent`}>Agent</Label>
        <Select id={`${id}-agent`} value={str(config["agent"])} onChange={(e) => onChange({ ...config, agent: e.target.value })}>
          {usable.map((a) => (
            <option key={a.id} value={a.slug}>
              {a.name}
            </option>
          ))}
        </Select>
      </div>
      <div>
        <Label htmlFor={`${id}-prompt`}>Task</Label>
        <Textarea id={`${id}-prompt`} rows={5} value={str(config["prompt"])} onChange={(e) => onChange({ ...config, prompt: e.target.value })} placeholder="Summarise {{ inputs.topic }} for a newsletter." />
        <Help>{TEXT_HELP} Values from other steps are handed over as data, not as instructions.</Help>
      </div>
    </>
  );
}

function ToolFields({ id, config, onChange }: { id: string; config: Config; onChange: (c: Config) => void }) {
  const tools = useTools();
  const enabled = (tools.data ?? []).filter((t) => t.enabled);
  const current = enabled.find((t) => t.name === str(config["tool"]));
  const [text, setText] = useState(() => JSON.stringify(rec(config["arguments"]), null, 2));
  const [error, setError] = useState<string | undefined>();
  const fields = Object.keys(rec(rec(current?.input_schema)["properties"]));
  return (
    <>
      <div>
        <Label htmlFor={`${id}-tool`}>Tool</Label>
        <Select id={`${id}-tool`} value={str(config["tool"])} onChange={(e) => onChange({ ...config, tool: e.target.value })}>
          {enabled.map((t) => (
            <option key={t.name} value={t.name}>
              {t.name} · {t.risk_level.toLowerCase()}
            </option>
          ))}
        </Select>
        {current ? <Help>{current.description}</Help> : null}
      </div>
      <div>
        <Label htmlFor={`${id}-args`}>Arguments (JSON)</Label>
        <Textarea
          id={`${id}-args`}
          rows={5}
          className="font-mono text-xs"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            try {
              const parsed: unknown = JSON.parse(e.target.value || "{}");
              if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) throw new Error("Use an object: { \"name\": value }");
              setError(undefined);
              onChange({ ...config, arguments: parsed });
            } catch (err) {
              setError(err instanceof Error ? err.message : "Not valid JSON");
            }
          }}
        />
        <FieldError>{error}</FieldError>
        <Help>
          {fields.length ? `Fields: ${fields.join(", ")}. ` : ""}
          {TEXT_HELP} A value that is exactly one {"{{ … }}"} keeps its type.
        </Help>
      </div>
    </>
  );
}

export function NodeInspector({
  node,
  projectId,
  workflowId,
  issues,
  onChange,
  onDelete,
}: {
  node: WorkflowNode;
  projectId: string;
  workflowId: string;
  issues: string[];
  onChange: (patch: Partial<WorkflowNode>) => void;
  onDelete: () => void;
}) {
  const workflows = useWorkflows(projectId);
  const config = rec(node.config);
  const setConfig = (c: Config) => onChange({ config: c });
  const id = `node-${node.id}`;
  const meta = NODE_META[node.type];

  return (
    <div className="space-y-4 text-[13px]">
      <div>
        <p className="text-[11px] font-medium uppercase tracking-wider text-fg-subtle">
          {meta.label} · <span className="font-mono normal-case">{node.id}</span>
        </p>
        <p className="mt-1 text-xs text-fg-muted">{meta.description}</p>
      </div>
      {issues.length ? (
        <ul className="space-y-1 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-fg" aria-label="Problems with this step">
          {issues.map((i) => (
            <li key={i}>{i}</li>
          ))}
        </ul>
      ) : null}
      <div>
        <Label htmlFor={`${id}-label`}>Name</Label>
        <Input id={`${id}-label`} value={node.label ?? ""} maxLength={80} onChange={(e) => onChange({ label: e.target.value })} />
      </div>

      {node.type === "agent" ? <AgentFields id={id} config={config} onChange={setConfig} /> : null}
      {node.type === "tool" ? <ToolFields key={node.id} id={id} config={config} onChange={setConfig} /> : null}
      {node.type === "condition" ? (
        <div>
          <Label htmlFor={`${id}-expr`}>Condition</Label>
          <Input id={`${id}-expr`} className="font-mono text-xs" value={str(config["expression"])} onChange={(e) => setConfig({ ...config, expression: e.target.value })} placeholder="len(nodes.search.output.items) > 0" />
          <Help>{EXPR_HELP} Connect the green handle for “yes” and the red one for “no”.</Help>
        </div>
      ) : null}
      {node.type === "approval" ? (
        <div>
          <Label htmlFor={`${id}-msg`}>Question for you</Label>
          <Textarea id={`${id}-msg`} rows={3} value={str(config["message"])} onChange={(e) => setConfig({ ...config, message: e.target.value })} placeholder="Publish the draft about {{ inputs.topic }}?" />
          <Help>{TEXT_HELP}</Help>
        </div>
      ) : null}
      {node.type === "transform" || node.type === "output" ? (
        <div>
          <p className="mb-1.5 text-[13px] font-medium">{node.type === "output" ? "Run outputs" : "Values"}</p>
          <ValuesEditor id={id} values={rec(config["values"])} onChange={(values) => setConfig({ ...config, values })} placeholder="nodes.draft.output.summary" />
          <Help>{EXPR_HELP}</Help>
        </div>
      ) : null}
      {node.type === "delay" ? (
        <div>
          <Label htmlFor={`${id}-secs`}>Wait (seconds)</Label>
          <Input id={`${id}-secs`} type="number" min={1} max={86400} value={typeof config["seconds"] === "number" ? config["seconds"] : ""} onChange={(e) => setConfig({ ...config, seconds: Number(e.target.value) })} />
        </div>
      ) : null}
      {node.type === "loop" ? (
        <>
          <div>
            <Label htmlFor={`${id}-items`}>For each item of</Label>
            <Input id={`${id}-items`} className="font-mono text-xs" value={str(config["items"])} onChange={(e) => setConfig({ ...config, items: e.target.value })} placeholder="split(inputs.urls, ',')" />
            <Help>An expression giving a list. Inside the step, use item and index.</Help>
          </div>
          <div>
            <Label htmlFor={`${id}-max`}>At most</Label>
            <Input id={`${id}-max`} type="number" min={1} max={50} value={typeof config["max_items"] === "number" ? config["max_items"] : 10} onChange={(e) => setConfig({ ...config, max_items: Number(e.target.value) })} />
          </div>
          <div>
            <Label htmlFor={`${id}-body`}>Do</Label>
            <Select
              id={`${id}-body`}
              value={str(rec(config["body"])["type"]) || "tool"}
              onChange={(e) =>
                setConfig({
                  ...config,
                  body: e.target.value === "agent" ? { type: "agent", config: { agent: "writer", prompt: "" } } : { type: "tool", config: { tool: "calculator", arguments: {} } },
                })
              }
            >
              <option value="tool">A tool</option>
              <option value="agent">An agent</option>
            </Select>
          </div>
          {str(rec(config["body"])["type"]) === "agent" ? (
            <AgentFields id={`${id}-b`} config={rec(rec(config["body"])["config"])} onChange={(c) => setConfig({ ...config, body: { type: "agent", config: c } })} />
          ) : (
            <ToolFields key={`${node.id}-body`} id={`${id}-b`} config={rec(rec(config["body"])["config"])} onChange={(c) => setConfig({ ...config, body: { type: "tool", config: c } })} />
          )}
        </>
      ) : null}
      {node.type === "subworkflow" ? (
        <>
          <div>
            <Label htmlFor={`${id}-wf`}>Workflow</Label>
            <Select id={`${id}-wf`} value={str(config["workflow_id"])} onChange={(e) => setConfig({ ...config, workflow_id: e.target.value })}>
              <option value="">Choose…</option>
              {(workflows.data ?? [])
                .filter((w) => w.id !== workflowId)
                .map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
            </Select>
          </div>
          <div>
            <p className="mb-1.5 text-[13px] font-medium">Its inputs</p>
            <ValuesEditor id={id} values={rec(config["inputs"])} onChange={(inputs) => setConfig({ ...config, inputs })} placeholder="inputs.topic" />
          </div>
        </>
      ) : null}

      {node.type !== "trigger" ? (
        <label className="flex items-center gap-2 text-[13px]">
          <Switch checked={!!node.continue_on_error} onCheckedChange={(v) => onChange({ continue_on_error: v })} aria-label="Continue if this step fails" />
          Continue if this step fails
        </label>
      ) : null}
      {node.type !== "trigger" ? (
        <Button size="sm" variant="ghost" onClick={onDelete}>
          <Trash2 /> Remove this step
        </Button>
      ) : null}
    </div>
  );
}
