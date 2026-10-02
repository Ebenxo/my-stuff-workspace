import type { Idea, IdeaKind } from "@nexus/schemas";
import { Card, cn, EmptyState, ErrorState, Input, Label, Skeleton } from "@nexus/ui";
import { Lightbulb, Search } from "lucide-react";
import { useDeferredValue, useState } from "react";
import { useSearchParams } from "react-router";
import { KIND_PLURAL } from "../features/ideas/format";
import { IdeaCard } from "../features/ideas/IdeaCard";
import { IdeaComposer } from "../features/ideas/IdeaComposer";
import { StartObjectiveDialog } from "../features/ideas/StartObjectiveDialog";
import { useIdeas, type IdeaStatusFilter } from "../lib/ideaQueries";
import { errorMessage, useProjects } from "../lib/queries";
import { useNow } from "../lib/useNow";
import { Page, PageHeader } from "./Page";

function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-line-strong bg-canvas p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "h-7 rounded px-2.5 text-[13px] font-medium transition-colors",
            value === o.value ? "bg-raised text-fg shadow-sm" : "text-fg-muted hover:text-fg",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

const STATUS_OPTIONS: { value: IdeaStatusFilter; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "done", label: "Done" },
  { value: "all", label: "All" },
];
const KIND_OPTIONS: { value: IdeaKind | "any"; label: string }[] = [
  { value: "any", label: "Everything" },
  ...(Object.keys(KIND_PLURAL) as IdeaKind[]).map((k) => ({ value: k, label: KIND_PLURAL[k] })),
];

export function IdeasRoute() {
  const [params] = useSearchParams();
  const highlight = params.get("idea") ?? undefined;
  const [status, setStatus] = useState<IdeaStatusFilter>(highlight ? "all" : "open");
  const [kind, setKind] = useState<IdeaKind | "any">("any");
  const [q, setQ] = useState("");
  const query = useDeferredValue(q);
  const ideas = useIdeas({ status, kind: kind === "any" ? undefined : kind, q: query });
  const projects = useProjects();
  const [starting, setStarting] = useState<Idea | null>(null);
  const now = useNow();
  const filtered = status !== "open" || kind !== "any" || query.trim() !== "";

  return (
    <Page>
      <PageHeader
        title="Ideas & notes"
        description="Ideas, notes and to-dos: the small things worth keeping. Pin what matters; give a to-do a due time and NEXUS reminds you. Any idea can become an objective."
      />

      <div className="mb-6">
        <IdeaComposer autoFocus={params.get("new") === "1"} />
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Segmented label="Status" value={status} options={STATUS_OPTIONS} onChange={setStatus} />
        <Segmented label="Kind" value={kind} options={KIND_OPTIONS} onChange={setKind} />
        <div className="relative ml-auto w-full sm:w-56">
          <Label htmlFor="ideas-search" className="sr-only">
            Search ideas
          </Label>
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-fg-subtle" aria-hidden="true" />
          <Input id="ideas-search" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search" className="pl-8" />
        </div>
      </div>

      <Card>
        {ideas.isPending ? (
          <div className="space-y-2 p-3">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </div>
        ) : ideas.isError ? (
          <ErrorState message={errorMessage(ideas.error)} onRetry={() => void ideas.refetch()} />
        ) : ideas.data.length === 0 ? (
          <EmptyState
            icon={<Lightbulb />}
            title={filtered ? "Nothing matches" : "Nothing here yet"}
            description={
              filtered
                ? "Try another filter, or clear the search."
                : "Write down the first idea, note or to-do above. Press Enter to save it."
            }
          />
        ) : (
          <ul className="divide-y divide-line" aria-label="Ideas, notes and to-dos">
            {ideas.data.map((idea) => (
              <IdeaCard
                key={idea.id}
                idea={idea}
                projects={projects.data ?? []}
                highlight={idea.id === highlight}
                onStart={setStarting}
                now={now}
              />
            ))}
          </ul>
        )}
      </Card>
      <StartObjectiveDialog idea={starting} onOpenChange={(open) => (open ? undefined : setStarting(null))} />
    </Page>
  );
}
