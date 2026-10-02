import type { Objective } from "@nexus/schemas";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@nexus/ui";
import { Check, X } from "lucide-react";
import { Link } from "react-router";
import { resultOf } from "./format";

const VERDICT = {
  PASS: { label: "Verified", tone: "success" },
  PARTIAL: { label: "Partly met", tone: "warning" },
  FAIL: { label: "Not met", tone: "danger" },
} as const;

/** What the Verifier concluded, criterion by criterion, and what was delivered. */
export function ResultCard({ objective }: { objective: Objective }) {
  const result = resultOf(objective);
  if (!result) return null;
  const verdict = result.verdict ? VERDICT[result.verdict] : null;
  return (
    <Card className={verdict?.tone === "success" ? "border-success/40" : verdict?.tone === "danger" ? "border-danger/40" : undefined}>
      <CardHeader className="flex flex-row flex-wrap items-center gap-2">
        <CardTitle>Result</CardTitle>
        {verdict ? <Badge tone={verdict.tone}>{verdict.label}</Badge> : null}
      </CardHeader>
      <CardContent className="space-y-4 text-[13px]">
        {result.summary ? <p className="whitespace-pre-wrap text-sm text-fg">{result.summary}</p> : null}
        {result.criteria.length ? (
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-fg-subtle">Checked against</p>
            <ul className="mt-1.5 space-y-1.5">
              {result.criteria.map((c, n) => (
                <li key={n} className="flex gap-2">
                  {c.met ? (
                    <Check className="mt-0.5 size-4 shrink-0 text-success" aria-label="Met" />
                  ) : (
                    <X className="mt-0.5 size-4 shrink-0 text-danger" aria-label="Not met" />
                  )}
                  <span>
                    {c.criterion}
                    {c.evidence ? <span className="block text-xs text-fg-subtle">{c.evidence}</span> : null}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {result.missing.length ? (
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-fg-subtle">Still missing</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-warning">
              {result.missing.map((m) => (
                <li key={m}>
                  <span className="text-fg">{m}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {result.artifacts.length ? (
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-fg-subtle">Deliverables</p>
            <ul className="mt-1.5 flex flex-wrap gap-2">
              {result.artifacts.map((a) => (
                <li key={a.id}>
                  <Link
                    to={`/projects/${objective.project_id}?tab=artifacts&artifact=${a.id}`}
                    className="inline-block rounded-md border border-line-strong bg-raised px-2 py-1 hover:bg-overlay"
                  >
                    {a.name} <span className="text-fg-subtle">v{a.version}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
