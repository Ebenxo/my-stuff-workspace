import type { EventRecord } from "@nexus/schemas";
import { describe, expect, it } from "vitest";
import { describeEvent } from "../events/describe";
import { dayLabel, dueLabel, duePresets, eventHref, fromLocalInput, groupByDay, parseQuickCapture, timelineHref, toLocalInput } from "./format";

// Local wall-clock times, so the tests hold in any timezone.
const local = (y: number, mo: number, d: number, h = 0, mi = 0) => new Date(y, mo - 1, d, h, mi);
const now = local(2026, 10, 2, 14, 0); // a Friday

const ev = (type: string, extra: Partial<EventRecord> = {}): EventRecord => ({
  seq: 1,
  id: "e",
  ts: now.toISOString(),
  type,
  actor: "user",
  payload: {},
  prev_hash: "",
  hash: "",
  ...extra,
});

describe("due dates", () => {
  it("says when, and flags what has passed", () => {
    expect(dueLabel(local(2026, 10, 2, 18).toISOString(), now)).toEqual({ text: "Today 18:00", tone: "warning" });
    expect(dueLabel(local(2026, 10, 3, 9).toISOString(), now)).toEqual({ text: "Tomorrow 09:00", tone: "neutral" });
    expect(dueLabel(local(2026, 10, 5, 9).toISOString(), now).text).toMatch(/^Monday 09:00$/);
    expect(dueLabel(local(2026, 10, 2, 9).toISOString(), now)).toEqual({ text: "Overdue · Today 09:00", tone: "danger" });
    expect(dueLabel(local(2026, 10, 1, 9).toISOString(), now).text).toBe("Overdue · Yesterday 09:00");
    expect(dueLabel(local(2026, 11, 20, 9).toISOString(), now).text).toMatch(/20 Nov.* 09:00|Nov 20.* 09:00/);
  });

  it("offers this evening, tomorrow morning and next Monday", () => {
    const [later, tomorrow, monday] = duePresets(now);
    expect(later).toMatchObject({ label: "This evening", at: local(2026, 10, 2, 18) });
    expect(tomorrow).toMatchObject({ label: "Tomorrow morning", at: local(2026, 10, 3, 9) });
    expect(monday).toMatchObject({ label: "Next Monday", at: local(2026, 10, 5, 9) });
    expect(duePresets(local(2026, 10, 2, 19, 30))[0]).toMatchObject({ label: "In an hour", at: local(2026, 10, 2, 20, 30) });
    expect(duePresets(local(2026, 10, 5, 8))[2]?.at).toEqual(local(2026, 10, 12, 9)); // on a Monday: the next one
  });

  it("round-trips the datetime-local input as an instant", () => {
    const iso = local(2026, 10, 3, 9, 5).toISOString();
    expect(toLocalInput(iso)).toBe("2026-10-03T09:05");
    expect(fromLocalInput("2026-10-03T09:05")).toBe(iso);
    expect(fromLocalInput("")).toBeNull();
    expect(fromLocalInput("not a date")).toBeNull();
    expect(toLocalInput(null)).toBe("");
  });
});

describe("quick capture", () => {
  it("reads a kind prefix, and treats anything else as an idea", () => {
    expect(parseQuickCapture("todo: buy soil")).toEqual({ kind: "todo", text: "buy soil" });
    expect(parseQuickCapture("To-do:call Sam")).toEqual({ kind: "todo", text: "call Sam" });
    expect(parseQuickCapture("NOTE: tea at 4")).toEqual({ kind: "note", text: "tea at 4" });
    expect(parseQuickCapture("idea: a podcast")).toEqual({ kind: "idea", text: "a podcast" });
    expect(parseQuickCapture("a thought: with a colon")).toEqual({ kind: "idea", text: "a thought: with a colon" });
  });
});

describe("history", () => {
  it("groups by local day, newest first", () => {
    const events = [
      ev("A", { seq: 3, ts: local(2026, 10, 2, 9).toISOString() }),
      ev("B", { seq: 2, ts: local(2026, 10, 1, 22).toISOString() }),
      ev("C", { seq: 1, ts: local(2026, 9, 28, 8).toISOString() }),
    ];
    expect(groupByDay(events, now).map((g) => [g.day, g.events.map((e) => e.seq)])).toEqual([
      ["Today", [3]],
      ["Yesterday", [2]],
      [dayLabel(local(2026, 9, 28).toISOString(), now), [1]],
    ]);
    expect(dayLabel(local(2025, 12, 31).toISOString(), now)).toMatch(/2025/);
  });

  it("links each entry to what it is about", () => {
    expect(eventHref(ev("IDEA_CREATED", { payload: { idea_id: "idea_1" } }))).toBe("/ideas?idea=idea_1");
    expect(eventHref(ev("IDEA_DELETED", { payload: { idea_id: "idea_1" } }))).toBe("/ideas");
    expect(eventHref(ev("APPROVAL_REQUIRED", { run_id: "run_1" }))).toBe("/approvals");
    expect(eventHref(ev("TASK_STARTED", { objective_id: "obj_1", run_id: "run_1" }))).toBe("/objectives/obj_1");
    expect(eventHref(ev("AGENT_COMPLETED", { run_id: "run_1" }))).toBe("/runs/run_1");
    expect(eventHref(ev("WORKFLOW_WAITING", { payload: { workflow_id: "wf_1", workflow_run_id: "wfr_1" } }))).toBe("/workflow-runs/wfr_1");
    expect(eventHref(ev("SCHEDULE_CREATED", { payload: { workflow_id: "wf_1" } }))).toBe("/workflows/wf_1");
    expect(eventHref(ev("PROJECT_CREATED", { project_id: "proj_1" }))).toBe("/projects/proj_1");
    expect(eventHref(ev("SYSTEM_STARTED"))).toBeUndefined();
  });

  it("links timeline items", () => {
    expect(timelineHref({ kind: "schedule", id: "sch_1", ref_id: "wf_1" })).toBe("/workflows/wf_1");
    expect(timelineHref({ kind: "approval", id: "appr_1", ref_id: "run_1" })).toBe("/approvals");
    expect(timelineHref({ kind: "idea", id: "idea_1" })).toBe("/ideas?idea=idea_1");
    expect(timelineHref({ kind: "workflow_run", id: "wfr_1" })).toBe("/workflow-runs/wfr_1");
  });

  it("describes idea events in plain words", () => {
    const p = (payload: Record<string, unknown>) => describeEvent(ev("IDEA_UPDATED", { payload: { kind: "todo", text: "Buy soil", ...payload } }));
    expect(describeEvent(ev("IDEA_CREATED", { payload: { kind: "note", text: "Tea at 4" } })).text).toBe("Note added: Tea at 4");
    expect(p({ changed: ["done_at", "status"], status: "done" })).toEqual({ text: "To-do done: Buy soil", tone: "success" });
    expect(p({ changed: ["done_at", "status"], status: "open" }).text).toBe("To-do reopened: Buy soil");
    expect(p({ changed: ["pinned"], pinned: true }).text).toBe("To-do pinned: Buy soil");
    expect(p({ changed: ["text"] }).text).toBe("To-do edited: Buy soil");
    expect(p({ changed: ["objective_id", "status"], objective_id: "obj_1" }).text).toBe("Started as an objective: Buy soil");
    expect(describeEvent(ev("IDEA_DUE", { payload: { kind: "todo", text: "Buy soil" } }))).toEqual({ text: "To-do due: Buy soil", tone: "warning" });
  });
});
