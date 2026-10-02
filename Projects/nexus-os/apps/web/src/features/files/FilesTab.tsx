import { ApiError, formatBytes, formatRelativeTime } from "@nexus/shared";
import { Button, Card, Dialog, DialogContent, DialogFooter, EmptyState, ErrorState, FieldError, Input, Label, Skeleton, Textarea, toast } from "@nexus/ui";
import { ChevronRight, File, FilePlus, Folder, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { useDeleteFile, useFileContent, useFiles, useWriteFile } from "../../lib/agentQueries";
import { errorMessage } from "../../lib/queries";
import { ROOT, baseName, breadcrumbs, isWritable, joinPath, parentPath, validateNewName } from "./paths";

function FileViewer({ projectId, path, onClose }: { projectId: string; path: string; onClose: () => void }) {
  const file = useFileContent(projectId, path);
  const write = useWriteFile(projectId);
  const del = useDeleteFile(projectId);
  const [draft, setDraft] = useState<string | undefined>();
  const [confirming, setConfirming] = useState(false);
  const writable = isWritable(path);

  return (
    <Card className="mt-3">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <code className="min-w-0 flex-1 truncate font-mono text-xs">{path}</code>
        {writable && draft === undefined && file.data ? (
          <Button size="sm" onClick={() => setDraft(file.data.content)}>
            <Pencil /> Edit
          </Button>
        ) : null}
        {writable ? (
          <Button size="sm" variant="ghost" onClick={() => setConfirming(true)} aria-label={`Delete ${baseName(path)}`}>
            <Trash2 />
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" onClick={onClose}>
          Close
        </Button>
      </header>
      <div className="p-3">
        {file.isPending ? (
          <Skeleton className="h-32" />
        ) : file.isError ? (
          <ErrorState
            title={file.error instanceof ApiError && file.error.status === 422 ? "This file can’t be shown" : "Couldn’t open the file"}
            message={errorMessage(file.error)}
          />
        ) : draft !== undefined ? (
          <div>
            <label htmlFor="file-editor" className="sr-only">
              File contents
            </label>
            <Textarea id="file-editor" value={draft} onChange={(e) => setDraft(e.target.value)} rows={14} spellCheck={false} className="font-mono text-xs" />
            <FieldError>{write.isError ? errorMessage(write.error) : undefined}</FieldError>
            <p className="mt-1 text-xs text-fg-subtle">Saving keeps the previous version in the project’s history.</p>
            <div className="mt-2 flex gap-2">
              <Button
                size="sm"
                variant="primary"
                loading={write.isPending}
                onClick={() =>
                  write.mutate(
                    { path, content: draft },
                    {
                      onSuccess: () => {
                        toast.success("Saved");
                        setDraft(undefined);
                      },
                    },
                  )
                }
              >
                Save
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setDraft(undefined)}>
                Discard changes
              </Button>
            </div>
          </div>
        ) : (
          <>
            {file.data.truncated ? <p className="mb-2 text-xs text-warning">Only the start of this file is shown.</p> : null}
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words font-mono text-xs">{file.data.content || "(empty file)"}</pre>
          </>
        )}
      </div>

      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent title={`Delete ${baseName(path)}?`} description="It moves to the project’s trash, so it can be recovered.">
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={del.isPending}
              onClick={() =>
                del.mutate(path, {
                  onSuccess: () => {
                    toast.success("Moved to trash");
                    setConfirming(false);
                    onClose();
                  },
                  onError: (e) => toast.error(errorMessage(e)),
                })
              }
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function NewFileDialog({ projectId, dir, open, onOpenChange, onCreated }: { projectId: string; dir: string; open: boolean; onOpenChange: (o: boolean) => void; onCreated: (path: string) => void }) {
  const write = useWriteFile(projectId);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | undefined>();
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          setName("");
          setError(undefined);
          write.reset();
        }
        onOpenChange(o);
      }}
    >
      <DialogContent title="New file" description={`Created in ${dir}/`}>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            const problem = validateNewName(name);
            setError(problem);
            if (problem) return;
            const path = joinPath(dir, name);
            write.mutate(
              { path, content: "" },
              {
                onSuccess: () => {
                  onOpenChange(false);
                  onCreated(path);
                },
              },
            );
          }}
        >
          <div>
            <Label htmlFor="new-file-name">File name</Label>
            <Input id="new-file-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="notes.md" aria-invalid={!!error} autoFocus />
            <FieldError>{error ?? (write.isError ? errorMessage(write.error) : undefined)}</FieldError>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={write.isPending}>
              Create
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function FilesTab({ projectId }: { projectId: string }) {
  const [dir, setDir] = useState(ROOT);
  const [open, setOpen] = useState<string | undefined>();
  const [creating, setCreating] = useState(false);
  const listing = useFiles(projectId, dir);
  const crumbs = breadcrumbs(dir);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <nav aria-label="Folder path" className="flex flex-wrap items-center text-[13px]">
          {crumbs.map((c, i) => (
            <span key={c.path} className="flex items-center">
              {i > 0 ? <ChevronRight className="mx-0.5 size-3.5 text-fg-subtle" aria-hidden="true" /> : null}
              {i === crumbs.length - 1 ? (
                <span aria-current="page" className="font-medium">
                  {c.label}
                </span>
              ) : (
                <button
                  type="button"
                  className="rounded px-1 text-fg-muted hover:bg-raised hover:text-fg"
                  onClick={() => {
                    setDir(c.path);
                    setOpen(undefined);
                  }}
                >
                  {c.label}
                </button>
              )}
            </span>
          ))}
        </nav>
        {isWritable(dir) ? (
          <Button size="sm" onClick={() => setCreating(true)}>
            <FilePlus /> New file
          </Button>
        ) : null}
      </div>

      <Card className="mt-3">
        {listing.isPending ? (
          <Skeleton className="m-3 h-28" />
        ) : listing.isError ? (
          <ErrorState message={errorMessage(listing.error)} onRetry={() => void listing.refetch()} />
        ) : listing.data.length === 0 ? (
          <EmptyState
            icon={<Folder />}
            title="This folder is empty"
            description={isWritable(dir) ? "Create a file here, or ask an agent to." : "Agents save their deliverables here."}
          />
        ) : (
          <ul className="divide-y divide-line" aria-label="Files">
            {dir !== ROOT ? (
              <li>
                <button type="button" className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] text-fg-muted hover:bg-raised/60" onClick={() => setDir(parentPath(dir))}>
                  <Folder className="size-4" aria-hidden="true" /> ..
                </button>
              </li>
            ) : null}
            {listing.data.map((e) => (
              <li key={e.path}>
                <button
                  type="button"
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-raised/60"
                  onClick={() => (e.kind === "dir" ? (setDir(e.path), setOpen(undefined)) : setOpen(e.path))}
                  aria-current={open === e.path ? "true" : undefined}
                >
                  {e.kind === "dir" ? <Folder className="size-4 text-accent-text" aria-hidden="true" /> : <File className="size-4 text-fg-subtle" aria-hidden="true" />}
                  <span className="min-w-0 flex-1 truncate">{baseName(e.path)}</span>
                  {e.kind === "file" ? (
                    <span className="font-mono text-[11px] text-fg-subtle">
                      {formatBytes(e.size)} · {formatRelativeTime(new Date(e.modified * 1000))}
                    </span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {open ? <FileViewer key={open} projectId={projectId} path={open} onClose={() => setOpen(undefined)} /> : null}
      <NewFileDialog projectId={projectId} dir={dir} open={creating} onOpenChange={setCreating} onCreated={(p) => setOpen(p)} />
    </div>
  );
}
