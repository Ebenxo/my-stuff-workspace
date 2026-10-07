import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DETAIL_TYPES, HISTORY_PAGE } from "../lib/ideaQueries";
import { useEvents } from "../stores/events";
import { jsonResponse, renderWithProviders } from "../test/render";
import { TimelineRoute } from "./Timeline";

const GET = vi.fn();
vi.mock("../lib/api", () => ({
  api: { GET: (...a: unknown[]) => GET(...a), POST: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn(), PUT: vi.fn() },
  runtimeConfig: { baseUrl: "", token: undefined },
}));

const soon = new Date(Date.now() + 3 * 3600 * 1000).toISOString();
const item = (over: object) => ({ detail: "", project_id: "proj_1", at: new Date().toISOString(), ref_id: null, idea_kind: null, ...over });
const timeline = {
  generated_at: new Date().toISOString(),
  waiting: [
    item({ kind: "objective", id: "obj_1", title: "Plan the spring planting", detail: "The plan is ready for your review.", status: "AWAITING_PLAN_APPROVAL" }),
    item({ kind: "idea", id: "idea_1", title: "Pay the water bill", detail: "To-do", status: "OVERDUE", idea_kind: "todo" }),
  ],
  now: [item({ kind: "workflow_run", id: "wfr_1", title: "Weekly check is running", status: "RUNNING" })],
  next: [item({ kind: "schedule", id: "sch_1", title: "Weekly check runs", detail: "Every Monday at 09:00", status: "SCHEDULED", at: soon, ref_id: "wf_1" })],
  pinned: [item({ kind: "idea", id: "idea_2", title: "Mulch keeps roots cool", status: "OPEN", idea_kind: "note" })],
};
const event = (seq: number, type: string, payload: object = {}, over: object = {}) => ({
  seq,
  id: `e${seq}`,
  ts: new Date().toISOString(),
  type,
  project_id: "proj_1",
  objective_id: null,
  task_id: null,
  run_id: null,
  agent_id: null,
  actor: "user",
  payload,
  prev_hash: "",
  hash: "",
  ...over,
});

function serve(pages: object[][]) {
  GET.mockImplementation((path: string, init?: { params?: { query?: { before_seq?: number } } }) => {
    switch (path) {
      case "/api/timeline":
        return Promise.resolve(jsonResponse(timeline));
      case "/api/projects":
        return Promise.resolve(jsonResponse([{ id: "proj_1", name: "Garden", status: "active", settings: {} }]));
      case "/api/events":
        return Promise.resolve(jsonResponse(init?.params?.query?.before_seq ? (pages[1] ?? []) : (pages[0] ?? [])));
      default:
        return Promise.resolve(jsonResponse([]));
    }
  });
}

describe("Timeline", () => {
  beforeEach(() => {
    GET.mockReset();
    useEvents.getState().clear();
  });

  it("shows what needs you, what is running, what is coming up, and what you pinned", async () => {
    serve([[event(2, "IDEA_CREATED", { kind: "todo", text: "Pay the water bill", idea_id: "idea_1" })]]);
    renderWithProviders(<TimelineRoute />, { route: "/timeline" });

    const needs = await screen.findByRole("list", { name: "Needs you" });
    expect(within(needs).getByRole("link", { name: /Plan the spring planting/ })).toHaveAttribute("href", "/objectives/obj_1");
    const bill = within(needs).getByRole("link", { name: /Pay the water bill/ });
    expect(bill).toHaveAttribute("href", "/ideas?idea=idea_1");
    expect(within(bill).getByText(/^Overdue · /)).toBeInTheDocument();

    const now = screen.getByRole("list", { name: "Happening now" });
    expect(within(now).getByRole("link", { name: /Weekly check is running/ })).toHaveAttribute("href", "/workflow-runs/wfr_1");
    const next = screen.getByRole("list", { name: "Coming up" });
    const run = within(next).getByRole("link", { name: /Weekly check runs/ });
    expect(run).toHaveAttribute("href", "/workflows/wf_1");
    expect(within(run).getByText(/^in 3 hours · /)).toBeInTheDocument();

    expect(screen.getByRole("link", { name: "Mulch keeps roots cool" })).toHaveAttribute("href", "/ideas?idea=idea_2");
    const today = await screen.findByRole("region", { name: "Today" });
    expect(within(today).getByRole("link", { name: /To-do added: Pay the water bill/ })).toHaveAttribute("href", "/ideas?idea=idea_1");
  });

  it("pages back through history, and shows every step only when asked", async () => {
    const first = Array.from({ length: HISTORY_PAGE }, (_, i) => event(500 - i, "PROJECT_UPDATED"));
    serve([first, [event(10, "PROJECT_CREATED", { name: "Garden" })]]);
    renderWithProviders(<TimelineRoute />, { route: "/timeline" });

    const query = () => (GET.mock.calls.filter((c) => c[0] === "/api/events").at(-1)?.[1] as { params: { query: Record<string, unknown> } }).params.query;
    await screen.findByRole("button", { name: "Load older" });
    expect(query()).toMatchObject({ newest_first: true, limit: HISTORY_PAGE, before_seq: 0 });
    for (const t of DETAIL_TYPES) expect(String(query()["exclude_types"])).toContain(t);

    await userEvent.click(screen.getByRole("button", { name: "Load older" }));
    expect(await screen.findByText("Project created: Garden")).toBeInTheDocument();
    expect(query()).toMatchObject({ before_seq: 500 - HISTORY_PAGE + 1 });
    expect(screen.getByText("That is everything.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("switch", { name: "Show every step" }));
    await waitFor(() => expect(String(query()["exclude_types"])).not.toContain("AGENT_STEP"));
    expect(String(query()["exclude_types"])).toContain("USAGE_RECORDED");
  });

  it("adds live events on top without reloading", async () => {
    serve([[event(5, "PROJECT_CREATED", { name: "Garden" })]]);
    renderWithProviders(<TimelineRoute />, { route: "/timeline" });
    await screen.findByText("Project created: Garden");
    useEvents.getState().add([
      event(6, "IDEA_CREATED", { kind: "note", text: "Tea at four", idea_id: "idea_5" }) as never,
      event(7, "USAGE_RECORDED") as never, // bookkeeping stays out
    ]);
    expect(await screen.findByText("Note added: Tea at four")).toBeInTheDocument();
    expect(screen.queryByText(/usage recorded/i)).not.toBeInTheDocument();
    expect(screen.getByText("2 entries shown")).toBeInTheDocument();
  });

  it("filters by project", async () => {
    serve([[]]);
    renderWithProviders(<TimelineRoute />, { route: "/timeline" });
    await screen.findByText("Nothing has happened yet");
    await userEvent.selectOptions(await screen.findByLabelText("Project"), "proj_1");
    await waitFor(() => expect(GET).toHaveBeenCalledWith("/api/timeline", { params: { query: { project_id: "proj_1" } } }));
  });
});
