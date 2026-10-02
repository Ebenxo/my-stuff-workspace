import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes, useLocation } from "react-router";
import { jsonResponse, renderWithProviders } from "../../test/render";
import { Onboarding } from "./Onboarding";

const GET = vi.fn();
const POST = vi.fn();
const PATCH = vi.fn();
vi.mock("../../lib/api", () => ({
  api: { GET: (...a: unknown[]) => GET(...a), POST: (...a: unknown[]) => POST(...a), PATCH: (...a: unknown[]) => PATCH(...a), PUT: vi.fn(), DELETE: vi.fn() },
  runtimeConfig: { baseUrl: "", token: undefined },
}));

const settings = {
  display_name: "",
  workspace_root: "/home/ada/NEXUS",
  default_permission_level: "balanced" as const,
  onboarding_completed: false,
  preferences: {},
  updated_at: "2026-09-29T10:00:00Z",
};

function Where() {
  const loc = useLocation();
  return <p data-testid="where">{loc.pathname}</p>;
}

function renderIt() {
  renderWithProviders(
    <Routes>
      <Route path="/" element={<Onboarding settings={settings} />} />
      <Route path="*" element={<Where />} />
    </Routes>,
    { route: "/" },
  );
}

describe("onboarding", () => {
  beforeEach(() => {
    for (const m of [GET, POST, PATCH]) m.mockReset();
    GET.mockResolvedValue(jsonResponse([]));
    PATCH.mockImplementation((_path: string, init: { body: object }) => Promise.resolve(jsonResponse({ ...settings, ...init.body })));
    POST.mockImplementation((path: string) => Promise.resolve(path === "/api/demo" ? jsonResponse({ id: "obj_1" }) : jsonResponse({})));
  });

  it("walks through the steps and starts the demo", async () => {
    renderIt();
    expect(screen.getByRole("heading", { name: "Welcome to NEXUS" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/What should NEXUS call you/), "Ada");
    await userEvent.click(screen.getByRole("button", { name: "Get started" }));
    expect(screen.getByRole("radio", { name: /Balanced/ })).toHaveAttribute("aria-checked", "true");
    await userEvent.click(screen.getByRole("radio", { name: /Cautious/ }));
    expect(screen.getByLabelText("Where project files live")).toHaveValue("/home/ada/NEXUS");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("heading", { name: /Connect a model/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Skip for now" }));
    expect(screen.getByRole("heading", { name: "You're set, Ada" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Try the demo/ }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/objectives/obj_1"));
    expect(PATCH).toHaveBeenCalledWith("/api/settings", {
      body: { display_name: "Ada", default_permission_level: "cautious", onboarding_completed: true },
    });
    expect(POST).toHaveBeenCalledWith("/api/demo");
  });

  it("can go back, and can be skipped entirely", async () => {
    renderIt();
    await userEvent.click(screen.getByRole("button", { name: "Get started" }));
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("heading", { name: "Welcome to NEXUS" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Setup steps" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Skip setup" }));
    await waitFor(() => expect(PATCH).toHaveBeenCalledWith("/api/settings", { body: { onboarding_completed: true } }));
    expect(POST).not.toHaveBeenCalled();
  });

  it("will not continue without a workspace folder", async () => {
    renderIt();
    await userEvent.click(screen.getByRole("button", { name: "Get started" }));
    await userEvent.clear(screen.getByLabelText("Where project files live"));
    expect(screen.getByText("Enter a folder.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  });
});
