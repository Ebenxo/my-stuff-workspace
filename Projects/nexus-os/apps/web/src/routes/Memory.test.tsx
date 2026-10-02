import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router";
import { describeEvent } from "../features/events/describe";
import { jsonResponse, renderWithProviders } from "../test/render";
import { MemoryRoute } from "./Memory";
import { SearchRoute } from "./Search";

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
  },
  runtimeConfig: { baseUrl: "", token: undefined },
}));

const source = { kind: "agent", agent: "researcher", run_id: null, task_id: null, objective_id: null, tainted: false, private: false };
const mem = (over: object = {}) => ({
  id: "mem_1",
  scope: "project",
  project_id: "proj_1",
  content: "The client prefers British spelling.",
  summary: "",
  importance: 0.5,
  source,
  tags: ["style"],
  status: "active",
  content_hash: "h",
  access_count: 2,
  last_accessed_at: null,
  merged_into: null,
  created_at: "2026-09-29T10:00:00Z",
  updated_at: "2026-09-29T10:00:00Z",
  ...over,
});

function serve(items: Record<string, object[]>) {
  GET.mockImplementation((path: string, opts?: { params?: { query?: Record<string, unknown> } }) => {
    const q = opts?.params?.query ?? {};
    switch (path) {
      case "/api/memory":
        return Promise.resolve(jsonResponse(items[String(q["status_filter"] ?? "active")] ?? []));
      case "/api/memory/stats":
        return Promise.resolve(jsonResponse({ active: (items["active"] ?? []).length, pending: (items["pending"] ?? []).length, deleted: 0 }));
      case "/api/memory/search":
        return Promise.resolve(
          jsonResponse([{ item: mem(), score: { semantic: 0.6, keyword: 1, recency: 1, importance: 0.5, task: 0, total: 0.645 } }]),
        );
      case "/api/projects":
        return Promise.resolve(jsonResponse([{ id: "proj_1", name: "Site", status: "active", settings: {} }]));
      case "/api/search":
        return Promise.resolve(
          jsonResponse({
            query: q["q"],
            engine: "fts5",
            hits: [
              { kind: "artifact", id: "art_1", project_id: "proj_1", title: "care-guide.md", snippet: "Water [succulents] monthly", score: 3 },
              { kind: "memory", id: "mem_1", project_id: "proj_1", title: "Succulents", snippet: "[Succulents] need little water", score: 2 },
              { kind: "project", id: "proj_1", project_id: "proj_1", title: "Garden", snippet: "", score: 1 },
            ],
          }),
        );
      default:
        return Promise.resolve(jsonResponse([]));
    }
  });
}

describe("Memory page", () => {
  beforeEach(() => {
    for (const m of [GET, POST, PATCH, DELETE]) m.mockReset();
  });

  it("lists memories with where they came from and what to know about them", async () => {
    serve({ active: [mem(), mem({ id: "mem_2", content: "Pricing page says Alpha is cheapest.", importance: 1, source: { ...source, tainted: true } })] });
    renderWithProviders(<MemoryRoute />, { route: "/memory" });
    const list = await screen.findByRole("list", { name: "Memories" });
    expect(within(list).getByText("The client prefers British spelling.")).toBeInTheDocument();
    expect(within(list).getAllByText(/Proposed by the researcher agent/)).toHaveLength(2);
    expect(within(list).getAllByText(/used 2 times/)).toHaveLength(2);
    expect(within(list).getByText("Pinned")).toBeInTheDocument();
    expect(within(list).getByText("After outside content")).toBeInTheDocument();
    expect(within(list).getAllByText("#style")).toHaveLength(2);
  });

  it("keeps a suggestion when asked", async () => {
    serve({ active: [], pending: [mem({ status: "pending", scope: "global", project_id: null })] });
    POST.mockResolvedValue(jsonResponse(mem()));
    renderWithProviders(<MemoryRoute />, { route: "/memory" });
    const tab = await screen.findByRole("tab", { name: /Suggestions/ });
    await waitFor(() => expect(within(tab).getByText("1")).toBeInTheDocument());
    await userEvent.click(tab);
    await userEvent.click(await screen.findByRole("button", { name: /Keep/ }));
    await waitFor(() => expect(POST).toHaveBeenCalledWith("/api/memory/{item_id}/confirm", { params: { path: { item_id: "mem_1" } } }));
  });

  it("shows what agents would recall, with the reasons", async () => {
    serve({ active: [mem()] });
    renderWithProviders(<MemoryRoute />, { route: "/memory" });
    await screen.findByRole("list", { name: "Memories" });
    await userEvent.click(screen.getByLabelText("Rank as agents would"));
    await userEvent.type(screen.getByLabelText(/What would agents recall/), "spelling");
    const recalled = await screen.findByRole("list", { name: "Recalled memories" });
    expect(within(recalled).getByText(/Match 65%/)).toHaveTextContent("Meaning 27, Words 15, Recent 15, Importance 8");
  });

  it("adds a memory and explains a refusal", async () => {
    serve({ active: [] });
    POST.mockResolvedValue(jsonResponse({ error: { code: "invalid_request", message: "Not remembered: it looks like it contains sensitive data (API key)." } }, 422));
    renderWithProviders(<MemoryRoute />, { route: "/memory" });
    await userEvent.click(await screen.findByRole("button", { name: /Add a memory/ }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("What should be remembered?"), "Key is sk-ant-xyz");
    await userEvent.type(within(dialog).getByLabelText("Tags"), "Ops, #ops");
    await userEvent.click(within(dialog).getByRole("button", { name: "Remember" }));
    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith("/api/memory", {
        body: { scope: "project", content: "Key is sk-ant-xyz", tags: ["ops"], pinned: false, project_id: "proj_1" },
      }),
    );
    expect(await within(dialog).findByText(/sensitive data \(API key\)/)).toBeInTheDocument();
  });
});

describe("Search page", () => {
  beforeEach(() => {
    for (const m of [GET, POST, PATCH, DELETE]) m.mockReset();
  });

  it("groups results by kind, links them and highlights matches", async () => {
    serve({});
    renderWithProviders(
      <Routes>
        <Route path="/search" element={<SearchRoute />} />
      </Routes>,
      { route: "/search?q=succulents" },
    );
    const headings = await screen.findAllByRole("heading", { level: 3 });
    expect(headings.map((h) => h.textContent)).toEqual(["Projects (1)", "Deliverables (1)", "Memory (1)"]);
    expect(screen.getByRole("link", { name: /care-guide\.md/ })).toHaveAttribute("href", "/projects/proj_1?tab=artifacts&artifact=art_1");
    expect(screen.getByRole("link", { name: /need little water/ })).toHaveAttribute("href", "/projects/proj_1?tab=memory&memory=mem_1");
    expect(screen.getAllByText("succulents", { selector: "mark" })).toHaveLength(1);
    expect(GET).toHaveBeenCalledWith("/api/search", { params: { query: { q: "succulents", project_id: undefined, kinds: [], limit: 50 } } });
  });
});

describe("memory activity", () => {
  it("is described in plain words without the matched secret", () => {
    const base = { seq: 1, id: "e", ts: "2026-01-01T00:00:00Z", actor: "system", prev_hash: "", hash: "" };
    expect(describeEvent({ ...base, type: "MEMORY_CREATED", payload: { preview: "Use metric units.", status: "pending" } })).toEqual({
      text: "Suggested remembering: Use metric units.",
      tone: "warning",
    });
    expect(describeEvent({ ...base, type: "MEMORY_REJECTED", payload: { categories: ["API key"] } }).text).toBe(
      "Not remembered: it looked like it contained API key",
    );
    expect(describeEvent({ ...base, type: "MEMORY_UPDATED", payload: { change: "confirmed", preview: "x" } }).text).toBe("Kept: x");
    expect(describeEvent({ ...base, type: "MEMORY_COMPRESSED", payload: { merged: 3 } }).text).toBe("Folded 3 older notes into one summary");
  });
});
