import { describe, expect, it } from "vitest";
import { SSEParser, streamEvents, type SSEMessage, type StreamStatus } from "./sse";

describe("SSEParser", () => {
  it("parses complete frames", () => {
    const p = new SSEParser();
    const msgs = p.push('id: 5\nevent: TASK_CREATED\ndata: {"a":1}\n\n');
    expect(msgs).toEqual([{ id: "5", event: "TASK_CREATED", data: '{"a":1}' }]);
  });

  it("handles frames split across arbitrary chunk boundaries", () => {
    const p = new SSEParser();
    const text = 'retry: 3000\n\nid: 1\nevent: A\ndata: x\n\nid: 2\nevent: B\ndata: y\ndata: z\n\n';
    const out: SSEMessage[] = [];
    for (const ch of text) out.push(...p.push(ch));
    expect(out).toEqual([
      { id: "1", event: "A", data: "x" },
      { id: "2", event: "B", data: "y\nz" },
    ]);
  });

  it("ignores comments (heartbeats) and handles CRLF", () => {
    const p = new SSEParser();
    expect(p.push(": ping\n\n")).toEqual([]);
    expect(p.push("id: 9\r\nevent: X\r\ndata: 1\r\n\r\n")).toEqual([{ id: "9", event: "X", data: "1" }]);
  });

  it("defaults the event name to 'message'", () => {
    expect(new SSEParser().push("data: hi\n\n")).toEqual([{ event: "message", data: "hi" }]);
  });
});

function sseResponse(frames: string[], status = 200): Response {
  const enc = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const f of frames) controller.enqueue(enc.encode(f));
      controller.close();
    },
  });
  return new Response(stream, { status, headers: { "content-type": "text/event-stream" } });
}

describe("streamEvents", () => {
  it("reconnects with Last-Event-ID after the stream ends", async () => {
    const seen: string[] = [];
    const headersSeen: (string | null)[] = [];
    let call = 0;
    const fetchImpl = (async (_url: string, init?: RequestInit) => {
      headersSeen.push(new Headers(init?.headers).get("last-event-id"));
      call += 1;
      if (call === 1) return sseResponse(["id: 1\nevent: A\ndata: one\n\n", "id: 2\nevent: A\ndata: two\n\n"]);
      return sseResponse(["id: 3\nevent: A\ndata: three\n\n"]);
    }) as unknown as typeof fetch;

    const statuses: StreamStatus[] = [];
    await new Promise<void>((resolve) => {
      const stop = streamEvents({
        url: "http://x/stream",
        fetchImpl,
        sleep: async () => undefined,
        onStatus: (s) => statuses.push(s),
        onMessage: (m) => {
          seen.push(m.data);
          if (m.data === "three") {
            stop();
            resolve();
          }
        },
      });
    });
    expect(seen).toEqual(["one", "two", "three"]);
    expect(headersSeen).toEqual([null, "2"]);
    expect(statuses).toContain("live");
    expect(statuses).toContain("reconnecting");
  });

  it("stops retrying on 401 and reports unauthorized", async () => {
    const statuses: StreamStatus[] = [];
    let calls = 0;
    const fetchImpl = (async () => {
      calls += 1;
      return new Response("nope", { status: 401 });
    }) as unknown as typeof fetch;
    streamEvents({
      url: "http://x/stream",
      fetchImpl,
      sleep: async () => undefined,
      onStatus: (s) => statuses.push(s),
      onMessage: () => undefined,
    });
    await new Promise((r) => setTimeout(r, 30));
    expect(calls).toBe(1);
    expect(statuses).toContain("unauthorized");
  });
});
