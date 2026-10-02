import { Dialog, DialogContent, toast } from "@nexus/ui";
import { useNavigate } from "react-router";
import { errorMessage, useCreateProject } from "../../lib/queries";
import { ProjectForm } from "./ProjectForm";

export function NewProjectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const create = useCreateProject();
  const navigate = useNavigate();
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) create.reset();
        onOpenChange(o);
      }}
    >
      <DialogContent title="New project" description="A project keeps its files, conversations, agents and memory together.">
        <ProjectForm
          submitLabel="Create project"
          pending={create.isPending}
          error={create.isError ? errorMessage(create.error) : undefined}
          onCancel={() => onOpenChange(false)}
          onSubmit={(v) =>
            create.mutate(
              {
                name: v.name,
                description: v.description,
                settings: { permission_level: v.permission_level, monthly_budget_usd: v.monthly_budget_usd },
              },
              {
                onSuccess: (project) => {
                  toast.success(`Created “${project.name}”`);
                  onOpenChange(false);
                  void navigate(`/projects/${project.id}`);
                },
              },
            )
          }
        />
      </DialogContent>
    </Dialog>
  );
}
