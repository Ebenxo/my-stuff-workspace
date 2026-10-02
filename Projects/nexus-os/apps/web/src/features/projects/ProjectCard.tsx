import type { Project } from "@nexus/schemas";
import { formatRelativeTime } from "@nexus/shared";
import { Badge, Card } from "@nexus/ui";
import { FolderOpen } from "lucide-react";
import { Link } from "react-router";

export function ProjectCard({ project }: { project: Project }) {
  return (
    <Link
      to={`/projects/${project.id}`}
      className="group block rounded-lg outline-offset-2 focus-visible:outline-2"
    >
      <Card className="h-full p-4 transition-colors group-hover:border-line-strong group-hover:bg-raised">
        <div className="flex items-start gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-md bg-accent/15 text-accent-text">
            <FolderOpen className="size-4" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="truncate text-sm font-medium text-fg">{project.name}</h3>
              {project.status === "archived" ? <Badge tone="warning">Archived</Badge> : null}
              {project.is_demo ? <Badge tone="info">Demo</Badge> : null}
            </div>
            <p className="mt-0.5 line-clamp-2 text-[13px] text-fg-muted">
              {project.description || "No description yet."}
            </p>
            <p className="mt-2 text-xs text-fg-subtle">Updated {formatRelativeTime(project.updated_at)}</p>
          </div>
        </div>
      </Card>
    </Link>
  );
}
