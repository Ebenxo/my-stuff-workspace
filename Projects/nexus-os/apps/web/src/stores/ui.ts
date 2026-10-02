import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type RightTab = "agents" | "graph" | "approvals" | "context" | "activity";
export type BottomTab = "terminal" | "logs" | "tools" | "events" | "errors";

interface UiState {
  sidebarCollapsed: boolean;
  rightOpen: boolean;
  rightTab: RightTab;
  bottomOpen: boolean;
  bottomTab: BottomTab;
  bottomHeight: number;
  toggleSidebar: () => void;
  setRight: (open: boolean, tab?: RightTab) => void;
  setBottom: (open: boolean, tab?: BottomTab) => void;
  setBottomHeight: (h: number) => void;
}

// localStorage can be unavailable or throw (private windows, blocked storage): fall back to memory.
const safeStorage = createJSONStorage(() => {
  try {
    const probe = "__nexus_probe__";
    window.localStorage.setItem(probe, "1");
    window.localStorage.removeItem(probe);
    return window.localStorage;
  } catch {
    const mem = new Map<string, string>();
    return {
      getItem: (k: string) => mem.get(k) ?? null,
      setItem: (k: string, v: string) => void mem.set(k, v),
      removeItem: (k: string) => void mem.delete(k),
    };
  }
});

export const useUi = create<UiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      rightOpen: true,
      rightTab: "activity",
      bottomOpen: false,
      bottomTab: "events",
      bottomHeight: 240,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setRight: (open, tab) => set((s) => ({ rightOpen: open, rightTab: tab ?? s.rightTab })),
      setBottom: (open, tab) => set((s) => ({ bottomOpen: open, bottomTab: tab ?? s.bottomTab })),
      setBottomHeight: (h) => set({ bottomHeight: Math.min(Math.max(h, 120), 640) }),
    }),
    { name: "nexus-ui", storage: safeStorage, version: 1 },
  ),
);
