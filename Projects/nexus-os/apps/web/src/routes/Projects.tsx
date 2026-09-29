import { Button, EmptyState, ErrorState, Skeleton } from "@nexus/ui";
import { FolderPlus, Plus } from "lucide-react";
import { useState } from "react";
import { NewProjectDialog } from "../features/projects/NewProjectDialog";
import { ProjectCard } from "../features/projects/ProjectCard";
import { errorMessage, useProjects } from "../lib/queries";
import { Page, PageHeader } from "./Page";

export function ProjectsRoute() {
  const [showArchived, setShowArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const projects = useProjects(showArchived ? "archived" : "active");

  return (
    <Page>
      <PageHeader
        title="Projects"
        description="Each project is a workspace with its own files, conversations, agents and memory."
        actions={
          <>
            <Button variant="ghost" size="sm" aria-pressed={showArchived} onClick={() => setShowArchived((v) => !v)}>
              {showArchived ? "Show active" : "Show archived"}
            </Button>
            <Button variant="primary" onClick={() => setCreating(true)}>
              <Plus /> New project
            </Button>
          </>
        }
      />
      {projects.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : projects.isError ? (
        <ErrorState title="Couldn't load projects" message={errorMessage(projects.error)} onRetry={() => void projects.refetch()} />
      ) : projects.data.length === 0 ? (
        <EmptyState
          icon={<FolderPlus />}
          title={showArchived ? "No archived projects" : "Create your first project"}
          description={showArchived ? undefined : "Projects hold everything NEXUS needs to work on something for you."}
          action={
            showArchived ? undefined : (
              <Button variant="primary" onClick={() => setCreating(true)}>
                <Plus /> New project
              </Button>
            )
          }
        />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {projects.data.map((p) => (
            <li key={p.id}>
              <ProjectCard project={p} />
            </li>
          ))}
        </ul>
      )}
      <NewProjectDialog open={creating} onOpenChange={setCreating} />
    </Page>
  );
}
