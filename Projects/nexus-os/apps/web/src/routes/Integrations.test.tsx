import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { describeEvent } from "../features/events/describe";
import { McpSettings } from "../features/mcp/McpSettings";
import { jsonResponse, renderWithProviders } from "../test/render";

const GET = vi.fn();
const POST = vi.fn();
const PATCH = vi.fn();
vi.mock("../lib/api", () => ({
  api: { GET: (...a: unknown[]) => GET(...a), POST: (...a: unknown[]) => POST(...a), PATCH: (...a: unknown[]) => PATCH(...a), PUT: vi.fn(), DELETE: vi.fn() },
  runtimeConfig: { baseUrl: "", token: undefined },
}));

const server = {
  id: "mcp_1",
  name: "github",
  description: "Issues and pull requests",
  transport: "stdio",
  command: "npx",
  args: ["-y", "@modelcontextprotocol/server-github"],
  cwd: null,
  env: {},
  url: "",
  headers: {},
  secret_env: ["GITHUB_TOKEN"],
  secret_headers: [],
  risk_level: "HIGH",
  timeout_s: 60,
  enabled: true,
  status: "running",
  error: null,
  server_name: "github-mcp",
  server_version: "1.2",
  protocol_version: "2025-06-18",
  tools: 2,
  resources: 0,
  prompts: 0,
  started_at: "2026-09-29T10:00:00Z",
  last_health: null,
  created_at: "2026-09-29T10:00:00Z",
  updated_at: "2026-09-29T10:00:00Z",
};
const broken = { ...server, id: "mcp_2", name: "files", command: "uvx", args: ["mcp-files"], status: "error", error: "Could not find the program 'uvx'.", tools: 0, secret_env: [] };

function serve() {
  GET.mockImplementation((path: string) => {
    if (path === "/api/mcp/servers") return Promise.resolve(jsonResponse([server, broken]));
    if (path === "/api/mcp/servers/{server_id}")
      return Promise.resolve(
        jsonResponse({
          server,
          instructions: "",
          tools: [
            { name: "mcp__github__create_issue", original_name: "create_issue", title: "", description: "Opens an issue.", input_schema: { properties: { title: {}, body: {} }, required: ["title"] }, hints: [], enabled: true, note: null },
            {
              name: "mcp__github__search",
              original_name: "search",
              title: "",
              description: "Searches.",
              input_schema: {},
              hints: ["The server says this tool only reads."],
              enabled: false,
              note: "The server changed this tool's description or arguments since you last saw it.",
            },
          ],
          resources: [],
          prompts: [],
          skipped: [],
        }),
      );
    return Promise.resolve(jsonResponse([]));
  });
  POST.mockResolvedValue(jsonResponse({ ...server, id: "mcp_3", name: "notes" }));
}

describe("Integrations: MCP servers", () => {
  beforeEach(() => {
    for (const m of [GET, POST, PATCH]) m.mockReset();
    serve();
  });

  it("lists servers with their state and problems", async () => {
    renderWithProviders(<McpSettings />);
    expect(await screen.findByText("github")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("npx -y @modelcontextprotocol/server-github")).toBeInTheDocument();
    expect(screen.getByText(/2 tools · 0 resources · 0 prompts · reports itself as github-mcp 1.2/)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Could not find the program 'uvx'.");
    expect(screen.getByRole("button", { name: /Start/ })).toBeInTheDocument(); // for the broken one
  });

  it("adds a server; secret values go in the request and nowhere else", async () => {
    renderWithProviders(<McpSettings />);
    await userEvent.click((await screen.findAllByRole("button", { name: /Add server/ }))[0]!);
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /Add server/ }));
    expect(within(dialog).getByText(/lowercase letters/)).toBeInTheDocument(); // nothing sent yet
    expect(POST).not.toHaveBeenCalled();
    await userEvent.type(within(dialog).getByLabelText("Name"), "notes");
    await userEvent.type(within(dialog).getByLabelText("Command"), "uvx");
    await userEvent.type(within(dialog).getByLabelText("Arguments (one per line)"), "mcp-notes{enter}--dir /tmp");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add secret variable" }));
    await userEvent.type(within(dialog).getByLabelText("Secret variable 1 name"), "NOTES_TOKEN");
    const secret = within(dialog).getByLabelText("Secret variable 1 value");
    expect(secret).toHaveAttribute("type", "password");
    await userEvent.type(secret, "s3cret");
    await userEvent.selectOptions(within(dialog).getByLabelText("Risk level of its tools"), "VERY_HIGH");
    await userEvent.click(within(dialog).getByRole("button", { name: /Add server/ }));
    await waitFor(() => expect(POST).toHaveBeenCalled());
    expect(POST.mock.calls[0]![0]).toBe("/api/mcp/servers");
    expect(POST.mock.calls[0]![1].body).toEqual({
      name: "notes",
      description: "",
      transport: "stdio",
      risk_level: "VERY_HIGH",
      timeout_s: 60,
      enabled: true,
      command: "uvx",
      args: ["mcp-notes", "--dir /tmp"],
      cwd: null,
      env: {},
      secret_env: { NOTES_TOKEN: "s3cret" },
    });
  });

  it("shows a server's tools, including ones switched off for review", async () => {
    renderWithProviders(<McpSettings />);
    const toggles = await screen.findAllByRole("button", { name: /Show tools, resources, prompts and log/ });
    await userEvent.click(toggles[0]!);
    const list = await screen.findByRole("list", { name: "Tools from this server" });
    expect(within(list).getByText("Arguments: title (required), body")).toBeInTheDocument();
    expect(within(list).getByText(/changed this tool's description/)).toBeInTheDocument();
    expect(within(list).getByText(/only reads\. \(A claim by the server, not a guarantee\.\)/)).toBeInTheDocument();
    PATCH.mockResolvedValue(jsonResponse({ name: "mcp__github__search", enabled: true }));
    await userEvent.click(within(list).getByRole("switch", { name: "Turn on mcp__github__search" }));
    await waitFor(() =>
      expect(PATCH).toHaveBeenCalledWith("/api/tools/{name}", { params: { path: { name: "mcp__github__search" } }, body: { enabled: true } }),
    );
  });

  it("describes MCP activity in plain words", () => {
    const base = { seq: 1, id: "e", ts: "2026-01-01T00:00:00Z", actor: "system", prev_hash: "", hash: "" };
    expect(describeEvent({ ...base, type: "MCP_SERVER_STARTED", payload: { name: "github", tools: 12 } }).text).toBe("MCP server github connected (12 tools)");
    expect(describeEvent({ ...base, type: "MCP_SERVER_FAILED", payload: { name: "github", message: "The server program ended (exit code 1)." } })).toEqual({
      text: "MCP server github is not working: The server program ended (exit code 1).",
      tone: "danger",
    });
    expect(
      describeEvent({ ...base, type: "SECURITY_FLAG", payload: { tool: "mcp__x__helper", findings: ["mcp_tool_definition"], source: "mcp:x" } }).text,
    ).toBe("MCP tool mcp__x__helper switched off until you review it");
  });
});
