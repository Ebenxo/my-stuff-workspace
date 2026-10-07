import { Badge, Button, Dialog, DialogContent, DialogFooter, FieldError, Input, Label, Select, Switch, Textarea, toast } from "@nexus/ui";
import { useMemo, useState } from "react";
import { useCreateAgent, usePickableModels, useTools, useUpdateAgent } from "../../lib/agentQueries";
import { errorMessage } from "../../lib/queries";
import { EMPTY_FORM, toCreate, toForm, toUpdate, unusableTools, validateForm, type AgentForm, type FormErrors } from "./form";
import { RISK, RISK_ORDER, type AgentView } from "./format";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Undefined = create a custom agent. */
  agent?: AgentView | undefined;
}

export function AgentDialog({ open, onOpenChange, agent }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title={agent ? (agent.builtin ? `Tune ${agent.name}` : `Edit ${agent.name}`) : "New agent"}
        description={
          agent?.builtin
            ? "Built-in agents keep their role and instructions. You can change which model they prefer, their limits and their tools."
            : "A custom agent uses the same safety rules as the built-in ones: everything goes through permissions."
        }
      >
        <AgentFormBody key={agent?.id ?? "new"} agent={agent} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function NumberField({
  id,
  label,
  value,
  error,
  onChange,
  hint,
}: {
  id: string;
  label: string;
  value: string;
  error: string | undefined;
  onChange: (v: string) => void;
  hint?: string;
}) {
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value)} aria-invalid={!!error} />
      {hint && !error ? <p className="mt-1 text-xs text-fg-subtle">{hint}</p> : null}
      <FieldError>{error}</FieldError>
    </div>
  );
}

function AgentFormBody({ agent, onDone }: { agent: AgentView | undefined; onDone: () => void }) {
  const builtin = agent?.builtin ?? false;
  const tools = useTools();
  const models = usePickableModels();
  const create = useCreateAgent();
  const update = useUpdateAgent(agent?.id ?? "");
  const [form, setForm] = useState<AgentForm>(() => (agent ? toForm(agent) : EMPTY_FORM));
  const [errors, setErrors] = useState<FormErrors>({});
  const set = <K extends keyof AgentForm>(k: K, v: AgentForm[K]) => setForm((f) => ({ ...f, [k]: v }));
  const pending = create.isPending || update.isPending;
  const failure = create.error ?? update.error;

  const grouped = useMemo(
    () =>
      RISK_ORDER.map((risk) => ({ risk, items: (tools.data ?? []).filter((t) => t.risk_level === risk) })).filter((g) => g.items.length),
    [tools.data],
  );
  const dead = useMemo(
    () => unusableTools(form.tools, tools.data ?? [], form.maxRisk, RISK_ORDER),
    [form.tools, form.maxRisk, tools.data],
  );

  function toggleTool(name: string, on: boolean) {
    set("tools", on ? [...new Set([...form.tools, name])] : form.tools.filter((t) => t !== name));
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const found = validateForm(form, builtin);
    setErrors(found);
    if (Object.keys(found).length) return;
    const done = {
      onSuccess: () => {
        toast.success(agent ? "Agent updated" : "Agent created");
        onDone();
      },
    };
    if (!agent) create.mutate(toCreate(form), done);
    else {
      const patch = toUpdate(agent, form);
      if (Object.keys(patch).length === 0) return onDone();
      update.mutate(patch, done);
    }
  }

  return (
    <form onSubmit={submit} className="max-h-[70vh] space-y-5 overflow-y-auto pr-1">
      {!builtin ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="agent-name">Name</Label>
            <Input id="agent-name" value={form.name} onChange={(e) => set("name", e.target.value)} aria-invalid={!!errors.name} />
            <FieldError>{errors.name}</FieldError>
          </div>
          <div>
            <Label htmlFor="agent-role">Role</Label>
            <Input id="agent-role" value={form.role} onChange={(e) => set("role", e.target.value)} placeholder="Writes release notes" aria-invalid={!!errors.role} />
            <FieldError>{errors.role}</FieldError>
          </div>
          <div className="sm:col-span-2">
            <Label htmlFor="agent-prompt">Instructions</Label>
            <Textarea
              id="agent-prompt"
              value={form.systemPrompt}
              onChange={(e) => set("systemPrompt", e.target.value)}
              rows={5}
              placeholder="Describe how this agent should work and what good output looks like."
            />
          </div>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor="agent-model">Preferred model</Label>
          <Select id="agent-model" value={form.preferredModel} onChange={(e) => set("preferredModel", e.target.value)}>
            <option value="">Automatic (recommended)</option>
            {(models.data ?? []).map((m) => (
              <option key={m.ref} value={m.ref}>
                {m.provider_name} · {m.display_name ?? m.id}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="agent-risk">Most risk it may ever take on</Label>
          <Select id="agent-risk" value={form.maxRisk} onChange={(e) => set("maxRisk", e.target.value as AgentForm["maxRisk"])}>
            {RISK_ORDER.map((r) => (
              <option key={r} value={r}>
                {RISK[r].label}: {RISK[r].meaning}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <fieldset>
        <legend className="mb-1.5 text-[13px] font-medium text-fg-muted">Tools it can use</legend>
        {tools.isPending ? (
          <p className="text-[13px] text-fg-subtle">Loading tools…</p>
        ) : (
          <div className="space-y-3 rounded-md border border-line p-3">
            {grouped.map((g) => (
              <div key={g.risk}>
                <p className="mb-1 flex items-center gap-2 text-xs text-fg-subtle">
                  <Badge tone={RISK[g.risk].tone}>{RISK[g.risk].label}</Badge>
                  {RISK[g.risk].meaning}
                </p>
                <ul className="grid gap-1 sm:grid-cols-2">
                  {g.items.map((t) => (
                    <li key={t.name}>
                      <label className="flex items-start gap-2 rounded px-1 py-0.5 text-[13px] hover:bg-raised">
                        <input
                          type="checkbox"
                          className="mt-1"
                          checked={form.tools.includes(t.name)}
                          onChange={(e) => toggleTool(t.name, e.target.checked)}
                        />
                        <span>
                          <code className="font-mono text-xs">{t.name}</code>
                          {t.requires_approval ? <span className="ml-1.5 text-[11px] text-warning">always asks</span> : null}
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
        {dead.length ? (
          <p role="note" className="mt-2 text-[13px] text-warning">
            {dead.join(", ")} can never run: {dead.length === 1 ? "its" : "their"} risk is above this agent’s limit. Raise the limit or remove{" "}
            {dead.length === 1 ? "it" : "them"}.
          </p>
        ) : null}
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-3">
        <NumberField id="agent-steps" label="Max steps" value={form.maxSteps} error={errors.maxSteps} onChange={(v) => set("maxSteps", v)} />
        <NumberField id="agent-tools" label="Max tool calls" value={form.maxToolCalls} error={errors.maxToolCalls} onChange={(v) => set("maxToolCalls", v)} />
        <NumberField
          id="agent-runtime"
          label="Max runtime (seconds)"
          value={form.maxRuntimeS}
          error={errors.maxRuntimeS}
          onChange={(v) => set("maxRuntimeS", v)}
          hint="Time spent waiting for you doesn’t count."
        />
        <NumberField id="agent-budget" label="Token budget" value={form.tokenBudget} error={errors.tokenBudget} onChange={(v) => set("tokenBudget", v)} />
        <NumberField id="agent-temp" label="Temperature" value={form.temperature} error={errors.temperature} onChange={(v) => set("temperature", v)} hint="0 = precise, 1 = varied" />
        <div className="flex items-end gap-3 pb-2">
          <Switch id="agent-enabled" checked={form.enabled} onCheckedChange={(v) => set("enabled", v)} />
          <Label htmlFor="agent-enabled" className="mb-0">
            Enabled
          </Label>
        </div>
      </div>

      <FieldError>{failure ? errorMessage(failure) : undefined}</FieldError>
      <DialogFooter>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" loading={pending}>
          {agent ? "Save changes" : "Create agent"}
        </Button>
      </DialogFooter>
    </form>
  );
}
