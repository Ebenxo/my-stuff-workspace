import { formatRelativeTime } from "@nexus/shared";
import type { Idea, IdeaKind, Project } from "@nexus/schemas";
import { Badge, Button, cn, FieldError, Input, Label, Select, Textarea, toast, Tooltip } from "@nexus/ui";
import { Check, Pencil, Pin, Rocket, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { useDeleteIdea, useUpdateIdea } from "../../lib/ideaQueries";
import { errorMessage } from "../../lib/queries";
import { dueLabel, fromLocalInput, KIND_LABEL, toLocalInput } from "./format";
import { KIND_ICON } from "./icons";
import { KindPicker } from "./KindPicker";

function Editor({ idea, projects, onClose }: { idea: Idea; projects: Project[]; onClose: () => void }) {
  const update = useUpdateIdea();
  const [text, setText] = useState(idea.text);
  const [kind, setKind] = useState<IdeaKind>(idea.kind);
  const [due, setDue] = useState(toLocalInput(idea.due_at));
  const [project, setProject] = useState(idea.project_id ?? "");

  function save(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    update.mutate(
      { id: idea.id, body: { text: text.trim(), kind, due_at: fromLocalInput(due), project_id: project || null } },
      { onSuccess: onClose },
    );
  }

  return (
    <form onSubmit={save} className="space-y-2" aria-label="Edit">
      <Label htmlFor={`edit-${idea.id}`} className="sr-only">
        Text
      </Label>
      <Textarea
        id={`edit-${idea.id}`}
        value={text}
        maxLength={4000}
        autoFocus
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose();
        }}
      />
      <div className="flex flex-wrap items-center gap-2">
        <KindPicker value={kind} onChange={setKind} idPrefix={`edit-kind-${idea.id}`} />
        <Label htmlFor={`edit-due-${idea.id}`} className="sr-only">
          Due
        </Label>
        <Input
          id={`edit-due-${idea.id}`}
          type="datetime-local"
          value={due}
          onChange={(e) => setDue(e.target.value)}
          className="h-8 w-56 text-[13px]"
        />
        <Label htmlFor={`edit-project-${idea.id}`} className="sr-only">
          Project
        </Label>
        <Select
          id={`edit-project-${idea.id}`}
          value={project}
          onChange={(e) => setProject(e.target.value)}
          className="h-8 w-40 text-[13px]"
        >
          <option value="">No project</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
        <div className="ml-auto flex gap-2">
          <Button type="button" size="sm" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" variant="primary" loading={update.isPending} disabled={!text.trim()}>
            Save
          </Button>
        </div>
      </div>
      <FieldError>{update.isError ? errorMessage(update.error) : null}</FieldError>
    </form>
  );
}

export function IdeaCard({
  idea,
  projects,
  highlight,
  onStart,
  now = new Date(),
}: {
  idea: Idea;
  projects: Project[];
  highlight?: boolean;
  onStart: (idea: Idea) => void;
  now?: Date;
}) {
  const update = useUpdateIdea();
  const remove = useDeleteIdea();
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const ref = useRef<HTMLLIElement>(null);
  const done = idea.status === "done";
  const Icon = KIND_ICON[idea.kind];
  const project = projects.find((p) => p.id === idea.project_id);
  const due = idea.due_at ? dueLabel(idea.due_at, now) : null;

  useEffect(() => {
    if (highlight) ref.current?.scrollIntoView({ block: "center" });
  }, [highlight]);

  useEffect(() => {
    if (!confirming) return;
    const t = setTimeout(() => setConfirming(false), 4000);
    return () => clearTimeout(t);
  }, [confirming]);

  const fail = (e: unknown) => toast.error(errorMessage(e));

  return (
    <li
      ref={ref}
      className={cn("group flex items-start gap-3 px-3 py-3", highlight && "bg-accent/5 ring-1 ring-inset ring-accent/40")}
      aria-label={`${KIND_LABEL[idea.kind]}: ${idea.text.slice(0, 60)}`}
    >
      <button
        type="button"
        role="checkbox"
        aria-checked={done}
        aria-label={done ? "Mark as not done" : "Mark as done"}
        disabled={update.isPending}
        onClick={() => update.mutate({ id: idea.id, body: { status: done ? "open" : "done" } }, { onError: fail })}
        className={cn(
          "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border transition-colors",
          done ? "border-success bg-success text-canvas" : "border-control hover:border-accent",
        )}
      >
        {done ? <Check className="size-3" aria-hidden="true" /> : null}
      </button>

      <div className="flex min-w-0 flex-1 flex-col gap-1 sm:flex-row sm:items-start sm:gap-3">
        <div className="min-w-0 flex-1">
          {editing ? (
            <Editor idea={idea} projects={projects} onClose={() => setEditing(false)} />
          ) : (
            <>
              <p className={cn("whitespace-pre-wrap break-words text-[14px] text-fg", done && "text-fg-subtle line-through")}>
                {idea.text}
              </p>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-subtle">
                <Badge tone="neutral">
                  <Icon className="size-3" aria-hidden="true" />
                  {KIND_LABEL[idea.kind]}
                </Badge>
                {due && !done ? <Badge tone={due.tone}>{due.text}</Badge> : null}
                {project ? (
                  <Link to={`/projects/${project.id}`} className="hover:text-fg hover:underline">
                    {project.name}
                  </Link>
                ) : null}
                {idea.objective_id ? (
                  <Link to={`/objectives/${idea.objective_id}`} className="text-accent-text hover:underline">
                    Started as an objective
                  </Link>
                ) : null}
                <span>
                  {done && idea.done_at
                    ? `Done ${formatRelativeTime(idea.done_at, now)}`
                    : `Added ${formatRelativeTime(idea.created_at, now)}`}
                </span>
              </div>
            </>
          )}
        </div>

        {editing ? null : (
          <div className="-ml-2 flex shrink-0 items-center gap-0.5 sm:ml-0">
            <Tooltip side="top" label={idea.pinned ? "Unpin" : "Pin"}>
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label={idea.pinned ? "Unpin" : "Pin"}
                aria-pressed={idea.pinned}
                onClick={() => update.mutate({ id: idea.id, body: { pinned: !idea.pinned } }, { onError: fail })}
                className={idea.pinned ? "text-accent-text [&_svg]:fill-current" : "text-fg-subtle"}
              >
                <Pin />
              </Button>
            </Tooltip>
            <Tooltip side="top" label="Edit">
              <Button size="icon-sm" variant="ghost" aria-label="Edit" onClick={() => setEditing(true)}>
                <Pencil />
              </Button>
            </Tooltip>
            {!done && !idea.objective_id ? (
              <Tooltip side="top" label="Start as an objective">
                <Button size="icon-sm" variant="ghost" aria-label="Start as an objective" onClick={() => onStart(idea)}>
                  <Rocket />
                </Button>
              </Tooltip>
            ) : null}
            {confirming ? (
              <Button
                size="sm"
                variant="danger"
                loading={remove.isPending}
                onClick={() => remove.mutate(idea.id, { onSuccess: () => toast.success("Deleted"), onError: fail })}
              >
                Delete?
              </Button>
            ) : (
              <Tooltip side="top" label="Delete">
                <Button size="icon-sm" variant="ghost" aria-label="Delete" onClick={() => setConfirming(true)}>
                  <Trash2 />
                </Button>
              </Tooltip>
            )}
          </div>
        )}
      </div>
    </li>
  );
}
