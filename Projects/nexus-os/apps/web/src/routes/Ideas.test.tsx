import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { jsonResponse, renderWithProviders } from "../test/render";
import { IdeasRoute } from "./Ideas";

const GET = vi.fn();
const POST = vi.fn();
const PATCH = vi.fn();
const DELETE = vi.fn();
vi.mock("../lib/api", () => ({
  api: {
    GET: (...a: unknown[]) => GET(...a),
    POST: (...a: unknown[]) => POST(...a),
    PATCH: (...a: unknown[]) => PATCH(...a),
    DELETE: (...a: unknown[]) => DELETE(...a),
    PUT: vi.fn(),
  },
  runtimeConfig: { baseUrl: "", token: undefined },
}));

const idea = (over: object = {}) => ({
  id: "idea_1",
  project_id: null,
  kind: "idea",
  text: "A case-study page per project",
  status: "open",
  pinned: false,
  due_at: null,
  reminded_at: null,
  done_at: null,
  objective_id: null,
  created_at: "2026-10-01T10:00:00Z",
  updated_at: "2026-10-01T10:00:00Z",
  ...over,
});
const project = { id: "proj_1", name: "Studio website", status: "active", settings: {} };

function serve(items: object[], providers: object[] = [{ id: "prov_1", kind: "anthropic" }]) {
  GET.mockImplementation((path: string) => {
    switch (path) {
      case "/api/ideas":
        return Promise.resolve(jsonResponse(items));
      case "/api/projects":
        return Promise.resolve(jsonResponse([project]));
      case "/api/providers":
        return Promise.resolve(jsonResponse(providers));
      default:
        return Promise.resolve(jsonResponse([]));
    }
  });
}

function renderIdeas(route = "/ideas") {
  return renderWithProviders(
    <Routes>
      <Route path="/ideas" element={<IdeasRoute />} />
      <Route path="/objectives/:id" element={<p>objective page</p>} />
    </Routes>,
    { route },
  );
}

describe("Ideas & notes", () => {
  beforeEach(() => {
    for (const fn of [GET, POST, PATCH, DELETE]) fn.mockReset();
  });

  it("captures an idea with Enter", async () => {
    serve([]);
    POST.mockResolvedValue(jsonResponse(idea({ text: "Try a darker sidebar" })));
    renderIdeas();
    expect(await screen.findByText("Nothing here yet")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Idea"), "  Try a darker sidebar {Enter}");
    await waitFor(() => expect(POST).toHaveBeenCalled());
    expect(POST).toHaveBeenCalledWith("/api/ideas", {
      body: { text: "Try a darker sidebar", kind: "idea", project_id: null, pinned: false, due_at: null },
    });
  });

  it("captures a pinned to-do with a due time and a project", async () => {
    serve([]);
    POST.mockResolvedValue(jsonResponse(idea({ kind: "todo" })));
    renderIdeas();
    await screen.findByText("Nothing here yet");
    await userEvent.click(screen.getByRole("radio", { name: "To-do" }));
    await userEvent.type(screen.getByLabelText("To-do"), "Renew the domain");
    await userEvent.click(screen.getByRole("button", { name: /Due time/ }));
    await userEvent.click(screen.getByRole("button", { name: "Tomorrow morning" }));
    await userEvent.click(screen.getByRole("switch", { name: "Pin it" }));
    await userEvent.selectOptions(screen.getByLabelText("Project"), "proj_1");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(POST).toHaveBeenCalled());
    const body = (POST.mock.calls[0]?.[1] as { body: Record<string, unknown> }).body;
    expect(body).toMatchObject({ text: "Renew the domain", kind: "todo", project_id: "proj_1", pinned: true });
    const due = new Date(body["due_at"] as string);
    expect([due.getHours(), due.getMinutes()]).toEqual([9, 0]);
    expect(due.getTime()).toBeGreaterThan(Date.now());
  });

  it("marks done, pins, deletes after a second click, and filters", async () => {
    serve([idea(), idea({ id: "idea_2", kind: "todo", text: "Send the invoice", due_at: "2020-01-01T09:00:00Z", project_id: "proj_1" })]);
    PATCH.mockResolvedValue(jsonResponse(idea()));
    DELETE.mockResolvedValue(jsonResponse(null, 204));
    renderIdeas();
    const invoice = (await screen.findByText("Send the invoice")).closest("li")!;
    expect(within(invoice).getByText(/^Overdue · /)).toBeInTheDocument();
    expect(within(invoice).getByRole("link", { name: "Studio website" })).toHaveAttribute("href", "/projects/proj_1");

    await userEvent.click(within(invoice).getByRole("checkbox", { name: "Mark as done" }));
    expect(PATCH).toHaveBeenCalledWith("/api/ideas/{idea_id}", { params: { path: { idea_id: "idea_2" } }, body: { status: "done" } });

    await userEvent.click(within(invoice).getByRole("button", { name: "Pin" }));
    expect(PATCH).toHaveBeenLastCalledWith("/api/ideas/{idea_id}", { params: { path: { idea_id: "idea_2" } }, body: { pinned: true } });

    await userEvent.click(within(invoice).getByRole("button", { name: "Delete" }));
    expect(DELETE).not.toHaveBeenCalled();
    await userEvent.click(within(invoice).getByRole("button", { name: "Delete?" }));
    await waitFor(() => expect(DELETE).toHaveBeenCalledWith("/api/ideas/{idea_id}", { params: { path: { idea_id: "idea_2" } } }));

    await userEvent.click(screen.getByRole("radio", { name: "To-dos" }));
    await userEvent.click(screen.getByRole("radio", { name: "Done" }));
    await waitFor(() =>
      expect(GET).toHaveBeenLastCalledWith("/api/ideas", {
        params: { query: { status_filter: "done", kind: "todo", project_id: undefined, q: undefined, limit: 300 } },
      }),
    );
  });

  it("edits text, kind and due time in place", async () => {
    serve([idea({ due_at: "2030-01-01T09:00:00Z" })]);
    PATCH.mockResolvedValue(jsonResponse(idea()));
    renderIdeas();
    const row = (await screen.findByText("A case-study page per project")).closest("li")!;
    await userEvent.click(within(row).getByRole("button", { name: "Edit" }));
    const box = within(row).getByRole("textbox");
    await userEvent.clear(box);
    await userEvent.type(box, "Case studies with before/after shots");
    await userEvent.click(within(row).getByRole("radio", { name: "Note" }));
    await userEvent.clear(within(row).getByLabelText("Due"));
    await userEvent.click(within(row).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(PATCH).toHaveBeenCalledWith("/api/ideas/{idea_id}", {
        params: { path: { idea_id: "idea_1" } },
        body: { text: "Case studies with before/after shots", kind: "note", due_at: null, project_id: null },
      }),
    );
  });

  it("starts an idea as an objective and opens it", async () => {
    serve([idea()]);
    POST.mockResolvedValue(jsonResponse({ idea: idea({ status: "done", objective_id: "obj_9" }), objective: { id: "obj_9" } }, 202));
    renderIdeas();
    const row = (await screen.findByText("A case-study page per project")).closest("li")!;
    await userEvent.click(within(row).getByRole("button", { name: "Start as an objective" }));
    const dialog = await screen.findByRole("dialog", { name: "Start as an objective" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Start" }));
    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith("/api/ideas/{idea_id}/objective", {
        params: { path: { idea_id: "idea_1" } },
        body: { project_id: "proj_1", run_mode: "review_plan", private: false },
      }),
    );
    expect(await screen.findByText("objective page")).toBeInTheDocument();
  });

  it("asks for a provider before starting an objective", async () => {
    serve([idea()], [{ id: "demo", kind: "demo" }]);
    renderIdeas();
    const row = (await screen.findByText("A case-study page per project")).closest("li")!;
    await userEvent.click(within(row).getByRole("button", { name: "Start as an objective" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByRole("link", { name: "Connect a provider" })).toHaveAttribute("href", "/settings/providers");
    expect(within(dialog).getByRole("button", { name: "Start" })).toBeDisabled();
  });

  it("highlights the idea a link points at, whatever its status", async () => {
    serve([idea({ status: "done", done_at: "2026-10-01T11:00:00Z" })]);
    renderIdeas("/ideas?idea=idea_1");
    await screen.findByText("A case-study page per project");
    expect(GET).toHaveBeenCalledWith("/api/ideas", expect.objectContaining({ params: expect.objectContaining({ query: expect.objectContaining({ status_filter: "all" }) }) }));
    expect(screen.getByRole("checkbox", { name: "Mark as not done" })).toBeInTheDocument();
  });
});
