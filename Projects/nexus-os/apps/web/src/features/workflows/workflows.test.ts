import type { WorkflowDefinition } from "@nexus/schemas";
import { describe, expect, it } from "vitest";
import { addAfter, addNode, connect, formatSeconds, placeNear, inputDefaults, inputValues, issuesByNode, nextNodeId, removeNode, summarize, updateNode } from "./model";

const base: WorkflowDefinition = {
  inputs: [],
  nodes: [{ id: "start", type: "trigger", label: "Start", config: {}, position: { x: 0, y: 0 }, continue_on_error: false }],
  edges: [],
};

describe("workflow editing", () => {
  it("adds steps with fresh ids and sensible defaults", () => {
    const one = addNode(base, "agent", { x: 200, y: 0 });
    expect(one.id).toBe("agent_1");
    const two = addNode(one.def, "agent", { x: 400, y: 0 });
    expect(two.id).toBe("agent_2");
    expect(two.def.nodes?.find((n) => n.id === "agent_2")?.config).toEqual({ agent: "writer", prompt: "" });
    expect(nextNodeId("tool", two.def.nodes ?? [])).toBe("tool_1");
  });

  it("adds a step after the selected one, connected and placed below it", () => {
    const first = addAfter(base, "approval", "start");
    expect(first.def.edges).toEqual([{ id: "start-approval_1", source: "start", target: "approval_1" }]);
    expect(first.def.nodes?.[1]?.position).toEqual({ x: 0, y: 150 });
    const second = addAfter(first.def, "tool", "approval_1"); // after an approval: its 'yes' path
    expect(second.def.edges?.at(-1)).toEqual({ id: "approval_1-tool_1-true", source: "approval_1", target: "tool_1", branch: "true" });
    const sibling = addAfter(second.def, "output", "approval_1"); // the spot is taken: placed beside it
    expect(sibling.def.nodes?.find((n) => n.id === "output_1")?.position).toEqual({ x: 260, y: 300 });
    const loose = addAfter(second.def, "delay", undefined);
    expect(loose.def.edges).toHaveLength(2);
    expect(placeNear([], 10, 20)).toEqual({ x: 10, y: 20 });
  });

  it("connects steps and refuses what cannot work", () => {
    let d = addNode(base, "condition", { x: 1, y: 1 }).def;
    d = addNode(d, "output", { x: 2, y: 2 }).def;
    d = addNode(d, "output", { x: 3, y: 3 }).def;
    const a = connect(d, "start", "condition_1");
    expect("def" in a).toBe(true);
    if (!("def" in a)) return;
    const yes = connect(a.def, "condition_1", "output_1", "true");
    expect("def" in yes && yes.def.edges?.at(-1)).toEqual({ id: "condition_1-output_1-true", source: "condition_1", target: "output_1", branch: "true" });
    if (!("def" in yes)) return;
    expect(connect(yes.def, "condition_1", "output_1", "true")).toEqual({ error: "Already connected." });
    expect(connect(yes.def, "output_1", "start")).toEqual({ error: "Nothing can lead into the start." });
    expect(connect(yes.def, "output_1", "output_1")).toEqual({ error: "A step cannot connect to itself." });
    expect(connect(yes.def, "output_1", "condition_1")).toEqual({ error: "That would make a loop. Use a Loop step to repeat work." });
    // a plain step's connection never carries a branch, even if a handle said so
    const plain = connect(yes.def, "start", "output_2", "false");
    expect("def" in plain && plain.def.edges?.at(-1)?.branch).toBeUndefined();
  });

  it("removes a step and its connections, but never the start", () => {
    const d = addNode(base, "delay", { x: 0, y: 0 }).def;
    const linked = connect(d, "start", "delay_1");
    if (!("def" in linked)) throw new Error("connect failed");
    const gone = removeNode(linked.def, "delay_1");
    expect(gone.nodes?.map((n) => n.id)).toEqual(["start"]);
    expect(gone.edges).toEqual([]);
    expect(removeNode(gone, "start").nodes).toHaveLength(1);
    expect(updateNode(d, "delay_1", { label: "Wait" }).nodes?.[1]?.label).toBe("Wait");
  });

  it("summarises steps for their cards", () => {
    const n = (type: never, config: Record<string, unknown>) => ({ id: "x", type, config });
    expect(summarize(n("agent" as never, { agent: "data_analyst", prompt: "Sum it" }))).toBe("data analyst: Sum it");
    expect(summarize(n("output" as never, { values: { a: "1", b: "2" } }))).toBe("a, b");
    expect(summarize(n("delay" as never, { seconds: 5400 }))).toBe("wait 1.5 h");
    expect(summarize(n("condition" as never, {}))).toBe("no condition yet");
    expect(formatSeconds(45)).toBe("45s");
    expect(formatSeconds(600)).toBe("10 min");
  });

  it("groups validation issues by step", () => {
    const { byNode, general } = issuesByNode({ ok: false, issues: [{ node: "a", message: "x" }, { node: "a", message: "y" }, { message: "z" }] });
    expect(byNode.get("a")).toEqual(["x", "y"]);
    expect(general).toEqual(["z"]);
  });

  it("turns the inputs form into API values", () => {
    const inputs = [
      { name: "topic", type: "text" as const, required: true },
      { name: "count", type: "number" as const, required: false, default: 3 },
      { name: "urgent", type: "boolean" as const, required: false },
    ];
    const form = inputDefaults(inputs);
    expect(form).toEqual({ topic: "", count: "3", urgent: false });
    expect(inputValues(inputs, { ...form, topic: "tea", count: "7" })).toEqual({ topic: "tea", count: 7, urgent: false });
    expect(inputValues(inputs, { ...form, count: " " })).toEqual({ urgent: false });
  });
});
