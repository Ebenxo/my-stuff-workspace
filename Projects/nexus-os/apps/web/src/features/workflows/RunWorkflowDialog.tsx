import type { Workflow } from "@nexus/schemas";
import { Button, Dialog, DialogContent, DialogFooter, FieldError, Input, Label, Switch, toast } from "@nexus/ui";
import { useState } from "react";
import { useNavigate } from "react-router";
import { errorMessage } from "../../lib/queries";
import { useRunWorkflow } from "../../lib/workflowQueries";
import { inputDefaults, inputValues } from "./model";

export function RunWorkflowDialog({ workflow, open, onOpenChange }: { workflow: Workflow; open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={`Run ${workflow.name}`} description="Steps that need your approval will wait for you.">
        <RunForm key={workflow.version} workflow={workflow} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function RunForm({ workflow, onDone }: { workflow: Workflow; onDone: () => void }) {
  const inputs = workflow.definition.inputs ?? [];
  const [form, setForm] = useState(() => inputDefaults(inputs));
  const run = useRunWorkflow(workflow.id);
  const navigate = useNavigate();
  const missing = inputs.filter((i) => (i.required ?? true) && i.type !== "boolean" && String(form[i.name] ?? "").trim() === "");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (missing.length) return;
    run.mutate(inputValues(inputs, form), {
      onSuccess: (r) => {
        toast.success("Started");
        onDone();
        void navigate(`/workflow-runs/${r.id}`);
      },
    });
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {inputs.length === 0 ? <p className="text-[13px] text-fg-muted">This workflow takes no inputs.</p> : null}
      {inputs.map((i) =>
        i.type === "boolean" ? (
          <label key={i.name} className="flex items-center gap-2 text-[13px]">
            <Switch checked={form[i.name] === true} onCheckedChange={(v) => setForm({ ...form, [i.name]: v })} aria-label={i.name} />
            {i.name}
            {i.description ? <span className="text-xs text-fg-subtle">{i.description}</span> : null}
          </label>
        ) : (
          <div key={i.name}>
            <Label htmlFor={`run-${i.name}`}>
              {i.name}
              {(i.required ?? true) ? "" : " (optional)"}
            </Label>
            <Input
              id={`run-${i.name}`}
              type={i.type === "number" ? "number" : "text"}
              value={String(form[i.name] ?? "")}
              onChange={(e) => setForm({ ...form, [i.name]: e.target.value })}
            />
            {i.description ? <p className="mt-1 text-xs text-fg-subtle">{i.description}</p> : null}
          </div>
        ),
      )}
      <FieldError>{run.isError ? errorMessage(run.error) : undefined}</FieldError>
      <DialogFooter>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" loading={run.isPending} disabled={missing.length > 0}>
          Run
        </Button>
      </DialogFooter>
    </form>
  );
}
