import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes, useLocation } from "react-router";
import { useOverlays } from "../../stores/overlays";
import { jsonResponse, renderWithProviders } from "../../test/render";
import { GO, resolveKey, shortcutList } from "../shortcuts/keys";
import { CommandPalette } from "./CommandPalette";
import { COMMANDS, paletteItems, rank, score } from "./commands";

const GET = vi.fn();
vi.mock("../../lib/api", () => ({
  api: { GET: (...a: unknown[]) => GET(...a), POST: vi.fn(), PUT: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() },
  runtimeConfig: { baseUrl: "", token: undefined },
}));

const key = (k: string, mods: Partial<{ ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean }> = {}) => ({
  key: k,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  shiftKey: false,
  ...mods,
});

describe("keyboard shortcuts", () => {
  const idle = { pendingG: false, typing: false };

  it("maps keys to actions", () => {
    expect(resolveKey(key("k", { ctrlKey: true }), idle).action).toBe("palette");
    expect(resolveKey(key("K", { metaKey: true }), idle).action).toBe("palette");
    expect(resolveKey(key("j", { ctrlKey: true }), idle).action).toBe("toggle-bottom");
    expect(resolveKey(key(".", { metaKey: true }), idle).action).toBe("toggle-activity");
    expect(resolveKey(key("/"), idle).action).toBe("search");
    expect(resolveKey(key("?", { shiftKey: true }), idle).action).toBe("shortcuts");
  });

  it("goes somewhere with g then a letter, and forgets a stray g", () => {
    const first = resolveKey(key("g"), idle);
    expect(first).toEqual({ pendingG: true });
    expect(resolveKey(key("w"), { pendingG: true, typing: false })).toEqual({ action: "go:/workflows", pendingG: false });
    expect(resolveKey(key("z"), { pendingG: true, typing: false })).toEqual({ pendingG: false });
    expect(Object.keys(GO)).toEqual(["c", "p", "a", "w", "r", "m", "s"]);
  });

  it("never takes letters while someone is typing, but modifier shortcuts still work", () => {
    const typing = { pendingG: false, typing: true };
    expect(resolveKey(key("g"), typing)).toEqual({ pendingG: false });
    expect(resolveKey(key("/"), typing).action).toBeUndefined();
    expect(resolveKey(key("?"), typing).action).toBeUndefined();
    expect(resolveKey(key("k", { ctrlKey: true }), typing).action).toBe("palette");
    expect(resolveKey(key("c", { ctrlKey: true }), idle).action).toBeUndefined(); // copy stays copy
  });

  it("lists shortcuts with the right modifier", () => {
    expect(shortcutList(true)[0]!.items[0]!.keys).toEqual(["⌘", "K"]);
    expect(shortcutList(false)[0]!.items[0]!.keys).toEqual(["Ctrl", "K"]);
  });
});

describe("palette ranking", () => {
  it("prefers exact, then prefix, then word start, then substring, then scattered letters", () => {
    expect(score("projects", "Projects")).toBe(100);
    expect(score("pro", "Projects")).toBe(80);
    expect(score("flow", "New workflow")).toBe(40);
    expect(score("work", "New workflow")).toBe(60);
    expect(score("nwf", "New workflow")).toBeGreaterThan(0);
    expect(score("xyz", "New workflow")).toBe(0);
  });

  it("uses keywords, and keeps listed order for ties", () => {
    expect(rank("mcp", COMMANDS).map((c) => c.id).slice(0, 2)).toEqual(["go-integrations", "new-mcp"]);
    expect(rank("api key", COMMANDS)[0]!.id).toBe("go-providers");
    expect(rank("", COMMANDS)).toHaveLength(COMMANDS.length);
  });

  it("offers projects, search results and a search-everything fallback", () => {
    const projects = [
      { id: "p1", name: "Tea shop", status: "active" },
      { id: "p2", name: "Old stuff", status: "archived" },
    ];
    const empty = paletteItems("", projects);
    expect(empty[0]!.group).toBe("Create");
    expect(empty.some((i) => i.label === "Tea shop")).toBe(true);
    expect(empty.some((i) => i.label === "Old stuff")).toBe(false);
    const items = paletteItems("tea", projects, [{ kind: "memory", id: "m1", title: "Tea prices", href: "/memory?memory=m1" }]);
    expect(items[0]).toMatchObject({ label: "Tea shop", to: "/projects/p1" });
    expect(items.find((i) => i.group === "Found")).toMatchObject({ label: "Tea prices", to: "/memory?memory=m1" });
    expect(items.at(-1)).toMatchObject({ id: "search-all", to: "/search?q=tea" });
  });
});

function Where() {
  const loc = useLocation();
  return <p data-testid="where">{loc.pathname + loc.search}</p>;
}

describe("command palette", () => {
  beforeEach(() => {
    GET.mockReset();
    GET.mockImplementation((path: string) =>
      Promise.resolve(path === "/api/projects" ? jsonResponse([{ id: "p1", name: "Tea shop", status: "active", settings: {} }]) : jsonResponse({ hits: [] })),
    );
  });

  it("finds a command by typing and goes there with Enter", async () => {
    renderWithProviders(
      <>
        <CommandPalette />
        <Routes>
          <Route path="*" element={<Where />} />
        </Routes>
      </>,
      { route: "/" },
    );
    act(() => useOverlays.getState().setPalette(true));
    const input = await screen.findByRole("combobox", { name: /Type a command/ });
    await userEvent.type(input, "new work{Enter}"); // Enter straight after typing picks from what was typed
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/workflows?new=1"));
    act(() => useOverlays.getState().setPalette(true));
    await userEvent.type(await screen.findByRole("combobox"), "new work");
    expect(screen.getAllByRole("option")[0]).toHaveTextContent("New workflow");
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/workflows?new=1"));
    expect(useOverlays.getState().palette).toBe(false);
  });

  it("moves through results with the arrow keys and opens a project", async () => {
    renderWithProviders(
      <>
        <CommandPalette />
        <Routes>
          <Route path="*" element={<Where />} />
        </Routes>
      </>,
      { route: "/" },
    );
    act(() => useOverlays.getState().setPalette(true));
    const input = await screen.findByRole("combobox");
    await userEvent.type(input, "tea");
    await screen.findByRole("option", { name: /Tea shop/ });
    await userEvent.keyboard("{ArrowDown}{ArrowUp}{Enter}");
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/projects/p1"));
  });
});
