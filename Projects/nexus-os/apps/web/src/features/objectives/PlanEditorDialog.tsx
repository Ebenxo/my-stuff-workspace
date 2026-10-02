import type { Objective } from "@nexus/schemas";
import { Button, Dialog, DialogContent, DialogFooter, FieldError, Input, Label, Select, Switch, Textarea, toast } from "@nexus/ui";
import { Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useAgents } from "../../lib/agentQueries";
import { errorMessage } from "../../lib/queries";
import { useEditPlan } from "../../lib/objectiveQueries";
import { planOf } from "./format";
import { RESERVED_AGENTS, blankTask, fromPlan, hasErrors, removeTask, toPlanEdit, validatePlan, type EditTask } from "./planEdit";

export function PlanEditorDialog({ objective, open, onOpenChange }: { objective: Objective; open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Edit the plan" description="Change, add or remove tasks before anything runs. The plan is checked again when you save.">
        <Editor key={objective.updated_at} objective={objective} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function Editor({ objective, onDone }: { objective: Objective; onDone: () => void }) {
  const agents = useAgents();
  const save = useEditPlan(objective.id);
  const plan = planOf(objective);
  const [tasks, setTasks] = useState<EditTask[]>(() => fromPlan(plan?.tasks ?? []));
  const [criteria, setCriteria] = useState((plan?.criteria ?? []).join("\n"));
  const [submitted, setSubmitted] = useState(false);
  const specialists = useMemo(
    () => (agents.data ?? []).filter((a) => !RESERVED_AGENTS.has(a.slug) && a.status !== "disabled"),
    [agents.data],
  );
  const errors = validatePlan(tasks, new Set(specialists.map((a) => a.slug)));
  const update = (key: string, patch: Partial<EditTask>) => setTasks((ts) => ts.map((t) => (t.key === key ? { ...t, ...patch } : t)));

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitted(true);
    if (hasErrors(errors)) return;
    const lines = criteria.split("\n").map((c) => c.trim()).filter(Boolean);
    save.mutate(toPlanEdit(tasks, lines), {
      onSuccess: () => {
        toast.success("Plan updated");
        onDone();
      },
    });
  }

  return (
    <form onSubmit={submit} className="max-h-[70vh] space-y-4 overflow-y-auto pr-1">
      <ol className="space-y-3">
        {tasks.map((t) => (
          <li key={t.key} className="rounded-lg border border-line p-3">
            <div className="grid gap-3 sm:grid-cols-[5rem_1fr_10rem]">
              <div>
                <Label htmlFor={`k-${t.key}`}>Key</Label>
                <Input id={`k-${t.key}`} value={t.key} readOnly className="font-mono" />
              </div>
              <div>
                <Label htmlFor={`t-${t.key}`}>Title</Label>
                <Input id={`t-${t.key}`} value={t.title} onChange={(e) => update(t.key, { title: e.target.value })} />
              </div>
              <div>
                <Label htmlFor={`a-${t.key}`}>Agent</Label>
                <Select id={`a-${t.key}`} value={t.agent} onChange={(e) => update(t.key, { agent: e.target.value })}>
                  {specialists.map((a) => (
                    <option key={a.id} value={a.slug}>
                      {a.name}
                    </option>
                  ))}
                </Select>
              </div>
            </div>
            <div className="mt-3">
              <Label htmlFor={`d-${t.key}`}>What to do</Label>
              <Textarea id={`d-${t.key}`} rows={2} value={t.description} onChange={(e) => update(t.key, { description: e.target.value })} />
            </div>
            {tasks.length > 1 ? (
              <fieldset className="mt-3">
                <legend className="text-[13px] font-medium text-fg-muted">Starts after</legend>
                <div className="mt-1 flex flex-wrap gap-3">
                  {tasks
                    .filter((o) => o.key !== t.key)
                    .map((o) => (
                      <label key={o.key} className="flex items-center gap-1.5 text-[13px]">
                        <input
                          type="checkbox"
                          checked={t.dependsOn.includes(o.key)}
                          onChange={(e) =>
                            update(t.key, { dependsOn: e.target.checked ? [...t.dependsOn, o.key] : t.dependsOn.filter((d) => d !== o.key) })
                          }
                        />
                        <span className="font-mono text-xs">{o.key}</span> {o.title || "untitled"}
                      </label>
                    ))}
                </div>
              </fieldset>
            ) : null}
            <div className="mt-3 flex flex-wrap items-center gap-4">
              <label className="flex items-center gap-2 text-[13px]">
                <Switch checked={t.review} onCheckedChange={(v) => update(t.key, { review: v })} aria-label={`Critic reviews ${t.key}`} />
                Critic reviews it
              </label>
              <label className="flex items-center gap-2 text-[13px]">
                <Switch checked={t.optional} onCheckedChange={(v) => update(t.key, { optional: v })} aria-label={`${t.key} is optional`} />
                Optional
              </label>
              <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setTasks((ts) => removeTask(ts, t.key))} aria-label={`Remove ${t.key}`}>
                <Trash2 /> Remove
              </Button>
            </div>
            {submitted && errors.byTask[t.key] ? <FieldError>{errors.byTask[t.key]!.join(" ")}</FieldError> : null}
          </li>
        ))}
      </ol>
      <Button size="sm" onClick={() => setTasks((ts) => [...ts, blankTask(ts, specialists[0]?.slug ?? "writer")])}>
        <Plus /> Add a task
      </Button>
      <div>
        <Label htmlFor="criteria">Done when (one per line)</Label>
        <Textarea id="criteria" rows={3} value={criteria} onChange={(e) => setCriteria(e.target.value)} />
      </div>
      {submitted && errors.general.length ? <FieldError>{errors.general.join(" ")}</FieldError> : null}
      <FieldError>{save.isError ? errorMessage(save.error) : undefined}</FieldError>
      <DialogFooter>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" loading={save.isPending}>
          Save plan
        </Button>
      </DialogFooter>
    </form>
  );
}
