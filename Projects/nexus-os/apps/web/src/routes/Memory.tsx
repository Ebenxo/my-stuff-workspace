import { Label, Select } from "@nexus/ui";
import { useSearchParams } from "react-router";
import { MemoryBrowser } from "../features/memory/MemoryBrowser";
import { useProjects } from "../lib/queries";
import { Page, PageHeader } from "./Page";

export function MemoryRoute() {
  const [params, setParams] = useSearchParams();
  const projects = useProjects("active");
  const projectId = params.get("project") ?? undefined;
  return (
    <Page>
      <PageHeader
        title="Memory"
        description="What NEXUS remembers across your work: facts, decisions and preferences. Agents are given the relevant ones as background, clearly marked as data. Everything here is yours to edit or delete."
      />
      <div className="mb-4 flex items-center gap-2">
        <Label htmlFor="memory-project-filter" className="mb-0 text-xs text-fg-muted">
          Project
        </Label>
        <Select
          id="memory-project-filter"
          value={projectId ?? ""}
          onChange={(e) => {
            const next = new URLSearchParams(params);
            if (e.target.value) next.set("project", e.target.value);
            else next.delete("project");
            next.delete("memory");
            setParams(next, { replace: true });
          }}
          className="h-8 w-56 text-[13px]"
        >
          <option value="">All projects</option>
          {(projects.data ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
      </div>
      <MemoryBrowser key={projectId ?? "all"} projectId={projectId} focusId={params.get("memory")} />
    </Page>
  );
}
