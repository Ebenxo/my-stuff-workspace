import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router";
import { describeEvent } from "../features/events/describe";
import { jsonResponse, renderWithProviders } from "../test/render";
import { WorkflowEditorRoute } from "./WorkflowEditor";
import { WorkflowRunRoute } from "./WorkflowRun";

const GET = vi.fn();
const POST = vi.fn();
const PUT = vi.fn();
vi.mock("../lib/api", () => ({
  api: { GET: (...a: unknown[]) => GET(...a), POST: (...a: unknown[]) => POST(...a), PUT: (...a: unknown[]) => PUT(...a), PATCH: vi.fn(), DELETE: vi.fn() },
  runtimeConfig: { baseUrl: "", token: undefined },
}));

const definition = {
  inputs: [{ name: "topic", type: "text", required: true, description: "" }],
  nodes: [
    { id: "start", type: "trigger", label: "Start", config: {}, position: { x: 0, y: 0 }, continue_on_error: false },
    { id: "gate", type: "approval", label: "Check", config: { message: "Publish?" }, position: { x: 260, y: 0 }, continue_on_error: false },
    { id: "out", type: "output", label: "Result", config: { values: { ok: "true" } }, position: { x: 520, y: 0 }, continue_on_error: false },
  ],
  edges: [
    { id: "start-gate", source: "start", target: "gate" },
    { id: "gate-out-true", source: "gate", target: "out", branch: "true" },
  ],
};
const workflow = {
  id: "wf_1",
  project_id: "proj_1",
  name: "Publisher",
  description: "",
  version: 3,
  enabled: true,
  definition,
  created_at: "2026-09-29T10:00:00Z",
  updated_at: "2026-09-29T10:00:00Z",
};
const state = (status: string, extra: object = {}) => ({ status, output: null, error: null, started_at: null, finished_at: null, run_id: null, child_run_id: null, resume: false, approval_id: null, attempts: 0, ...extra });

function serve(validation = { ok: true, issues: [] as { node?: string; message: string }[] }) {
  GET.mockImplementation((path: string) => {
    switch (path) {
      case "/api/workflows/{workflow_id}":
        return Promise.resolve(jsonResponse(workflow));
      case "/api/projects/{project_id}":
        return Promise.resolve(jsonResponse({ id: "proj_1", name: "Site", status: "active", settings: {} }));
      case "/api/workflow-runs/{run_id}":
        return Promise.resolve(
          jsonResponse({
            name: "Publisher",
            definition,
            run: {
              id: "wfr_1",
              workflow_id: "wf_1",
              workflow_version: 3,
              project_id: "proj_1",
              status: "WAITING",
              unattended: true,
              schedule_id: "sch_1",
              parent_run_id: null,
              depth: 0,
              inputs: { topic: "tea" },
              outputs: {},
              node_states: { start: state("COMPLETED"), gate: state("WAITING", { output: { message: "Publish the tea post?" } }), out: state("PENDING") },
              error: null,
              started_at: "2026-09-29T10:00:00Z",
              finished_at: null,
            },
          }),
        );
      default:
        return Promise.resolve(jsonResponse([]));
    }
  });
  POST.mockImplementation((path: string) =>
    Promise.resolve(path === "/api/workflows/validate" ? jsonResponse(validation) : jsonResponse({ ...workflow })),
  );
}

describe("Workflow editor", () => {
  beforeEach(() => {
    for (const m of [GET, POST, PUT]) m.mockReset();
  });

  it("adds a step, marks the draft unsaved and saves it as the whole definition", async () => {
    serve();
    PUT.mockResolvedValue(jsonResponse({ ...workflow, version: 4 }));
    renderWithProviders(
      <Routes>
        <Route path="/workflows/:workflowId" element={<WorkflowEditorRoute />} />
      </Routes>,
      { route: "/workflows/wf_1" },
    );
    expect(await screen.findByDisplayValue("Publisher")).toBeInTheDocument();
    expect(await screen.findByText("Ready to run.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Run$/ })).toBeEnabled();
    await userEvent.click(within(screen.getByRole("toolbar", { name: "Add a step" })).getByRole("button", { name: /Delay/ }));
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Run$/ })).toBeDisabled(); // save first
    expect(screen.getByLabelText("Wait (seconds)")).toHaveValue(60); // the new step is selected
    await userEvent.click(screen.getByRole("button", { name: /Save/ }));
    await waitFor(() => expect(PUT).toHaveBeenCalled());
    const body = PUT.mock.calls[0]![1].body;
    expect(body.definition.nodes.map((n: { id: string }) => n.id)).toEqual(["start", "gate", "out", "delay_1"]);
  });

  it("lists what must be fixed before a run", async () => {
    serve({ ok: false, issues: [{ node: "gate", message: "message: Field required" }, { message: "A workflow needs exactly one start (trigger) step." }] });
    renderWithProviders(
      <Routes>
        <Route path="/workflows/:workflowId" element={<WorkflowEditorRoute />} />
      </Routes>,
      { route: "/workflows/wf_1" },
    );
    expect(await screen.findByText(/2 things need fixing/)).toBeInTheDocument();
    expect(screen.getByText("A workflow needs exactly one start (trigger) step.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "gate" }));
    expect(within(screen.getByRole("list", { name: "Problems with this step" })).getByText("message: Field required")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Run$/ })).toBeDisabled();
  });
});

describe("Workflow run page", () => {
  beforeEach(() => {
    for (const m of [GET, POST, PUT]) m.mockReset();
  });

  it("shows the waiting step and approves it", async () => {
    serve();
    renderWithProviders(
      <Routes>
        <Route path="/workflow-runs/:runId" element={<WorkflowRunRoute />} />
      </Routes>,
      { route: "/workflow-runs/wfr_1" },
    );
    const region = await screen.findByRole("region", { name: "Your decision" });
    expect(within(region).getByText("Publish the tea post?")).toBeInTheDocument();
    expect(screen.getByText("Scheduled")).toBeInTheDocument();
    expect(screen.getByText(/1 of 3 steps done/)).toBeInTheDocument();
    await userEvent.type(within(region).getByLabelText("Note"), "ok");
    await userEvent.click(within(region).getByRole("button", { name: /Approve/ }));
    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith("/api/workflow-runs/{run_id}/nodes/{node_id}/approve", {
        params: { path: { run_id: "wfr_1", node_id: "gate" } },
        body: { note: "ok" },
      }),
    );
  });
});

describe("workflow activity", () => {
  it("is described in plain words", () => {
    const base = { seq: 1, id: "e", ts: "2026-01-01T00:00:00Z", actor: "scheduler", prev_hash: "", hash: "" };
    expect(describeEvent({ ...base, type: "WORKFLOW_STARTED", payload: { name: "Digest", scheduled: true } }).text).toBe("Scheduled run of Digest started");
    expect(describeEvent({ ...base, type: "WORKFLOW_NODE_FAILED", payload: { name: "Digest", label: "Fetch", message: "timeout" } })).toEqual({
      text: "Digest: Fetch failed: timeout",
      tone: "danger",
    });
    expect(describeEvent({ ...base, type: "SCHEDULE_SKIPPED", payload: { reason: "the previous run is still going" } }).text).toBe(
      "Scheduled run skipped: the previous run is still going",
    );
  });
});
