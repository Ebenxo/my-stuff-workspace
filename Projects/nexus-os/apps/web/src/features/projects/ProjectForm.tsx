import type { PermissionLevel, Project } from "@nexus/schemas";
import { Button, DialogFooter, FieldError, Input, Label, Textarea } from "@nexus/ui";
import { useState, type FormEvent } from "react";
import { PERMISSION_COPY } from "./permissions";

export interface ProjectFormValues {
  name: string;
  description: string;
  permission_level: PermissionLevel | null;
}

export function ProjectForm({
  initial,
  submitLabel,
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  initial?: Project;
  submitLabel: string;
  pending: boolean;
  error?: string | undefined;
  onSubmit: (values: ProjectFormValues) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [level, setLevel] = useState<PermissionLevel | "">(initial?.settings.permission_level ?? "");
  const [touched, setTouched] = useState(false);
  const nameError = touched && name.trim() === "" ? "Give the project a name." : undefined;

  function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (name.trim() === "") return;
    onSubmit({ name: name.trim(), description: description.trim(), permission_level: level || null });
  }

  return (
    <form onSubmit={submit} noValidate>
      <div className="space-y-4">
        <div>
          <Label htmlFor="project-name">Name</Label>
          <Input
            id="project-name"
            value={name}
            maxLength={120}
            autoFocus
            aria-invalid={nameError ? true : undefined}
            aria-describedby={nameError ? "project-name-error" : undefined}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => setTouched(true)}
            placeholder="e.g. YouTube Automation"
          />
          <div id="project-name-error">
            <FieldError>{nameError}</FieldError>
          </div>
        </div>
        <div>
          <Label htmlFor="project-desc">Description</Label>
          <Textarea
            id="project-desc"
            value={description}
            maxLength={2000}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What is this project for?"
          />
        </div>
        <div>
          <Label htmlFor="project-perm">Permissions</Label>
          <select
            id="project-perm"
            value={level}
            onChange={(e) => setLevel(e.target.value as PermissionLevel | "")}
            className="h-9 w-full rounded-md border border-control bg-canvas px-2.5 text-sm text-fg hover:border-fg-subtle"
          >
            <option value="">Use my default</option>
            {(Object.keys(PERMISSION_COPY) as PermissionLevel[]).map((k) => (
              <option key={k} value={k}>
                {PERMISSION_COPY[k].label}
              </option>
            ))}
          </select>
          <p className="mt-1.5 text-xs text-fg-muted">
            {level ? PERMISSION_COPY[level].help : "This project follows the default in Settings."}
          </p>
        </div>
        <FieldError>{error}</FieldError>
      </div>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" loading={pending}>
          {submitLabel}
        </Button>
      </DialogFooter>
    </form>
  );
}
