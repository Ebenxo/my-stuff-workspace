import type { SearchHit } from "@nexus/schemas";
import { Card, EmptyState, ErrorState, Input, Skeleton } from "@nexus/ui";
import { Search as SearchIcon } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { KIND_LABEL, searchHref, snippetParts } from "../features/memory/format";
import { useUniversalSearch } from "../lib/memoryQueries";
import { errorMessage } from "../lib/queries";
import { Page, PageHeader, Section } from "./Page";

const ORDER: SearchHit["kind"][] = ["project", "objective", "artifact", "memory"];

function Snippet({ text }: { text: string }) {
  return (
    <>
      {snippetParts(text).map((p, i) =>
        p.hit ? (
          <mark key={i} className="rounded bg-accent/25 px-0.5 text-fg">
            {p.text}
          </mark>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </>
  );
}

function SearchBox({ initial, onSearch }: { initial: string; onSearch: (q: string) => void }) {
  const [text, setText] = useState(initial);
  return (
    <form
      role="search"
      className="relative mb-6"
      onSubmit={(e) => {
        e.preventDefault();
        onSearch(text.trim());
      }}
    >
      <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-fg-subtle" aria-hidden="true" />
      <label htmlFor="search-page" className="sr-only">
        Search
      </label>
      <Input id="search-page" value={text} onChange={(e) => setText(e.target.value)} placeholder="Search everything…" className="h-10 pl-9 text-[15px]" autoFocus />
    </form>
  );
}

export function SearchRoute() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const results = useUniversalSearch(q);

  const groups = ORDER.map((kind) => ({ kind, hits: (results.data?.hits ?? []).filter((h) => h.kind === kind) })).filter((g) => g.hits.length);

  return (
    <Page>
      <PageHeader title="Search" description="Projects, objectives, deliverables and memory in one place." />
      <SearchBox key={q} initial={q} onSearch={(next) => setParams(next ? { q: next } : {}, { replace: true })} />

      {!q ? (
        <EmptyState icon={<SearchIcon />} title="Search your work" description="Find a project, an objective, a deliverable's contents or something NEXUS remembers." />
      ) : results.isPending ? (
        <Skeleton className="h-40" />
      ) : results.isError ? (
        <ErrorState message={errorMessage(results.error)} onRetry={() => void results.refetch()} />
      ) : groups.length === 0 ? (
        <EmptyState title={`Nothing found for “${q}”`} description="Try fewer or different words. The last word also matches as a prefix." />
      ) : (
        groups.map((g) => (
          <Section key={g.kind} title={`${KIND_LABEL[g.kind]} (${g.hits.length})`}>
            <Card>
              <ul className="divide-y divide-line">
                {g.hits.map((h) => (
                  <li key={`${h.kind}-${h.id}`}>
                    <Link to={searchHref(h)} className="block px-3 py-2.5 hover:bg-raised/60">
                      <span className="block truncate text-[13px] font-medium text-fg">{h.title}</span>
                      {h.snippet ? (
                        <span className="mt-0.5 line-clamp-2 block text-xs text-fg-muted">
                          <Snippet text={h.snippet} />
                        </span>
                      ) : null}
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          </Section>
        ))
      )}
    </Page>
  );
}
