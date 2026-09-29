import { Button, FieldError, Label, Select, Switch, toast } from "@nexus/ui";
import { FlaskConical, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useCreateObjective, useStartDemo } from "../../lib/objectiveQueries";
import { errorMessage, useHasRealProvider, useProjects } from "../../lib/queries";

/**
 * The Command Center's main input. By default the plan is shown for review before anything runs;
 * the person can opt into running it straight away.
 */
export function ObjectiveComposer({ projectId, onNewProject }: { projectId?: string; onNewProject?: () => void }) {
  const projects = useProjects("active");
  const create = useCreateObjective();
  const demo = useStartDemo();
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [project, setProject] = useState(projectId ?? "");
  const [review, setReview] = useState(true);
  const [priv, setPriv] = useState(false);
  const [params] = useSearchParams();
  // Focus only on a deliberate request to write one (?focus=objective, e.g. from the command palette).
  const focus = params.get("focus") === "objective";

  const selectedProject = project || projects.data?.[0]?.id || "";
  const noProvider = useHasRealProvider() === false;
  const noProject = projects.data?.length === 0;
  const canSubmit = text.trim().length >= 3 && !!selectedProject && !noProvider;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    create.mutate(
      { project_id: selectedProject, text: text.trim(), run_mode: review ? "review_plan" : "auto", private: priv },
      {
        onSuccess: (o) => {
          setText("");
          void navigate(`/objectives/${o.id}`);
        },
      },
    );
  }

  function startDemo() {
    demo.mutate(undefined, {
      onSuccess: (o) => {
        toast.success("Demo started with scripted agents. Nothing leaves this machine.");
        void navigate(`/objectives/${o.id}`);
      },
      onError: (e) => toast.error(errorMessage(e)),
    });
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-line-strong bg-surface p-3 shadow-sm">
      <label htmlFor="objective" className="sr-only">
        Objective
      </label>
      <textarea
        id="objective"
        autoFocus={focus}
        rows={3}
        value={text}
        maxLength={20_000}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit();
        }}
        placeholder="Describe an objective, e.g. “Compare three note-taking apps and write a one-page recommendation.”"
        className="w-full resize-y bg-transparent px-2 py-1.5 text-[15px] text-fg placeholder:text-fg-subtle focus-visible:outline-none"
      />
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-2 pt-2">
        {projectId ? null : (
          <div className="flex items-center gap-2">
            <Label htmlFor="objective-project" className="mb-0 text-xs text-fg-muted">
              Project
            </Label>
            <Select id="objective-project" value={selectedProject} onChange={(e) => setProject(e.target.value)} className="h-8 w-44 text-[13px]">
              {(projects.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </div>
        )}
        <label className="flex items-center gap-2 text-xs text-fg-muted">
          <Switch checked={review} onCheckedChange={setReview} aria-label="Review the plan first" />
          Review the plan first
        </label>
        <label className="flex items-center gap-2 text-xs text-fg-muted">
          <Switch checked={priv} onCheckedChange={setPriv} aria-label="Keep on this device" />
          Keep on this device
        </label>
        <div className="ml-auto flex items-center gap-2">
          {projectId ? null : (
            <Button size="sm" variant="ghost" loading={demo.isPending} onClick={startDemo}>
              <FlaskConical /> Try the demo
            </Button>
          )}
          <Button type="submit" size="sm" variant="primary" loading={create.isPending} disabled={!canSubmit}>
            <Sparkles /> Start
          </Button>
        </div>
      </div>
      {noProvider ? (
        <p className="px-2 pt-2 text-xs text-fg-muted">
          <Link to="/settings/providers" className="text-accent-text underline">
            Connect an AI provider
          </Link>{" "}
          to start your own objectives.{projectId ? "" : " The demo works without one."}
        </p>
      ) : noProject && !projectId ? (
        <p className="px-2 pt-2 text-xs text-fg-muted">
          Objectives run inside a project.{" "}
          {onNewProject ? (
            <button type="button" onClick={onNewProject} className="text-accent-text underline">
              Create one
            </button>
          ) : (
            "Create one first."
          )}
        </p>
      ) : null}
      <div className="px-2">
        <FieldError>{create.isError ? errorMessage(create.error) : undefined}</FieldError>
      </div>
    </form>
  );
}
