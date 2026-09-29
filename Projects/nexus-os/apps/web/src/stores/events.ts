import type { EventRecord } from "@nexus/schemas";
import type { StreamStatus } from "@nexus/shared";
import { create } from "zustand";

const MAX_EVENTS = 500;

interface EventsState {
  events: EventRecord[];
  status: StreamStatus;
  lastSeq: number;
  add: (events: EventRecord[]) => void;
  setStatus: (status: StreamStatus) => void;
  clear: () => void;
}

export const useEvents = create<EventsState>()((set) => ({
  events: [],
  status: "connecting",
  lastSeq: 0,
  add: (incoming) =>
    set((state) => {
      const known = new Set(state.events.map((e) => e.seq));
      const fresh = incoming.filter((e) => !known.has(e.seq));
      if (fresh.length === 0) return state;
      const merged = [...state.events, ...fresh].sort((a, b) => a.seq - b.seq).slice(-MAX_EVENTS);
      return { events: merged, lastSeq: merged[merged.length - 1]?.seq ?? state.lastSeq };
    }),
  setStatus: (status) => set({ status }),
  clear: () => set({ events: [] }),
}));
