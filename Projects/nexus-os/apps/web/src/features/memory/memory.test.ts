import type { ContextReport, MemoryItem } from "@nexus/schemas";
import { describe, expect, it } from "vitest";
import { contextSummary, explainScore, flagsOf, parseTags, provenance, searchHref, snippetParts } from "./format";

const item = (over: Partial<MemoryItem> = {}): MemoryItem => ({
  id: "mem_1",
  scope: "project",
  project_id: "proj_1",
  content: "The client prefers British spelling.",
  summary: "",
  importance: 0.5,
  source: { kind: "agent", agent: "data_analyst", run_id: null, task_id: null, objective_id: null, tainted: false, private: false },
  tags: [],
  status: "active",
  content_hash: "h",
  access_count: 0,
  last_accessed_at: null,
  merged_into: null,
  created_at: "2026-09-29T10:00:00Z",
  updated_at: "2026-09-29T10:00:00Z",
  ...over,
});

describe("memory views", () => {
  it("says where a memory came from", () => {
    expect(provenance(item())).toBe("Proposed by the data analyst agent");
    expect(provenance(item({ source: { ...item().source, kind: "user" } }))).toBe("Written by you");
    expect(provenance(item({ source: { ...item().source, kind: "summary" } }))).toBe("Summary of older notes");
  });

  it("flags what the person should know", () => {
    expect(flagsOf(item())).toEqual([]);
    const flagged = flagsOf(
      item({ scope: "global", importance: 1, status: "pending", source: { ...item().source, tainted: true, private: true } }),
    ).map((f) => f.label);
    expect(flagged).toEqual(["All projects", "Pinned", "Suggestion", "On this device", "After outside content"]);
  });

  it("explains a score by contribution", () => {
    expect(explainScore({ semantic: 0.8, keyword: 1, recency: 1, importance: 0.5, task: 0, total: 0.735 })).toEqual([
      { label: "Meaning", share: 36 },
      { label: "Words", share: 15 },
      { label: "Recent", share: 15 },
      { label: "Importance", share: 8 },
    ]);
  });

  it("cleans typed tags", () => {
    expect(parseTags(" Design, #design ,, billing\nQ3 ")).toEqual(["design", "billing", "q3"]);
  });

  it("links every kind of search result", () => {
    expect(searchHref({ kind: "project", id: "proj_1", project_id: "proj_1" })).toBe("/projects/proj_1");
    expect(searchHref({ kind: "objective", id: "obj_1", project_id: "proj_1" })).toBe("/objectives/obj_1");
    expect(searchHref({ kind: "artifact", id: "art_1", project_id: "proj_1" })).toBe("/projects/proj_1?tab=artifacts&artifact=art_1");
    expect(searchHref({ kind: "memory", id: "mem_1", project_id: "proj_1" })).toBe("/projects/proj_1?tab=memory&memory=mem_1");
    expect(searchHref({ kind: "memory", id: "mem_2", project_id: null })).toBe("/memory?memory=mem_2");
  });

  it("highlights matches without HTML", () => {
    expect(snippetParts("… water [succulents] monthly [in] summer")).toEqual([
      { text: "… water ", hit: false },
      { text: "succulents", hit: true },
      { text: " monthly ", hit: false },
      { text: "in", hit: true },
      { text: " summer", hit: false },
    ]);
    expect(snippetParts("<b>not html</b>")).toEqual([{ text: "<b>not html</b>", hit: false }]);
  });

  it("summarises a context report", () => {
    const report: ContextReport = {
      budget_tokens: 1000,
      used_tokens: 640,
      memory_query: "q",
      notes: [],
      entries: [
        { source: "task:t1", kind: "upstream", tokens: 500, score: 1, included: true, truncated: true, reason: "", memory_id: null },
        { source: "memory:mem_1", kind: "memory", tokens: 140, score: 0.6, included: true, truncated: false, reason: "", memory_id: "mem_1" },
        { source: "memory:mem_2", kind: "memory", tokens: 900, score: 0.4, included: false, truncated: false, reason: "over", memory_id: "mem_2" },
      ],
    };
    expect(contextSummary(report)).toEqual({ included: 2, dropped: 1, cut: 1, memories: 1, percent: 64 });
  });
});
