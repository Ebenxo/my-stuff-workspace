import type { EventRecord } from "@nexus/schemas";
import { beforeEach, describe, expect, it } from "vitest";
import { useEvents } from "./events";

const ev = (seq: number, type = "TASK_CREATED"): EventRecord => ({
  seq,
  id: `evt_${seq}`,
  ts: new Date(2026, 0, 1, 0, 0, seq).toISOString(),
  type,
  actor: "system",
  payload: {},
  prev_hash: "0",
  hash: "1",
});

describe("event store", () => {
  beforeEach(() => useEvents.setState({ events: [], lastSeq: 0, status: "connecting" }));

  it("orders by sequence and drops duplicates", () => {
    useEvents.getState().add([ev(3), ev(1)]);
    useEvents.getState().add([ev(2), ev(3)]);
    expect(useEvents.getState().events.map((e) => e.seq)).toEqual([1, 2, 3]);
    expect(useEvents.getState().lastSeq).toBe(3);
  });

  it("keeps only the newest 500 events", () => {
    useEvents.getState().add(Array.from({ length: 620 }, (_, i) => ev(i + 1)));
    const { events } = useEvents.getState();
    expect(events).toHaveLength(500);
    expect(events[0]?.seq).toBe(121);
    expect(events.at(-1)?.seq).toBe(620);
  });

  it("does not change state for a replayed batch", () => {
    useEvents.getState().add([ev(1)]);
    const before = useEvents.getState().events;
    useEvents.getState().add([ev(1)]);
    expect(useEvents.getState().events).toBe(before);
  });
});
