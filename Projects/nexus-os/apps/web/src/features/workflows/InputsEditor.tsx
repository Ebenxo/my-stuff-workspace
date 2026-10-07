import type { WorkflowInput } from "@nexus/schemas";
import { Button, Input, Select, Switch } from "@nexus/ui";
import { Plus, Trash2 } from "lucide-react";

/** The values a person (or a schedule) gives each run. Referenced as inputs.<name>. */
export function InputsEditor({ inputs, onChange }: { inputs: WorkflowInput[]; onChange: (inputs: WorkflowInput[]) => void }) {
  const update = (i: number, patch: Partial<WorkflowInput>) => onChange(inputs.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  return (
    <div className="space-y-2 text-[13px]">
      {inputs.length === 0 ? <p className="text-xs text-fg-muted">No inputs: every run is the same. Add one to ask for a value each time.</p> : null}
      {inputs.map((input, i) => (
        <div key={i} className="flex flex-wrap items-center gap-2 rounded-md border border-line p-2">
          <label htmlFor={`in-${i}-name`} className="sr-only">
            Input name
          </label>
          <Input
            id={`in-${i}-name`}
            value={input.name}
            onChange={(e) => update(i, { name: e.target.value.replace(/[^a-z0-9_]/gi, "_").toLowerCase() })}
            className="w-32 font-mono text-xs"
          />
          <label htmlFor={`in-${i}-type`} className="sr-only">
            Type
          </label>
          <Select id={`in-${i}-type`} value={input.type ?? "text"} onChange={(e) => update(i, { type: e.target.value as WorkflowInput["type"] })} className="h-8 w-28 text-xs">
            <option value="text">Text</option>
            <option value="number">Number</option>
            <option value="boolean">Yes / no</option>
          </Select>
          <label className="flex items-center gap-1.5 text-xs text-fg-muted">
            <Switch checked={input.required ?? true} onCheckedChange={(v) => update(i, { required: v })} aria-label={`${input.name} is required`} />
            Required
          </label>
          <Button size="icon-sm" variant="ghost" className="ml-auto" aria-label={`Remove ${input.name}`} onClick={() => onChange(inputs.filter((_, j) => j !== i))}>
            <Trash2 />
          </Button>
          <label htmlFor={`in-${i}-desc`} className="sr-only">
            Description
          </label>
          <Input
            id={`in-${i}-desc`}
            value={input.description ?? ""}
            onChange={(e) => update(i, { description: e.target.value })}
            placeholder="What to enter (shown when running)"
            className="basis-full text-xs"
          />
        </div>
      ))}
      <Button
        size="sm"
        variant="ghost"
        onClick={() => {
          const taken = new Set(inputs.map((x) => x.name));
          let n = inputs.length + 1;
          while (taken.has(`input_${n}`)) n++;
          onChange([...inputs, { name: `input_${n}`, type: "text", required: true, description: "" }]);
        }}
      >
        <Plus /> Add an input
      </Button>
    </div>
  );
}
