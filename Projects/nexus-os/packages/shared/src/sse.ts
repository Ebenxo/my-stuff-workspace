export interface SSEMessage {
  id?: string;
  event: string;
  data: string;
}

/** Incremental Server-Sent Events parser (handles chunks split anywhere, CRLF, comments). */
export class SSEParser {
  private buffer = "";
  private id: string | undefined;
  private event = "";
  private data: string[] = [];

  push(chunk: string): SSEMessage[] {
    this.buffer += chunk;
    const out: SSEMessage[] = [];
    let idx: number;
    while ((idx = this.buffer.search(/\r\n|\n|\r/)) !== -1) {
      const line = this.buffer.slice(0, idx);
      const sep = /^\r\n/.test(this.buffer.slice(idx)) ? 2 : 1;
      // A lone trailing CR may be the first half of CRLF; wait for more input.
      if (this.buffer[idx] === "\r" && idx + 1 === this.buffer.length) break;
      this.buffer = this.buffer.slice(idx + sep);
      const msg = this.line(line);
      if (msg) out.push(msg);
    }
    return out;
  }

  private line(line: string): SSEMessage | null {
    if (line === "") {
      if (this.data.length === 0 && !this.event) {
        this.id = undefined;
        return null;
      }
      const msg: SSEMessage = {
        event: this.event || "message",
        data: this.data.join("\n"),
        ...(this.id !== undefined ? { id: this.id } : {}),
      };
      this.event = "";
      this.data = [];
      return msg;
    }
    if (line.startsWith(":")) return null;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "data") this.data.push(value);
    else if (field === "event") this.event = value;
    else if (field === "id" && !value.includes("\0")) this.id = value;
    return null;
  }
}

export type StreamStatus = "connecting" | "live" | "reconnecting" | "unauthorized" | "closed";

export interface StreamOptions {
  url: string;
  headers?: Record<string, string>;
  /** Resume point; updated automatically from received ids. */
  lastEventId?: string | undefined;
  onMessage: (msg: SSEMessage) => void;
  onStatus?: (status: StreamStatus) => void;
  fetchImpl?: typeof fetch;
  /** Backoff schedule in ms; the last value repeats. */
  backoffMs?: number[];
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
}

const defaultSleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    const t = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(t);
        resolve();
      },
      { once: true },
    );
  });

/**
 * Fetch-based SSE client (EventSource cannot send an Authorization header). Reconnects with
 * backoff, resuming from the last event id so no events are lost or duplicated. Returns stop().
 */
export function streamEvents(opts: StreamOptions): () => void {
  const controller = new AbortController();
  const doFetch = opts.fetchImpl ?? fetch;
  const backoff = opts.backoffMs ?? [500, 1000, 2000, 5000, 10000];
  const sleep = opts.sleep ?? defaultSleep;
  let lastId = opts.lastEventId;

  void (async () => {
    let attempt = 0;
    while (!controller.signal.aborted) {
      opts.onStatus?.(attempt === 0 ? "connecting" : "reconnecting");
      try {
        const response = await doFetch(opts.url, {
          headers: {
            Accept: "text/event-stream",
            ...opts.headers,
            ...(lastId !== undefined ? { "Last-Event-ID": lastId } : {}),
          },
          signal: controller.signal,
        });
        if (response.status === 401 || response.status === 403) {
          opts.onStatus?.("unauthorized");
          return;
        }
        if (!response.ok || !response.body) throw new Error(`stream failed (${response.status})`);
        attempt = 0;
        opts.onStatus?.("live");
        const parser = new SSEParser();
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          for (const msg of parser.push(decoder.decode(value, { stream: true }))) {
            if (msg.id !== undefined) lastId = msg.id;
            opts.onMessage(msg);
          }
        }
      } catch (error) {
        if (controller.signal.aborted) break;
        void error;
      }
      if (controller.signal.aborted) break;
      const wait = backoff[Math.min(attempt, backoff.length - 1)] ?? 1000;
      attempt += 1;
      opts.onStatus?.("reconnecting");
      await sleep(wait, controller.signal);
    }
    opts.onStatus?.("closed");
  })();

  return () => controller.abort();
}
