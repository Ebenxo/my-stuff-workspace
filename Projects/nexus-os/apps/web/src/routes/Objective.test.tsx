import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router";
import { ObjectiveComposer } from "../features/objectives/ObjectiveComposer";
import { jsonResponse, renderWithProviders } from "../test/render";
import { ObjectiveRoute } from "./Objective";

const GET = vi.fn();
const POST = vi.fn();
const PUT = vi.fn();
vi.mock("../lib/api", () => ({
  api: { GET: (...a: unknown[]) => GET(...a), POST: (...a: unknown[]) => POST(...a), PUT: (...a: unknown[]) => PUT(...a) },
  runtimeConfig: { baseUrl: "", token: undefined },
}));

const PLAN = {
  objective: "Compare three assistants",
  assumptions: ["Public information only"],
  constraints: [],
  risks: [],
  completion_criteria: ["Covers all three", "Cites sources"],
  warnings: [],
  follow_up: [],
  tasks: [
    { key: "t1", title: "Research the assistants", description: "Collect facts", agent: "researcher", depends_on: [], tools: ["web_search"], expected_outputs: [], review: false, optional: false, approval_required: false },
    { key: "t2", title: "Write the report", description: "", agent: "writer", depends_on: ["t1"], tools: [], expected_outputs: [], review: true, optional: false, approval_required: false },
  ],
};

const objective = (over: object = {}) => ({
  id: "obj_1",
  project_id: "proj_1",
  text: "Research three AI coding assistants and create a comparison report",
  status: "AWAITING_PLAN_APPROVAL",
  run_mode: "review_plan",
  execution_mode: "normal",
  strategy: { name: "multi_agent", rationale: "Research then writing.", estimated_tokens: 42000, agents: ["researcher", "writer"] },
  plan: PLAN,
  result: null,
  error: null,
  model: null,
  private: false,
  replan_count: 0,
  created_at: "2026-09-29T10:00:00Z",
  updated_at: "2026-09-29T10:00:05Z",
  completed_at: null,
  ...over,
});

const task = (over: object = {}) => ({
  id: "task_1",
  objective_id: "obj_1",
  project_id: "proj_1",
  key: "t1",
  title: "Research the assistants",
  description: "Collect facts",
  kind: "work",
  assigned_agent: "researcher",
  status: "WAITING",
  depends_on: [],
  inputs: {},
  outputs: null,
  attempts: 0,
  max_attempts: 2,
  approval_required: false,
  optional: false,
  review: false,
  round: 0,
  parent_task_id: null,
  run_id: null,
  resume: false,
  error: null,
  started_at: null,
  completed_at: null,
  created_at: "2026-09-29T10:00:01Z",
  ...over,
});

function serve(detail: object) {
  GET.mockImplementation((path: string) => {
    switch (path) {
      case "/api/objectives/{objective_id}":
        return Promise.resolve(jsonResponse(detail));
      case "/api/projects/{project_id}":
        return Promise.resolve(jsonResponse({ id: "proj_1", name: "Research", status: "active", settings: {}, is_demo: false }));
      case "/api/projects":
        return Promise.resolve(jsonResponse([{ id: "proj_1", name: "Research", status: "active", settings: {} }]));
      case "/api/providers":
        return Promise.resolve(jsonResponse([{ id: "prov_1", kind: "ollama", name: "Local" }]));
      default:
        return Promise.resolve(jsonResponse([]));
    }
  });
}

const page = () =>
  renderWithProviders(
    <Routes>
      <Route path="/objectives/:objectiveId" element={<ObjectiveRoute />} />
      <Route path="/" element={<ObjectiveComposer />} />
    </Routes>,
    { route: "/objectives/obj_1" },
  );

describe("ObjectiveRoute", () => {
  beforeEach(() => {
    for (const m of [GET, POST, PUT]) m.mockReset();
  });

  it("shows the plan for review and runs it on request", async () => {
    serve({ objective: objective(), tasks: [task(), task({ id: "task_2", key: "t2", title: "Write the report", assigned_agent: "writer", depends_on: ["task_1"], review: true })], messages: [] });
    POST.mockResolvedValue(jsonResponse(objective({ status: "RUNNING" })));
    page();
    const plan = await screen.findByText("Plan · 2 tasks");
    expect(plan).toBeInTheDocument();
    expect(screen.getByText("Reviewed by the Critic")).toBeInTheDocument();
    expect(screen.getByText("Covers all three")).toBeInTheDocument();
    expect(screen.getByText("multi agent")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Run safe steps only/ }));
    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith("/api/objectives/{objective_id}/run", { params: { path: { objective_id: "obj_1" } }, body: { mode: "safe_only" } }),
    );
  });

  it("asks the person when a task is blocked on a question", async () => {
    serve({
      objective: objective({ status: "PAUSED", error: { code: "needs_person", message: "A task needs your answer." } }),
      tasks: [task({ status: "BLOCKED", run_id: "run_1", error: { code: "needs_input", message: "Which three assistants?", options: ["The usual three"] } })],
      messages: [
        { id: "msg_1", sender: "researcher", recipient: "user", task_id: "task_1", type: "QUESTION", payload: { question: "Which three assistants?" }, timestamp: "2026-09-29T10:01:00Z" },
      ],
    });
    POST.mockResolvedValue(jsonResponse(task({ status: "QUEUED" })));
    page();
    const region = await screen.findByRole("region", { name: "Needs your decision" });
    expect(within(region).getByText("Which three assistants?")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("A task needs your answer.");
    expect(screen.getByRole("button", { name: /Continue/ })).toBeInTheDocument();
    // the hand-off feed names who asked whom
    expect(within(screen.getByRole("list", { name: "Agent messages" })).getByText("asked")).toBeInTheDocument();

    await userEvent.click(within(region).getByRole("button", { name: "The usual three" }));
    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith("/api/tasks/{task_id}/answer", { params: { path: { task_id: "task_1" } }, body: { text: "The usual three" } }),
    );
  });

  it("shows the verified result with its deliverables", async () => {
    serve({
      objective: objective({
        status: "COMPLETED",
        result: {
          verdict: "PASS",
          summary: "The report covers all three assistants.",
          criteria: [{ criterion: "Covers all three", met: true, evidence: "Sections 2-4" }],
          missing_requirements: [],
          artifacts: [{ artifact_id: "art_1", name: "comparison.md", version: 2 }],
        },
      }),
      tasks: [task({ status: "COMPLETED", outputs: { summary: "Collected facts" } })],
      messages: [],
    });
    page();
    expect(await screen.findByText("Verified")).toBeInTheDocument();
    expect(screen.getByText("The report covers all three assistants.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /comparison\.md/ })).toHaveAttribute("href", "/projects/proj_1?tab=artifacts&artifact=art_1");
    expect(screen.queryByRole("button", { name: /Cancel/ })).not.toBeInTheDocument();
    expect(screen.getByText("1 of 1 tasks done")).toBeInTheDocument();
  });

  it("says when the objective does not exist", async () => {
    GET.mockResolvedValue(jsonResponse({ detail: "Not found" }, 404));
    page();
    expect(await screen.findByText("Objective not found")).toBeInTheDocument();
  });
});

describe("ObjectiveComposer", () => {
  beforeEach(() => {
    for (const m of [GET, POST, PUT]) m.mockReset();
  });

  it("starts an objective with the plan reviewed first by default", async () => {
    serve({ objective: objective(), tasks: [], messages: [] });
    POST.mockResolvedValue(jsonResponse(objective({ status: "RECEIVED", plan: null })));
    renderWithProviders(
      <Routes>
        <Route path="/" element={<ObjectiveComposer />} />
        <Route path="/objectives/:objectiveId" element={<p>objective page</p>} />
      </Routes>,
    );
    const start = await screen.findByRole("button", { name: /Start/ });
    expect(start).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Objective"), "Summarise the notes");
    await waitFor(() => expect(start).toBeEnabled());
    await userEvent.click(start);
    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith("/api/objectives", {
        body: { project_id: "proj_1", text: "Summarise the notes", run_mode: "review_plan", private: false },
      }),
    );
    expect(await screen.findByText("objective page")).toBeInTheDocument();
  });

  it("does not count the demo's scripted model as a connected provider", async () => {
    serve({ objective: objective(), tasks: [], messages: [] });
    const base = GET.getMockImplementation()!;
    GET.mockImplementation((path: string) =>
      path === "/api/providers" ? Promise.resolve(jsonResponse([{ id: "prov_demo", kind: "demo", name: "Demo (scripted)" }])) : base(path),
    );
    renderWithProviders(<ObjectiveComposer />);
    expect(await screen.findByRole("link", { name: "Connect an AI provider" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Objective"), "Summarise the notes");
    expect(screen.getByRole("button", { name: /Start/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Try the demo/ })).toBeEnabled();
  });

  it("offers the demo", async () => {
    serve({ objective: objective(), tasks: [], messages: [] });
    POST.mockResolvedValue(jsonResponse(objective({ id: "obj_demo" })));
    renderWithProviders(
      <Routes>
        <Route path="/" element={<ObjectiveComposer />} />
        <Route path="/objectives/:objectiveId" element={<p>demo page</p>} />
      </Routes>,
    );
    await userEvent.click(await screen.findByRole("button", { name: /Try the demo/ }));
    await waitFor(() => expect(POST).toHaveBeenCalledWith("/api/demo"));
    expect(await screen.findByText("demo page")).toBeInTheDocument();
  });
});
