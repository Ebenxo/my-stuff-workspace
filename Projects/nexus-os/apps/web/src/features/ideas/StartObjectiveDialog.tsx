import type { Idea } from "@nexus/schemas";
import { Button, Dialog, DialogContent, DialogFooter, FieldError, Label, Select, Switch } from "@nexus/ui";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { useStartIdeaObjective } from "../../lib/ideaQueries";
import { errorMessage, useHasRealProvider, useProjects } from "../../lib/queries";

/** Hand an idea to NEXUS as an objective. By default the plan is shown for review before anything runs. */
export function StartObjectiveDialog({ idea, onOpenChange }: { idea: Idea | null; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={idea !== null} onOpenChange={onOpenChange}>
      <DialogContent title="Start as an objective" description="NEXUS plans it, and the agents do the work.">
        {/* Keyed by idea, so every idea opens with fresh choices. */}
        {idea ? <StartForm key={idea.id} idea={idea} onDone={() => onOpenChange(false)} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function StartForm({ idea, onDone }: { idea: Idea; onDone: () => void }) {
  const projects = useProjects("active");
  const start = useStartIdeaObjective();
  const navigate = useNavigate();
  const noProvider = useHasRealProvider() === false;
  const [project, setProject] = useState(idea.project_id ?? "");
  const [review, setReview] = useState(true);
  const [priv, setPriv] = useState(false);

  const selected = project || projects.data?.[0]?.id || "";
  const noProjects = projects.data?.length === 0;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!selected || noProvider) return;
    start.mutate(
      {
        id: idea.id,
        body: {
          project_id: selected,
          run_mode: review ? "review_plan" : "auto",
          private: priv,
        },
      },
      {
        onSuccess: (res) => {
          onDone();
          void navigate(`/objectives/${res.objective.id}`);
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <blockquote className="max-h-32 overflow-auto whitespace-pre-wrap rounded-md border border-line bg-canvas px-3 py-2 text-[13px] text-fg">
        {idea.text}
      </blockquote>
      {noProvider ? (
        <p className="text-[13px] text-fg-muted">
          Connect an AI provider first.{" "}
          <Link to="/settings/providers" className="text-accent-text hover:underline">
            Connect a provider
          </Link>
        </p>
      ) : null}
      {noProjects ? (
        <p className="text-[13px] text-fg-muted">
          Objectives live in a project.{" "}
          <Link to="/projects?new=1" className="text-accent-text hover:underline">
            Create a project
          </Link>
        </p>
      ) : (
        <div>
          <Label htmlFor="idea-objective-project">Project</Label>
          <Select id="idea-objective-project" value={selected} onChange={(e) => setProject(e.target.value)}>
            {(projects.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        </div>
      )}
      <label className="flex items-center justify-between gap-3 text-[13px] text-fg">
        Show me the plan before anything runs
        <Switch checked={review} onCheckedChange={setReview} aria-label="Show me the plan before anything runs" />
      </label>
      <label className="flex items-center justify-between gap-3 text-[13px] text-fg">
        Keep it on this device (local models only)
        <Switch checked={priv} onCheckedChange={setPriv} aria-label="Keep it on this device" />
      </label>
      <FieldError>{start.isError ? errorMessage(start.error) : null}</FieldError>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" loading={start.isPending} disabled={!selected || noProvider}>
          Start
        </Button>
      </DialogFooter>
    </form>
  );
}
