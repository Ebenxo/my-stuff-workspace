/**
 * Boots the browser preview: loads the person's saved data, answers API requests in the page
 * (including the live event stream), saves every change, and sends due reminders while open.
 */
import { claudeAi, type SampleFn } from "./ai";
import { choosePersistence, type ClaudeRuntime, type StorageKind } from "./persist";
import { PREVIEW_ORIGIN, PreviewServer } from "./server";
import { applyDoc, docBody, emptyState } from "./state";

const REMIND_EVERY_MS = 30_000;

let storage: StorageKind = "none";
let model = false;
/** Where this preview keeps the person's data (shown in the banner). */
export const previewStorage = (): StorageKind => storage;
/** Whether Claude is available as the model in this view (shown in the banner). */
export const previewHasModel = (): boolean => model;

function json(status: number, body: unknown): Response {
  return status === 204
    ? new Response(null, { status })
    : new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

/** The live event stream, in the same SSE format as the real API, resuming after Last-Event-ID. */
function eventStream(server: PreviewServer, req: Request, url: URL): Response {
  const after = Number(req.headers.get("Last-Event-ID") ?? url.searchParams.get("after") ?? 0) || 0;
  const encoder = new TextEncoder();
  let stop = (): void => undefined;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const send = (e: { seq: number }) => controller.enqueue(encoder.encode(`id: ${e.seq}\ndata: ${JSON.stringify(e)}\n\n`));
      for (const e of server.eventsAfter(after)) send(e);
      const off = server.onEvent(send);
      stop = () => {
        off();
        try {
          controller.close();
        } catch {
          // already closed
        }
      };
      req.signal.addEventListener("abort", () => stop(), { once: true });
    },
    cancel() {
      stop();
    },
  });
  return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
}

export async function installPreview(): Promise<void> {
  const runtime = (window as unknown as { claude?: ClaudeRuntime }).claude;
  const [persistence, sample] = await Promise.all([
    choosePersistence(runtime),
    runtime?.use ? (runtime.use("sample") as Promise<SampleFn | null>).catch(() => null) : Promise.resolve(null),
  ]);
  storage = persistence.kind;
  model = sample !== null;
  let loaded: Map<string, Record<string, unknown>> | null = null;
  try {
    loaded = await persistence.load();
  } catch (error) {
    console.error("NEXUS preview: could not load saved data", error);
  }
  const state = emptyState(new Date());
  for (const [key, body] of loaded ?? []) {
    try {
      applyDoc(state, key, body);
    } catch (error) {
      console.error(`NEXUS preview: skipped saved ${key}`, error);
    }
  }
  const server = new PreviewServer(state, () => new Date(), claudeAi(sample));
  if (!loaded) server.started();

  const save = (): void => {
    if (server.dirty.size === 0) return;
    const keys = [...server.dirty];
    server.dirty.clear();
    persistence.save(keys.map((k) => [k, docBody(server.state, k)]));
  };
  // Work that runs in the background (agents, objectives, workflows) saves as it goes.
  server.onChange(save);
  server.recover();

  const realFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const target = input instanceof Request ? input.url : String(input);
    if (!target.startsWith(PREVIEW_ORIGIN)) return realFetch(input, init);
    const req = new Request(input, init);
    const url = new URL(req.url);
    if (url.pathname === "/api/events/stream") return eventStream(server, req, url);
    const text = req.method === "GET" || req.method === "HEAD" ? "" : await req.text();
    let body: unknown;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        return json(422, { error: { code: "invalid_request", message: "The request body is not valid JSON." } });
      }
    }
    const reply = server.handle(req.method, url, body);
    save();
    return json(reply.status, reply.body);
  };

  server.remindDue();
  save();
  setInterval(() => {
    server.remindDue();
    save();
  }, REMIND_EVERY_MS);
}
