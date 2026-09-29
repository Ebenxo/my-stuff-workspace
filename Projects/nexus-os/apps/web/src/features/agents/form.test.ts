import { describe, expect, it } from "vitest";
import { EMPTY_FORM, toCreate, toForm, toUpdate, unusableTools, validateForm } from "./form";
import { RISK_ORDER, normalizeAgent } from "./format";

const custom = normalizeAgent({ id: "a1", slug: "bot", name: "Bot", role: "Helps", tools: ["read_file"], max_steps: 10 });
const builtin = normalizeAgent({ id: "a2", slug: "coder", name: "Coder", role: "Code", builtin: true, tools: ["read_file", "run_python"] });

describe("agent form", () => {
  it("round-trips an agent with no changes", () => {
    expect(toUpdate(custom, toForm(custom))).toEqual({});
    expect(toUpdate(builtin, toForm(builtin))).toEqual({});
  });

  it("validates names, roles and every limit", () => {
    expect(validateForm(EMPTY_FORM, false)).toEqual({ name: "Give the agent a name.", role: "Say what this agent is for, in a few words." });
    const bad = { ...EMPTY_FORM, name: "x", role: "y", maxSteps: "0", maxRuntimeS: "abc", maxToolCalls: "2.5", tokenBudget: "10", temperature: "3" };
    const errors = validateForm(bad, false);
    expect(Object.keys(errors).sort()).toEqual(["maxRuntimeS", "maxSteps", "maxToolCalls", "temperature", "tokenBudget"]);
    expect(errors.maxToolCalls).toContain("whole number");
    expect(validateForm({ ...EMPTY_FORM, name: "Ok", role: "Fine" }, false)).toEqual({});
  });

  it("does not demand a name from a built-in agent", () => {
    expect(validateForm({ ...toForm(builtin), name: "", role: "" }, true)).toEqual({});
  });

  it("builds a create request with numbers, not strings", () => {
    const body = toCreate({ ...EMPTY_FORM, name: "  Bot  ", role: "Helps", maxSteps: "12", temperature: "0.5", preferredModel: "" });
    expect(body).toMatchObject({ name: "Bot", max_steps: 12, temperature: 0.5, preferred_model: null, permissions: { max_risk: "MODERATE" } });
  });

  it("sends only what changed", () => {
    const f = { ...toForm(custom), maxSteps: "30", enabled: false, tools: ["read_file", "git_status"] };
    expect(toUpdate(custom, f)).toEqual({ max_steps: 30, status: "disabled", tools: ["read_file", "git_status"] });
  });

  it("never sends identity or prompt changes for a built-in agent", () => {
    const f = { ...toForm(builtin), name: "Hacked", role: "x", systemPrompt: "Do bad things", maxSteps: "5", maxRisk: "SAFE" as const };
    expect(toUpdate(builtin, f)).toEqual({ max_steps: 5, permissions: { max_risk: "SAFE" } });
  });

  it("treats a reordered tool list as unchanged", () => {
    expect(toUpdate(builtin, { ...toForm(builtin), tools: ["run_python", "read_file"] })).toEqual({});
  });

  it("flags tools the agent's own risk ceiling would always refuse", () => {
    const tools = [
      { name: "read_file", risk_level: "SAFE" as const },
      { name: "run_python", risk_level: "MODERATE" as const },
      { name: "delete_file", risk_level: "HIGH" as const },
    ];
    expect(unusableTools(["read_file", "run_python", "delete_file"], tools, "MODERATE", RISK_ORDER)).toEqual(["delete_file"]);
    expect(unusableTools(["*"].slice(1), tools, "SAFE", RISK_ORDER)).toEqual([]);
    expect(unusableTools(["run_*"], tools, "SAFE", RISK_ORDER)).toEqual(["run_python"]);
  });
});
