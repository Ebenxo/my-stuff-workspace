import type { ContextReport, MemoryItem, ScoreBreakdown, SearchHit } from "@nexus/schemas";

/** Who or what a memory came from, in the words the person sees next to it. */
export function provenance(item: Pick<MemoryItem, "source">): string {
  const s = item.source;
  switch (s.kind) {
    case "user":
      return "Written by you";
    case "agent":
      return s.agent ? `Proposed by the ${s.agent.replaceAll("_", " ")} agent` : "Proposed by an agent";
    case "objective":
      return "Outcome of an objective";
    case "summary":
      return "Summary of older notes";
  }
}

export interface MemoryFlag {
  label: string;
  tone: "neutral" | "info" | "warning" | "accent" | "success";
  hint: string;
}

export function flagsOf(item: MemoryItem): MemoryFlag[] {
  const flags: MemoryFlag[] = [];
  if (item.scope === "global") flags.push({ label: "All projects", tone: "info", hint: "Offered to agents in every project." });
  if (item.importance >= 1) flags.push({ label: "Pinned", tone: "accent", hint: "Always given to this project's agents." });
  if (item.status === "pending") flags.push({ label: "Suggestion", tone: "warning", hint: "Not used until you keep it." });
  if (item.source.private) flags.push({ label: "On this device", tone: "neutral", hint: "Only recalled into private runs." });
  if (item.source.tainted)
    flags.push({
      label: "After outside content",
      tone: "warning",
      hint: "Written after the agent read a web page or file. Check it before relying on it.",
    });
  return flags;
}

export const SCORE_PARTS: { key: keyof Omit<ScoreBreakdown, "total">; label: string; weight: number }[] = [
  { key: "semantic", label: "Meaning", weight: 0.45 },
  { key: "keyword", label: "Words", weight: 0.15 },
  { key: "recency", label: "Recent", weight: 0.15 },
  { key: "importance", label: "Importance", weight: 0.15 },
  { key: "task", label: "Same work", weight: 0.1 },
];

/** Each part's contribution to the total, largest first, for a compact "why" line. */
export function explainScore(score: ScoreBreakdown): { label: string; share: number }[] {
  return SCORE_PARTS.map((p) => ({ label: p.label, share: Math.round(score[p.key] * p.weight * 100) }))
    .filter((p) => p.share > 0)
    .sort((a, b) => b.share - a.share);
}

/** Tags typed as "a, b ,c" (or with #) become a clean, unique list. */
export function parseTags(text: string): string[] {
  const seen = new Set<string>();
  for (const raw of text.split(/[,\n]/)) {
    const tag = raw.trim().replace(/^#/, "").toLowerCase().slice(0, 40);
    if (tag) seen.add(tag);
  }
  return [...seen].slice(0, 12);
}

export function searchHref(hit: Pick<SearchHit, "kind" | "id" | "project_id">): string {
  switch (hit.kind) {
    case "project":
      return `/projects/${hit.id}`;
    case "objective":
      return `/objectives/${hit.id}`;
    case "artifact":
      return `/projects/${hit.project_id}?tab=artifacts&artifact=${hit.id}`;
    case "memory":
      return hit.project_id ? `/projects/${hit.project_id}?tab=memory&memory=${hit.id}` : `/memory?memory=${hit.id}`;
  }
}

export const KIND_LABEL: Record<SearchHit["kind"], string> = {
  project: "Projects",
  objective: "Objectives",
  artifact: "Deliverables",
  memory: "Memory",
};

/** Split an FTS snippet ("… [match] …") into plain and highlighted parts, without using HTML. */
export function snippetParts(snippet: string): { text: string; hit: boolean }[] {
  const parts: { text: string; hit: boolean }[] = [];
  const re = /\[([^\]]*)\]/g;
  let last = 0;
  for (let m = re.exec(snippet); m; m = re.exec(snippet)) {
    if (m.index > last) parts.push({ text: snippet.slice(last, m.index), hit: false });
    parts.push({ text: m[1] ?? "", hit: true });
    last = m.index + m[0].length;
  }
  if (last < snippet.length) parts.push({ text: snippet.slice(last), hit: false });
  return parts;
}

export function contextSummary(report: ContextReport) {
  const entries = report.entries ?? [];
  const included = entries.filter((e) => e.included);
  return {
    included: included.length,
    dropped: entries.length - included.length,
    cut: included.filter((e) => e.truncated).length,
    memories: included.filter((e) => e.kind === "memory").length,
    percent: report.budget_tokens ? Math.min(100, Math.round((report.used_tokens / report.budget_tokens) * 100)) : 0,
  };
}
