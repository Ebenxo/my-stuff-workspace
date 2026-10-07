import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProvidersRoute } from "../../routes/Providers";
import { jsonResponse, renderWithProviders } from "../../test/render";

const GET = vi.fn();
const POST = vi.fn();
const PATCH = vi.fn();
const DELETE = vi.fn();
vi.mock("../../lib/api", () => ({
  api: {
    GET: (...a: unknown[]) => GET(...a),
    POST: (...a: unknown[]) => POST(...a),
    PATCH: (...a: unknown[]) => PATCH(...a),
    DELETE: (...a: unknown[]) => DELETE(...a),
  },
  runtimeConfig: { baseUrl: "", token: undefined },
}));

const KINDS = [
  { kind: "anthropic", label: "Anthropic", default_base_url: "https://api.anthropic.com", needs_key: true, local: false, help: "Claude models." },
  { kind: "ollama", label: "Ollama (local)", default_base_url: "http://127.0.0.1:11434", needs_key: false, local: true, help: "Local models." },
  { kind: "openai_compatible", label: "Custom OpenAI-compatible", default_base_url: null, needs_key: false, local: false, help: "Any compatible endpoint." },
  { kind: "demo", label: "Demo (scripted)", default_base_url: null, needs_key: false, local: true, help: "Scripted responses." },
];

const provider = (over: object = {}) => ({
  id: "prov_1",
  kind: "anthropic",
  name: "Claude",
  base_url: null,
  default_model: "claude-sonnet-5-5",
  enabled: true,
  options: { models: {}, structured_mode: "json_schema" },
  has_key: true,
  key_hint: "••••0123",
  is_local: false,
  last_test_at: null,
  last_test_ok: null,
  last_test_error: null,
  created_at: "2026-09-29T10:00:00Z",
  ...over,
});

function route(providers: object[]) {
  GET.mockImplementation((path: string) => {
    if (path === "/api/providers") return Promise.resolve(jsonResponse(providers));
    if (path === "/api/providers/kinds") return Promise.resolve(jsonResponse(KINDS));
    if (path === "/api/providers/{provider_id}/models") return Promise.resolve(jsonResponse([{ id: "claude-sonnet-5-5" }, { id: "claude-opus-5-5" }]));
    return Promise.resolve(jsonResponse([]));
  });
}

describe("ProvidersRoute", () => {
  beforeEach(() => {
    for (const m of [GET, POST, PATCH, DELETE]) m.mockReset();
  });

  it("invites the user to connect a provider when there are none", async () => {
    route([]);
    renderWithProviders(<ProvidersRoute />);
    expect(await screen.findByText("Connect an AI provider")).toBeInTheDocument();
    expect(screen.getByText(/local model that never leaves this machine/)).toBeInTheDocument();
  });

  it("does not offer the scripted demo provider as a manual choice", async () => {
    route([]);
    renderWithProviders(<ProvidersRoute />);
    await userEvent.click((await screen.findAllByRole("button", { name: /Add provider/ }))[0]!);
    await screen.findByRole("radio", { name: /Anthropic/ });
    expect(screen.queryByRole("radio", { name: /Demo/ })).not.toBeInTheDocument();
  });

  it("adds a cloud provider: picks the kind, requires a key, sends it once, and never echoes it", async () => {
    route([]);
    POST.mockResolvedValue(jsonResponse(provider(), 201));
    renderWithProviders(<ProvidersRoute />);
    await userEvent.click((await screen.findAllByRole("button", { name: /Add provider/ }))[0]!);
    await userEvent.click(await screen.findByRole("radio", { name: /Anthropic/ }));

    const key = await screen.findByLabelText(/API key/);
    expect(key).toHaveAttribute("type", "password");
    expect(key).toHaveAttribute("autocomplete", "new-password");
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByText("Anthropic needs an API key.")).toBeInTheDocument();
    expect(POST).not.toHaveBeenCalled();

    await userEvent.type(key, "sk-ant-test-key-0123456789");
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    await waitFor(() => expect(POST).toHaveBeenCalled());
    expect(POST.mock.calls[0]?.[0]).toBe("/api/providers");
    expect(POST.mock.calls[0]?.[1]).toMatchObject({ body: { kind: "anthropic", name: "Anthropic", api_key: "sk-ant-test-key-0123456789" } });
  });

  it("local providers need no key, and a custom endpoint needs a URL", async () => {
    route([]);
    POST.mockResolvedValue(jsonResponse(provider({ kind: "ollama", is_local: true, has_key: false, key_hint: null }), 201));
    renderWithProviders(<ProvidersRoute />);
    await userEvent.click((await screen.findAllByRole("button", { name: /Add provider/ }))[0]!);
    await userEvent.click(await screen.findByRole("radio", { name: /Ollama/ }));
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    await waitFor(() => expect(POST).toHaveBeenCalled());
    expect(POST.mock.calls[0]?.[1].body).not.toHaveProperty("api_key");

    POST.mockClear();
    await userEvent.click((await screen.findAllByRole("button", { name: /Add provider/ }))[0]!);
    await userEvent.click(await screen.findByRole("radio", { name: /Custom/ }));
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByText("Enter the endpoint's base URL.")).toBeInTheDocument();
    expect(POST).not.toHaveBeenCalled();
  });

  it("shows server-side validation errors inside the dialog", async () => {
    route([]);
    POST.mockResolvedValue(jsonResponse({ error: { code: "invalid_request", message: "An API key would be sent unencrypted. Use https://" } }, 422));
    renderWithProviders(<ProvidersRoute />);
    await userEvent.click((await screen.findAllByRole("button", { name: /Add provider/ }))[0]!);
    await userEvent.click(await screen.findByRole("radio", { name: /Anthropic/ }));
    await userEvent.type(await screen.findByLabelText(/API key/), "k-0123456789abcdef");
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByText(/sent unencrypted/)).toBeInTheDocument();
  });

  it("lists providers with key hint, locality and connection results", async () => {
    route([provider({ last_test_ok: true, last_test_at: "2026-09-29T10:00:00Z" }), provider({ id: "prov_2", name: "Local", kind: "ollama", is_local: true, has_key: false, key_hint: null, last_test_ok: false, last_test_error: "Could not connect to Ollama. Is it running and reachable?" })]);
    renderWithProviders(<ProvidersRoute />);
    expect(await screen.findByText("Claude")).toBeInTheDocument();
    expect(screen.getByText("••••0123")).toBeInTheDocument();
    expect(screen.getByText("not needed")).toBeInTheDocument();
    expect(screen.getByText("On this machine")).toBeInTheDocument();
    expect(screen.getByText(/Is it running and reachable/)).toBeInTheDocument();
    expect(screen.queryByText(/sk-/)).not.toBeInTheDocument();
  });

  it("tests a connection and shows the outcome", async () => {
    route([provider()]);
    POST.mockResolvedValue(jsonResponse({ ok: true, latency_ms: 123, detail: "Connected. 4 model(s) available.", models_found: 4 }));
    renderWithProviders(<ProvidersRoute />);
    await userEvent.click(await screen.findByRole("button", { name: /Test connection/ }));
    expect(await screen.findByText(/Connected. 4 model\(s\) available. \(123 ms\)/)).toBeInTheDocument();
    expect(POST.mock.calls[0]?.[0]).toBe("/api/providers/{provider_id}/test");
  });

  it("reports a failed test without hiding the reason", async () => {
    route([provider()]);
    POST.mockResolvedValue(jsonResponse({ ok: false, latency_ms: 40, detail: "Authentication failed: invalid key", error_code: "auth_failed" }));
    renderWithProviders(<ProvidersRoute />);
    await userEvent.click(await screen.findByRole("button", { name: /Test connection/ }));
    expect(await screen.findByText(/Authentication failed: invalid key/)).toBeInTheDocument();
  });

  it("toggles a provider off and on", async () => {
    route([provider()]);
    PATCH.mockResolvedValue(jsonResponse(provider({ enabled: false })));
    renderWithProviders(<ProvidersRoute />);
    await userEvent.click(await screen.findByRole("switch", { name: "Disable Claude" }));
    await waitFor(() => expect(PATCH).toHaveBeenCalled());
    expect(PATCH.mock.calls[0]?.[1]).toMatchObject({ body: { enabled: false } });
  });

  it("edit shows only a key hint, omits the key when blank, and can remove it", async () => {
    route([provider()]);
    PATCH.mockResolvedValue(jsonResponse(provider()));
    renderWithProviders(<ProvidersRoute />);
    await userEvent.click(await screen.findByRole("button", { name: /Edit/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/A key is stored \(••••0123\)/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/API key/)).toHaveValue("");

    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(PATCH).toHaveBeenCalledTimes(1));
    expect(PATCH.mock.calls[0]?.[1].body).not.toHaveProperty("api_key");

    await userEvent.click(await screen.findByRole("button", { name: /Edit/ }));
    const again = await screen.findByRole("dialog");
    await userEvent.click(within(again).getByLabelText("Remove the stored key"));
    await userEvent.click(within(again).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(PATCH).toHaveBeenCalledTimes(2));
    expect(PATCH.mock.calls[1]?.[1].body).toMatchObject({ api_key: "" });
  });

  it("asks before removing a provider", async () => {
    route([provider()]);
    DELETE.mockResolvedValue({ data: undefined, response: new Response(null, { status: 204 }) });
    renderWithProviders(<ProvidersRoute />);
    await userEvent.click(await screen.findByRole("button", { name: "Remove Claude" }));
    const dialog = await screen.findByRole("dialog", { name: /Remove Claude\?/ });
    expect(DELETE).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove provider" }));
    await waitFor(() => expect(DELETE).toHaveBeenCalled());
  });

  it("shows an error state with retry when the list fails", async () => {
    GET.mockImplementation((path: string) =>
      Promise.resolve(path === "/api/providers" ? jsonResponse({ error: { code: "internal_error", message: "Database is locked" } }, 500) : jsonResponse(KINDS)),
    );
    renderWithProviders(<ProvidersRoute />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Database is locked");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
