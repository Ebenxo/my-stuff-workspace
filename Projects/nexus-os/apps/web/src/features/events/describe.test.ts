import type { EventRecord } from "@nexus/schemas";
import { describe, expect, it } from "vitest";
import { describeEvent, isActivityEvent, isErrorEvent } from "./describe";

const base: EventRecord = {
  seq: 1,
  id: "e",
  ts: "2026-01-01T00:00:00Z",
  type: "X",
  actor: "system",
  payload: {},
  prev_hash: "",
  hash: "",
};

describe("describeEvent", () => {
  it("summarises known events", () => {
    expect(describeEvent({ ...base, type: "PROJECT_CREATED", payload: { name: "Site" } })).toEqual({
      text: "Project created: Site",
      tone: "success",
    });
    expect(describeEvent({ ...base, type: "SETTINGS_UPDATED", payload: { changed: ["a", "b"] } }).text).toBe("Settings updated (a, b)");
  });

  it("falls back to a readable label and infers tone", () => {
    expect(describeEvent({ ...base, type: "EXPORT_COMPLETED" })).toEqual({ text: "Export completed", tone: "success" });
    expect(describeEvent({ ...base, type: "APPROVAL_REQUIRED" }).tone).toBe("warning");
    expect(describeEvent({ ...base, type: "TOOL_DENIED" }).tone).toBe("danger");
  });

  it("describes objectives, tasks and hand-offs in plain words", () => {
    const d = (type: string, payload: Record<string, unknown>) => describeEvent({ ...base, type, payload });
    expect(d("PLAN_CREATED", { tasks: 4 })).toEqual({ text: "Plan ready: 4 tasks", tone: "info" });
    expect(d("TASK_STARTED", { key: "t1", title: "Research", agent: "researcher" }).text).toBe("Researcher started “Research”");
    expect(d("TASK_BLOCKED", { key: "t2" })).toEqual({ text: "Task t2 needs you", tone: "warning" });
    expect(d("REVIEW_COMPLETED", { title: "Draft", verdict: "revise" })).toEqual({ text: "Critic asked for changes to “Draft”", tone: "warning" });
    expect(d("VERIFICATION_COMPLETED", { verdict: "PASS", summary: "All met" })).toEqual({ text: "Verifier: PASS, All met", tone: "success" });
    expect(d("OBJECTIVE_COMPLETED", { verdict: "PASS" }).text).toBe("Objective complete and verified");
    expect(d("AGENT_MESSAGE", { sender: "orchestrator", recipient: "writer", type: "TASK_REQUEST", payload: { title: "Write it" } }).text).toBe(
      "NEXUS assigned writer: Write it",
    );
    expect(d("AGENT_MESSAGE", { sender: "writer", recipient: "user", type: "QUESTION", payload: { question: "Which tone?" } })).toEqual({
      text: "Writer asked you: Which tone?",
      tone: "warning",
    });
    // a question from a lone run keeps its original wording
    expect(d("AGENT_MESSAGE", { kind: "question", text: "Which file?" }).text).toBe("Agent asks: Which file?");
  });

  it("classifies error events", () => {
    expect(isErrorEvent({ ...base, type: "TASK_FAILED" })).toBe(true);
    expect(isErrorEvent({ ...base, type: "SECURITY_FLAG" })).toBe(true);
    expect(isErrorEvent({ ...base, type: "TASK_COMPLETED" })).toBe(false);
  });

  it("describes agent, tool and approval activity in plain words", () => {
    const d = (type: string, payload: Record<string, unknown>) => describeEvent({ ...base, type, payload });
    expect(d("AGENT_STARTED", { name: "Writer", prompt: "Write a brief" })).toEqual({ text: "Writer started: Write a brief", tone: "accent" });
    expect(d("AGENT_STEP", { n: 2, summary: "Reading the file" }).text).toBe("Step 2: Reading the file");
    expect(d("AGENT_FAILED", { message: "Stopped after 3 steps" })).toEqual({ text: "Agent stopped: Stopped after 3 steps", tone: "danger" });
    expect(d("AGENT_INTERRUPTED", {}).tone).toBe("warning");
    expect(d("TOOL_CALLED", { tool: "write_file", risk: "MODERATE" }).text).toBe("Tool: write_file (moderate risk)");
    expect(d("TOOL_DENIED", { tool: "run_command", reason: "blocked" }).text).toBe("run_command was refused: blocked");
    expect(d("SECURITY_FLAG", { source: "file:notes.txt" }).text).toContain("file:notes.txt");
    expect(d("APPROVAL_REQUIRED", { tool: "delete_file" })).toEqual({ text: "Approval needed: delete_file", tone: "warning" });
    expect(d("APPROVAL_GRANTED", { tool: "delete_file" }).tone).toBe("success");
    expect(d("ARTIFACT_UPDATED", { name: "report.md", version: 3 }).text).toBe("Updated report.md to v3");
    expect(d("FILE_WRITTEN", { path: "files/a.md", created: true }).text).toBe("Created files/a.md");
    expect(d("FILE_DELETED", { path: "files/a.md" }).text).toBe("Moved files/a.md to trash");
  });

  it("does not print the clipboard text into the activity feed", () => {
    const view = describeEvent({ ...base, type: "CLIPBOARD_REQUEST", payload: { text: "secret-looking text", label: "Copy summary" } });
    expect(view.text).toBe("Copy offered: Copy summary");
    expect(view.text).not.toContain("secret-looking");
  });

  it("keeps bookkeeping out of activity feeds (it stays in the raw event log)", () => {
    expect(isActivityEvent({ ...base, type: "NOTIFICATION_CREATED" })).toBe(false);
    expect(isActivityEvent({ ...base, type: "USAGE_RECORDED" })).toBe(false);
    expect(isActivityEvent({ ...base, type: "APPROVAL_REQUIRED" })).toBe(true);
    expect(isActivityEvent({ ...base, type: "AGENT_COMPLETED" })).toBe(true);
  });

  it("never renders payload fields it does not know", () => {
    const view = describeEvent({ ...base, type: "TASK_CREATED", payload: { secret_reasoning: "should not appear" } });
    expect(view.text).not.toContain("should not appear");
  });
});
