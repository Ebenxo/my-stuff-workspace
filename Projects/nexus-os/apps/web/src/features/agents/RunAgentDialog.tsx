import { Button, Dialog, DialogContent, DialogFooter, FieldError, Label, Select, Switch, Textarea, toast } from "@nexus/ui";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { useAgents, useModels, useStartRun } from "../../lib/agentQueries";
import { errorMessage, useProjects, useProviders } from "../../lib/queries";
import { normalizeAgent } from "./format";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agentId?: string | undefined;
  projectId?: string | undefined;
}

export function RunAgentDialog({ open, onOpenChange, agentId, projectId }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Run an agent" description="The agent works step by step. Anything risky waits for your approval.">
        {/* The dialog content unmounts when closed, so the form starts fresh every time it opens. */}
        <RunAgentForm agentId={agentId} projectId={projectId} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function RunAgentForm({ agentId, projectId, onDone }: { agentId: string | undefined; projectId: string | undefined; onDone: () => void }) {
  const agents = useAgents();
  const projects = useProjects("active");
  const providers = useProviders();
  const models = useModels();
  const start = useStartRun();
  const navigate = useNavigate();

  const usable = useMemo(() => (agents.data ?? []).map(normalizeAgent).filter((a) => a.status !== "disabled"), [agents.data]);
  const [agent, setAgent] = useState(agentId ?? "");
  const [project, setProject] = useState(projectId ?? "");
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState("");
  const [priv, setPriv] = useState(false);

  const selectedAgent = agent || usable[0]?.slug || "";
  const selectedProject = project || projects.data?.[0]?.id || "";
  const noProvider = providers.data && providers.data.length === 0;
  const canSubmit = !!selectedAgent && !!selectedProject && prompt.trim().length > 0 && !noProvider;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    start.mutate(
      {
        agent: selectedAgent,
        project_id: selectedProject,
        prompt: prompt.trim(),
        ...(model ? { model } : {}),
        private: priv,
      },
      {
        onSuccess: (run) => {
          toast.success("Started. You can follow it live.");
          onDone();
          void navigate(`/runs/${run.id}`);
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {noProvider ? (
        <p role="note" className="rounded-md border border-accent/40 bg-accent/10 px-3 py-2 text-[13px]">
          Agents need a model.{" "}
          <Link to="/settings/providers" className="text-accent-text underline" onClick={onDone}>
            Connect an AI provider
          </Link>{" "}
          first.
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor="run-agent">Agent</Label>
          <Select id="run-agent" value={selectedAgent} onChange={(e) => setAgent(e.target.value)}>
            {usable.map((a) => (
              <option key={a.id} value={a.slug}>
                {a.name}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="run-project">Project</Label>
          <Select id="run-project" value={selectedProject} onChange={(e) => setProject(e.target.value)}>
            {(projects.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
          {projects.data && projects.data.length === 0 ? (
            <p className="mt-1.5 text-[13px] text-fg-muted">Create a project first: agents work inside one.</p>
          ) : null}
        </div>
      </div>

      <div>
        <Label htmlFor="run-prompt">What should it do?</Label>
        <Textarea
          id="run-prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={4}
          maxLength={20_000}
          placeholder="Summarise the CSV in files/sales.csv and save a short report."
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor="run-model">Model</Label>
          <Select id="run-model" value={model} onChange={(e) => setModel(e.target.value)}>
            <option value="">Automatic (recommended)</option>
            {(models.data ?? []).map((m) => (
              <option key={m.ref} value={m.ref}>
                {m.provider_name} · {m.display_name ?? m.id}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex items-end gap-3 pb-2">
          <Switch id="run-private" checked={priv} onCheckedChange={setPriv} />
          <Label htmlFor="run-private" className="mb-0">
            Keep on this device
            <span className="block text-xs font-normal text-fg-subtle">Only local models; nothing is sent to a cloud provider.</span>
          </Label>
        </div>
      </div>

      <FieldError>{start.isError ? errorMessage(start.error) : undefined}</FieldError>
      <DialogFooter>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" loading={start.isPending} disabled={!canSubmit}>
          Start
        </Button>
      </DialogFooter>
    </form>
  );
}
