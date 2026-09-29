import type { MemoryItem } from "@nexus/schemas";
import { Button, Dialog, DialogContent, DialogFooter, FieldError, Input, Label, Select, Switch, Textarea, toast } from "@nexus/ui";
import { useState } from "react";
import { useCreateMemory, useUpdateMemory } from "../../lib/memoryQueries";
import { errorMessage, useProjects } from "../../lib/queries";
import { parseTags } from "./format";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Edit this memory; without it, a new memory is written. */
  item?: MemoryItem | undefined;
  projectId?: string | undefined;
}

export function MemoryDialog({ open, onOpenChange, item, projectId }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title={item ? "Edit memory" : "Add a memory"}
        description="Agents are given relevant memories as background. Never store passwords, keys or personal identifiers: they are refused."
      >
        <MemoryForm key={item?.id ?? "new"} item={item} projectId={projectId} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function MemoryForm({ item, projectId, onDone }: { item: MemoryItem | undefined; projectId: string | undefined; onDone: () => void }) {
  const projects = useProjects("active");
  const create = useCreateMemory();
  const update = useUpdateMemory();
  const [content, setContent] = useState(item?.content ?? "");
  const [tags, setTags] = useState((item?.tags ?? []).join(", "));
  const [pinned, setPinned] = useState((item?.importance ?? 0) >= 1);
  const [scope, setScope] = useState<"project" | "global">(item?.scope === "global" ? "global" : "project");
  const [project, setProject] = useState(projectId ?? "");
  const chosenProject = project || projects.data?.[0]?.id || "";
  const pending = create.isPending || update.isPending;
  const error = create.error ?? update.error;
  const valid = content.trim().length >= 3 && (scope === "global" || !!chosenProject || !!item);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid) return;
    const done = {
      onSuccess: () => {
        toast.success(item ? "Memory updated" : "Remembered");
        onDone();
      },
    };
    if (item) {
      update.mutate({ id: item.id, body: { content: content.trim(), tags: parseTags(tags), pinned } }, done);
    } else {
      create.mutate(
        {
          scope,
          content: content.trim(),
          tags: parseTags(tags),
          pinned,
          ...(scope === "project" ? { project_id: chosenProject } : {}),
        },
        done,
      );
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <Label htmlFor="memory-content">What should be remembered?</Label>
        <Textarea
          id="memory-content"
          rows={4}
          maxLength={4000}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="The client prefers British spelling and a friendly, plain tone."
        />
        <p className="mt-1 text-xs text-fg-subtle">One self-contained fact, decision or preference reads best.</p>
      </div>
      {item ? null : (
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="memory-scope">Applies to</Label>
            <Select id="memory-scope" value={scope} onChange={(e) => setScope(e.target.value as "project" | "global")}>
              <option value="project">One project</option>
              <option value="global">All projects</option>
            </Select>
          </div>
          {scope === "project" && !projectId ? (
            <div>
              <Label htmlFor="memory-project">Project</Label>
              <Select id="memory-project" value={chosenProject} onChange={(e) => setProject(e.target.value)}>
                {(projects.data ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </Select>
            </div>
          ) : null}
        </div>
      )}
      <div>
        <Label htmlFor="memory-tags">Tags</Label>
        <Input id="memory-tags" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="style, billing" />
      </div>
      <label className="flex items-center gap-3 text-[13px]">
        <Switch checked={pinned} onCheckedChange={setPinned} aria-label="Pin" />
        <span>
          Pin it
          <span className="block text-xs text-fg-subtle">Pinned project memories are given to every agent in the project.</span>
        </span>
      </label>
      <FieldError>{error ? errorMessage(error) : undefined}</FieldError>
      <DialogFooter>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" loading={pending} disabled={!valid}>
          {item ? "Save" : "Remember"}
        </Button>
      </DialogFooter>
    </form>
  );
}
