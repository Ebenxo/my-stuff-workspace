import type { ContextReport } from "@nexus/schemas";
import { Badge, Card, CardContent } from "@nexus/ui";
import { Link } from "react-router";
import { contextSummary } from "./format";

const KIND: Record<string, string> = { upstream: "Earlier task", memory: "Memory", given: "Provided" };

/** What the agent was given besides its task, and why: the stored ContextReport. */
export function ContextPanel({ report, projectId }: { report: ContextReport; projectId?: string | null }) {
  const s = contextSummary(report);
  const entries = report.entries ?? [];
  const notes = report.notes ?? [];
  return (
    <Card>
      <CardContent className="space-y-3 pt-4 text-[13px]">
        <div>
          <div className="flex items-center justify-between text-xs text-fg-muted">
            <span>
              {s.included} {s.included === 1 ? "item" : "items"} given
              {s.dropped ? `, ${s.dropped} left out` : ""}
              {s.cut ? `, ${s.cut} shortened` : ""}
            </span>
            <span className="font-mono">
              {report.used_tokens.toLocaleString()} / {report.budget_tokens.toLocaleString()} tokens
            </span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-raised" role="meter" aria-label="Context budget used" aria-valuenow={s.percent} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-full rounded-full bg-accent" style={{ width: `${s.percent}%` }} />
          </div>
        </div>
        {entries.length === 0 ? (
          <p className="text-fg-muted">
            Only the task itself.{notes.length ? ` ${notes.join(" ")}` : " Nothing remembered was relevant."}
          </p>
        ) : (
          <ul className="space-y-1.5" aria-label="Context given to the agent">
            {entries.map((e) => (
              <li key={e.source} className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                <Badge tone={e.included ? (e.truncated ? "warning" : "success") : "neutral"}>
                  {e.included ? (e.truncated ? "Shortened" : "Given") : "Left out"}
                </Badge>
                <span className="text-fg-muted">{KIND[e.kind] ?? e.kind}</span>
                {e.memory_id && projectId ? (
                  <Link to={`/projects/${projectId}?tab=memory&memory=${e.memory_id}`} className="font-mono text-xs text-accent-text hover:underline">
                    {e.source}
                  </Link>
                ) : (
                  <span className="font-mono text-xs text-fg-subtle">{e.source}</span>
                )}
                <span className="basis-full text-xs text-fg-subtle sm:basis-auto">
                  {e.reason} · {e.tokens.toLocaleString()} tokens
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
