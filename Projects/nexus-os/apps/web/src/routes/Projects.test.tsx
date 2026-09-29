import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { jsonResponse, renderWithProviders } from "../test/render";
import { ProjectsRoute } from "./Projects";

const GET = vi.fn();
const POST = vi.fn();
vi.mock("../lib/api", () => ({
  api: { GET: (...a: unknown[]) => GET(...a), POST: (...a: unknown[]) => POST(...a) },
  runtimeConfig: { baseUrl: "", token: undefined },
}));

const project = (id: string, name: string, extra: object = {}) => ({
  id,
  name,
  slug: name.toLowerCase(),
  description: `About ${name}`,
  icon: "folder",
  status: "active",
  is_demo: false,
  settings: { permission_level: null, allowed_domains: [], linked_folders: [] },
  created_at: "2026-09-29T10:00:00Z",
  updated_at: "2026-09-29T10:00:00Z",
  ...extra,
});

describe("ProjectsRoute", () => {
  beforeEach(() => {
    GET.mockReset();
    POST.mockReset();
  });

  it("shows a loading state, then the projects", async () => {
    GET.mockResolvedValue(jsonResponse([project("p1", "Alpha"), project("p2", "Beta", { is_demo: true })]));
    renderWithProviders(<ProjectsRoute />);
    expect(screen.getByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByText("Demo")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Alpha/ })).toHaveAttribute("href", "/projects/p1");
  });

  it("offers to create the first project when there are none", async () => {
    GET.mockResolvedValue(jsonResponse([]));
    renderWithProviders(<ProjectsRoute />);
    expect(await screen.findByText("Create your first project")).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: /New project/ })[0]!);
    expect(await screen.findByRole("dialog", { name: "New project" })).toBeInTheDocument();
  });

  it("shows the server's message and retries on error", async () => {
    GET.mockResolvedValueOnce(jsonResponse({ error: { code: "internal_error", message: "Database is locked" } }, 500));
    GET.mockResolvedValueOnce(jsonResponse([project("p1", "Recovered")]));
    renderWithProviders(<ProjectsRoute />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Database is locked");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Recovered")).toBeInTheDocument();
  });

  it("creates a project through the dialog", async () => {
    GET.mockResolvedValue(jsonResponse([]));
    POST.mockResolvedValue(jsonResponse(project("p9", "Fresh"), 201));
    renderWithProviders(<ProjectsRoute />);
    await userEvent.click((await screen.findAllByRole("button", { name: /New project/ }))[0]!);
    await userEvent.type(await screen.findByLabelText("Name"), "Fresh");
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));
    await waitFor(() => expect(POST).toHaveBeenCalled());
    expect(POST.mock.calls[0]?.[0]).toBe("/api/projects");
    expect(POST.mock.calls[0]?.[1]).toMatchObject({ body: { name: "Fresh" } });
  });

  it("surfaces a creation error inside the dialog", async () => {
    GET.mockResolvedValue(jsonResponse([]));
    POST.mockResolvedValue(jsonResponse({ error: { code: "conflict", message: "Name taken" } }, 409));
    renderWithProviders(<ProjectsRoute />);
    await userEvent.click((await screen.findAllByRole("button", { name: /New project/ }))[0]!);
    await userEvent.type(await screen.findByLabelText("Name"), "Dup");
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(await screen.findByText("Name taken")).toBeInTheDocument();
  });
});
