import { describe, expect, it } from "vitest";
import {
  agentCanUse,
  clip,
  formatToolText,
  normalizeAgent,
  parseArgumentsJson,
  parseStep,
  prettyArgs,
  runDuration,
  stepHeadline,
  toolMatches,
} from "./format";

describe("agent helpers", () => {
  it("fills in defaults the API leaves out", () => {
    const a = normalizeAgent({ id: "agent_1", slug: "x", name: "X", role: "r" });
    expect(a).toMatchObject({ maxRisk: "MODERATE", maxSteps: 20, tokenBudget: 200_000, status: "idle", builtin: false, tools: [] });
  });

  it("matches exact names and prefix patterns", () => {
    expect(toolMatches("git_*", "git_status")).toBe(true);
    expect(toolMatches("git_*", "read_file")).toBe(false);
    expect(toolMatches("read_file", "read_file")).toBe(true);
    expect(agentCanUse({ tools: ["read_file", "git_*"] }, "git_log")).toBe(true);
    expect(agentCanUse({ tools: ["read_file"] }, "run_command")).toBe(false);
  });
});

describe("steps", () => {
  const raw = {
    n: 2,
    summary: "Reading the notes",
    action: { type: "tool_call", tool: "read_file", arguments: { path: "files/a.md", huge: "x".repeat(900) } },
    observation: { status: "ok", text: '{"a":1}', untrusted: true, flags: ["override_instructions"] },
    notes: ["This is your last step."],
  };

  it("parses a tool step with its observation", () => {
    const s = parseStep(raw)!;
    expect(s).toMatchObject({ n: 2, kind: "tool_call", tool: "read_file", notes: ["This is your last step."] });
    expect(s.observation).toMatchObject({ status: "ok", untrusted: true, flags: ["override_instructions"] });
    expect(stepHeadline(s)).toBe("Used read_file");
    expect(s.args[0]).toEqual(["path", "files/a.md"]);
    expect(s.args[1]![1]).toContain("more characters");
  });

  it("parses finish and question steps", () => {
    const fin = parseStep({ n: 3, summary: "s", action: { type: "finish", result: { status: "partial", summary: "Half done" } } })!;
    expect(fin).toMatchObject({ kind: "finish", resultStatus: "partial", resultSummary: "Half done" });
    expect(stepHeadline(fin)).toBe("Finished");
    const failed = parseStep({ n: 1, summary: "", action: { type: "finish", result: { status: "failed", summary: "x" } } })!;
    expect(stepHeadline(failed)).toBe("Reported it could not finish");
    const q = parseStep({ n: 1, summary: "", action: { type: "ask_human", question: "Which?" } })!;
    expect(q).toMatchObject({ kind: "ask_human", question: "Which?" });
  });

  it("survives malformed data instead of crashing", () => {
    expect(parseStep(null)).toBeNull();
    expect(parseStep({ n: 1 })).toBeNull();
    expect(parseStep({ action: { type: "mystery" } })!.kind).toBe("unknown");
    expect(prettyArgs("nope")).toEqual([]);
  });

  it("clips long text and pretty-prints JSON results only", () => {
    expect(clip("abcdef", 3)).toBe("abc… (3 more characters)");
    expect(formatToolText('{"a":1}')).toBe('{\n  "a": 1\n}');
    expect(formatToolText("plain words")).toBe("plain words");
    expect(formatToolText("{broken")).toBe("{broken");
  });
});

describe("editing arguments", () => {
  it("accepts a JSON object", () => {
    expect(parseArgumentsJson('{"path": "files/b.txt"}')).toEqual({ ok: true, value: { path: "files/b.txt" } });
  });
  it("explains what is wrong", () => {
    expect(parseArgumentsJson("{oops")).toMatchObject({ ok: false });
    expect(parseArgumentsJson("[1,2]")).toEqual({ ok: false, error: expect.stringContaining("JSON object") });
    expect(parseArgumentsJson("42")).toMatchObject({ ok: false });
  });
});

describe("run timing", () => {
  it("measures finished and running runs", () => {
    const start = "2026-09-29T10:00:00Z";
    expect(runDuration({ started_at: start, finished_at: "2026-09-29T10:00:30Z" })).toBe(30);
    expect(runDuration({ started_at: start, finished_at: null }, new Date("2026-09-29T10:01:00Z"))).toBe(60);
  });
});
