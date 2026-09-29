import type { EventRecord } from "@nexus/schemas";
import { describe, expect, it } from "vitest";
import { describeEvent, isErrorEvent } from "./describe";

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
    expect(describeEvent({ ...base, type: "TASK_COMPLETED" })).toEqual({ text: "Task completed", tone: "success" });
    expect(describeEvent({ ...base, type: "APPROVAL_REQUIRED" }).tone).toBe("warning");
    expect(describeEvent({ ...base, type: "TOOL_DENIED" }).tone).toBe("danger");
  });

  it("classifies error events", () => {
    expect(isErrorEvent({ ...base, type: "TASK_FAILED" })).toBe(true);
    expect(isErrorEvent({ ...base, type: "SECURITY_FLAG" })).toBe(true);
    expect(isErrorEvent({ ...base, type: "TASK_COMPLETED" })).toBe(false);
  });

  it("never renders payload fields it does not know", () => {
    const view = describeEvent({ ...base, type: "TASK_CREATED", payload: { secret_reasoning: "should not appear" } });
    expect(view.text).not.toContain("should not appear");
  });
});
