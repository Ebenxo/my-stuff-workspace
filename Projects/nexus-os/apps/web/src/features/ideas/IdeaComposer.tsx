import type { IdeaKind } from "@nexus/schemas";
import { Button, FieldError, Input, Label, Select, Switch, toast } from "@nexus/ui";
import { CalendarClock, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useCreateIdea } from "../../lib/ideaQueries";
import { errorMessage, useProjects } from "../../lib/queries";
import { duePresets, fromLocalInput, KIND_LABEL, toLocalInput } from "./format";
import { KindPicker } from "./KindPicker";

const PLACEHOLDER: Record<IdeaKind, string> = {
  idea: "Write down an idea…",
  note: "Write a note to keep…",
  todo: "What needs doing?",
};

/** Capture an idea, a note or a to-do. Enter saves; Shift+Enter adds a line. */
export function IdeaComposer({ autoFocus = false, defaultProjectId }: { autoFocus?: boolean; defaultProjectId?: string }) {
  const create = useCreateIdea();
  const projects = useProjects("active");
  const [text, setText] = useState("");
  const [kind, setKind] = useState<IdeaKind>("idea");
  const [due, setDue] = useState(""); // datetime-local value
  const [project, setProject] = useState(defaultProjectId ?? "");
  const [pinned, setPinned] = useState(false);
  const [showDue, setShowDue] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  const canSave = text.trim().length > 0 && !create.isPending;

  function save() {
    if (!canSave) return;
    create.mutate(
      { text: text.trim(), kind, project_id: project || null, pinned, due_at: fromLocalInput(due) },
      {
        onSuccess: (idea) => {
          setText("");
          setDue("");
          setShowDue(false);
          setPinned(false);
          ref.current?.focus();
          toast.success(`${KIND_LABEL[idea.kind]} saved`);
        },
      },
    );
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
      className="rounded-xl border border-line-strong bg-surface p-3 shadow-sm"
      aria-label="Capture an idea, note or to-do"
    >
      <label htmlFor="idea-text" className="sr-only">
        {KIND_LABEL[kind]}
      </label>
      <textarea
        id="idea-text"
        ref={ref}
        value={text}
        rows={2}
        maxLength={4000}
        placeholder={PLACEHOLDER[kind]}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            save();
          }
        }}
        className="block w-full resize-none bg-transparent px-1 py-1 text-[15px] text-fg placeholder:text-fg-subtle focus-visible:outline-none"
      />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <KindPicker value={kind} onChange={setKind} idPrefix="compose-kind" />
        {showDue || due ? null : (
          <Button type="button" size="sm" variant="ghost" onClick={() => setShowDue(true)}>
            <CalendarClock /> Due time
          </Button>
        )}
        <label className="flex items-center gap-2 text-[13px] text-fg-muted">
          <Switch checked={pinned} onCheckedChange={setPinned} aria-label="Pin it" />
          Pin
        </label>
        <div className="ml-auto flex items-center gap-2">
          <Label htmlFor="idea-project" className="sr-only">
            Project
          </Label>
          <Select id="idea-project" value={project} onChange={(e) => setProject(e.target.value)} className="h-8 w-40 text-[13px]">
            <option value="">No project</option>
            {(projects.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
          <Button type="submit" variant="primary" size="sm" disabled={!canSave} loading={create.isPending}>
            Save
          </Button>
        </div>
      </div>
      {showDue || due ? (
        <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-line pt-2">
          <Label htmlFor="idea-due" className="mb-0 text-[13px]">
            Due
          </Label>
          <Input id="idea-due" type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} className="h-8 w-56 text-[13px]" />
          {duePresets().map((p) => (
            <Button key={p.id} type="button" size="sm" variant="ghost" onClick={() => setDue(toLocalInput(p.at.toISOString()))}>
              {p.label}
            </Button>
          ))}
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            aria-label="No due time"
            onClick={() => {
              setDue("");
              setShowDue(false);
            }}
          >
            <X />
          </Button>
          <p className="w-full text-xs text-fg-subtle">You get a notification when it comes due.</p>
        </div>
      ) : null}
      <FieldError>{create.isError ? errorMessage(create.error) : null}</FieldError>
    </form>
  );
}
