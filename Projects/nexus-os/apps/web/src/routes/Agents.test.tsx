import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { jsonResponse, renderWithProviders } from "../test/render";
import { AgentsRoute } from "./Agents";

const GET = vi.fn();
const POST = vi.fn();
const PATCH = vi.fn();
vi.mock("../lib/api", () => ({
  api: { GET: (...a: unknown[]) => GET(...a), POST: (...a: unknown[]) => POST(...a), PATCH: (...a: unknown[]) => PATCH(...a) },
  runtimeConfig: { baseUrl: "", token: undefined },
}));

const agent = (over: object = {}) => ({
  id: "agent_builtin_coder",
  slug: "coder",
  name: "Coder",
  role: "Writes, runs and debugs code",
  description: "Implements features.",
  icon: "code",
  system_prompt: "You are the Coder.",
  tools: ["read_file", "run_python"],
  permissions: { max_risk: "HIGH", may_request_approval: true },
  max_steps: 30,
  max_runtime_s: 600,
  max_tool_calls: 60,
  token_budget: 200000,
  temperature: 0.1,
  status: "idle",
  builtin: true,
  ...over,
});

const TOOLS = [
  { name: "read_file", source: "builtin", description: "Read a file", risk_level: "SAFE", requires_approval: false, capabilities: [], enabled: true, input_schema: {} },
  { name: "run_python", source: "builtin", description: "Run Python", risk_level: "MODERATE", requires_approval: false, capabilities: [], enabled: true, input_schema: {} },
  { name: "delete_file", source: "builtin", description: "Delete", risk_level: "HIGH", requires_approval: true, capabilities: [], enabled: true, input_schema: {} },
];

function serve(agents: object[]) {
  GET.mockImplementation((path: string) => {
    switch (path) {
      case "/api/agents":
        return Promise.resolve(jsonResponse(agents));
      case "/api/tools":
        return Promise.resolve(jsonResponse(TOOLS));
      case "/api/projects":
        return Promise.resolve(jsonResponse([{ id: "proj_1", name: "Site", status: "active", settings: {} }]));
      case "/api/providers":
        return Promise.resolve(jsonResponse([{ id: "prov_1", kind: "ollama", name: "Local" }]));
      case "/api/models":
        return Promise.resolve(jsonResponse([{ ref: "prov_1:llama", id: "llama", provider_id: "prov_1", provider_name: "Local", display_name: "Llama", tier: "balanced", local: true }]));
      default:
        return Promise.resolve(jsonResponse([]));
    }
  });
}

describe("AgentsRoute", () => {
  beforeEach(() => {
    for (const m of [GET, POST, PATCH]) m.mockReset();
  });

  it("lists agents with what each can do", async () => {
    serve([agent(), agent({ id: "agent_x", slug: "custom-bot", name: "Custom Bot", role: "Does things", builtin: false, status: "disabled", max_steps: 5, tools: ["read_file"] })]);
    renderWithProviders(<AgentsRoute />);
    await screen.findByRole("heading", { name: "Coder" });
    expect(screen.getByRole("heading", { name: "Custom Bot" })).toBeInTheDocument();
    expect(screen.getByText("Built-in")).toBeInTheDocument();
    expect(screen.getByText("Custom")).toBeInTheDocument();
    expect(screen.getByText("Disabled")).toBeInTheDocument();
    expect(screen.getByText("2 tools")).toBeInTheDocument();
    expect(screen.getByText("1 tools")).toBeInTheDocument();
    expect(screen.getByText("30 steps")).toBeInTheDocument();
    expect(screen.getByText("5 steps")).toBeInTheDocument();
  });

  it("does not let a disabled agent be run", async () => {
    serve([agent({ status: "disabled" })]);
    renderWithProviders(<AgentsRoute />);
    await screen.findByRole("heading", { name: "Coder" });
    expect(screen.getByRole("button", { name: "Run" })).toBeDisabled();
  });

  it("starts a run for the chosen agent, project and task", async () => {
    serve([agent()]);
    POST.mockResolvedValue(jsonResponse({ id: "run_1", status: "RUNNING" }, 202));
    renderWithProviders(<AgentsRoute />);
    await screen.findByRole("heading", { name: "Coder" });
    await userEvent.click(screen.getAllByRole("button", { name: "Run" })[0]!);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByLabelText("Agent")).toHaveValue("coder"));
    const start = within(dialog).getByRole("button", { name: "Start" });
    expect(start).toBeDisabled(); // needs a task first
    await userEvent.type(within(dialog).getByLabelText("What should it do?"), "Fix the bug in files/app.py");
    await waitFor(() => expect(start).toBeEnabled());
    await userEvent.click(start);
    await waitFor(() => expect(POST).toHaveBeenCalled());
    expect(POST.mock.calls[0]![0]).toBe("/api/agents/run");
    expect((POST.mock.calls[0]![1] as { body: unknown }).body).toEqual({
      agent: "coder",
      project_id: "proj_1",
      prompt: "Fix the bug in files/app.py",
      private: false,
    });
  });

  it("asks to connect a provider before running when there is none", async () => {
    serve([agent()]);
    GET.mockImplementation((path: string) =>
      Promise.resolve(jsonResponse(path === "/api/agents" ? [agent()] : path === "/api/projects" ? [{ id: "proj_1", name: "Site", status: "active", settings: {} }] : [])),
    );
    renderWithProviders(<AgentsRoute />);
    await screen.findByRole("heading", { name: "Coder" });
    await userEvent.click(screen.getAllByRole("button", { name: "Run" })[0]!);
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/Agents need a model/)).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText("What should it do?"), "Do something");
    expect(within(dialog).getByRole("button", { name: "Start" })).toBeDisabled();
  });

  it("tunes a built-in agent without touching its identity, and sends only what changed", async () => {
    serve([agent()]);
    PATCH.mockResolvedValue(jsonResponse(agent({ max_steps: 8 })));
    renderWithProviders(<AgentsRoute />);
    await screen.findByRole("heading", { name: "Coder" });
    await userEvent.click(screen.getByRole("button", { name: /Tune/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Tune Coder")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Name")).not.toBeInTheDocument(); // built-ins keep their name and instructions
    expect(within(dialog).queryByLabelText("Instructions")).not.toBeInTheDocument();
    const steps = within(dialog).getByLabelText("Max steps");
    await userEvent.clear(steps);
    await userEvent.type(steps, "8");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(PATCH).toHaveBeenCalled());
    expect(PATCH.mock.calls[0]![0]).toBe("/api/agents/{agent_id}");
    expect((PATCH.mock.calls[0]![1] as { body: unknown }).body).toEqual({ max_steps: 8 });
  });

  it("validates limits before saving", async () => {
    serve([agent()]);
    renderWithProviders(<AgentsRoute />);
    await screen.findByRole("heading", { name: "Coder" });
    await userEvent.click(screen.getByRole("button", { name: /Tune/ }));
    const dialog = await screen.findByRole("dialog");
    const steps = within(dialog).getByLabelText("Max steps");
    await userEvent.clear(steps);
    await userEvent.type(steps, "500");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    expect(await within(dialog).findByText(/Max steps must be between 1 and 100/)).toBeInTheDocument();
    expect(PATCH).not.toHaveBeenCalled();
  });

  it("warns about tools the agent's risk ceiling would always refuse", async () => {
    serve([agent({ permissions: { max_risk: "MODERATE", may_request_approval: true }, tools: ["read_file", "delete_file"] })]);
    renderWithProviders(<AgentsRoute />);
    await screen.findByRole("heading", { name: "Coder" });
    await userEvent.click(screen.getByRole("button", { name: /Tune/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/delete_file can never run/)).toBeInTheDocument();
  });

  it("creates a custom agent that needs a name and a role", async () => {
    serve([]);
    POST.mockResolvedValue(jsonResponse(agent({ id: "agent_new", slug: "bot", name: "Bot", builtin: false }), 201));
    renderWithProviders(<AgentsRoute />);
    await userEvent.click(await screen.findByRole("button", { name: /New agent/ }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create agent" }));
    expect(await within(dialog).findByText("Give the agent a name.")).toBeInTheDocument();
    expect(POST).not.toHaveBeenCalled();
    await userEvent.type(within(dialog).getByLabelText("Name"), "Bot");
    await userEvent.type(within(dialog).getByLabelText("Role"), "Helps with releases");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create agent" }));
    await waitFor(() => expect(POST).toHaveBeenCalled());
    const body = (POST.mock.calls[0]![1] as { body: Record<string, unknown> }).body;
    expect(body).toMatchObject({ name: "Bot", role: "Helps with releases", max_steps: 20, permissions: { max_risk: "MODERATE" } });
  });
});
