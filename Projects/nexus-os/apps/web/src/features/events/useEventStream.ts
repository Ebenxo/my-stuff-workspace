import { parseEventRecord } from "@nexus/schemas";
import { authHeaders, streamEvents, unwrap } from "@nexus/shared";
import { toast } from "@nexus/ui";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, runtimeConfig } from "../../lib/api";
import { useEvents } from "../../stores/events";

const INVALIDATIONS: [RegExp, string[][]][] = [
  [/^PROJECT_/, [["projects"], ["project"]]],
  [/^(CONVERSATION|MESSAGE)_/, [["conversations"], ["messages"]]],
  [/^NOTIFICATION_/, [["notifications"]]],
  [/^SETTINGS_/, [["settings"], ["tools"]]],
  [/^SYSTEM_/, [["health"]]],
  [/^AGENT_/, [["runs"], ["run"], ["agents"]]],
  [/^(TOOL_|POLICY_|SECURITY_)/, [["tool-calls"], ["run"]]],
  [/^APPROVAL_/, [["approvals"], ["approval-grants"], ["run"], ["runs"], ["tool-calls"]]],
  [/^ARTIFACT_/, [["artifacts"], ["artifact"], ["artifact-versions"]]],
  [/^FILE_/, [["files"], ["file"]]],
];

/** A tool can offer text to copy. Nothing is copied until the person clicks: browsers need a user gesture. */
function offerClipboard(payload: Record<string, unknown>): void {
  const text = typeof payload["text"] === "string" ? payload["text"] : "";
  if (!text) return;
  const label = typeof payload["label"] === "string" && payload["label"] ? payload["label"] : "Copy text";
  toast(label, {
    description: text.length > 80 ? `${text.slice(0, 80)}…` : text,
    duration: 30_000,
    action: {
      label: "Copy",
      onClick: () => {
        navigator.clipboard.writeText(text).then(
          () => toast.success("Copied"),
          () => toast.error("Couldn’t copy. Select the text and copy it yourself."),
        );
      },
    },
  });
}

function makeInvalidator(qc: QueryClient) {
  const pending = new Set<string>();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const flush = () => {
    timer = undefined;
    for (const key of pending) void qc.invalidateQueries({ queryKey: JSON.parse(key) as string[] });
    pending.clear();
  };
  return {
    note(type: string) {
      for (const [re, keys] of INVALIDATIONS) {
        if (re.test(type)) for (const k of keys) pending.add(JSON.stringify(k));
      }
      if (pending.size && timer === undefined) timer = setTimeout(flush, 150);
    },
    dispose() {
      if (timer !== undefined) clearTimeout(timer);
    },
  };
}

/** Connects once for the whole app: prefill recent history, then tail live events with resume. */
export function useEventStream(): void {
  const qc = useQueryClient();
  useEffect(() => {
    let stop: (() => void) | undefined;
    let cancelled = false;
    const invalidator = makeInvalidator(qc);
    const { add, setStatus } = useEvents.getState();

    void (async () => {
      let startAfter = 0;
      try {
        const history = await unwrap(
          api.GET("/api/events", { params: { query: { newest_first: true, limit: 100 } } }),
        );
        const parsed = history
          .map((h) => parseEventRecord(h))
          .filter((e): e is NonNullable<typeof e> => e !== null)
          .reverse();
        add(parsed);
        startAfter = parsed[parsed.length - 1]?.seq ?? 0;
      } catch {
        // The stream below reports connection problems; history is best-effort.
      }
      if (cancelled) return;
      stop = streamEvents({
        url: `${runtimeConfig.baseUrl}/api/events/stream`,
        headers: authHeaders(runtimeConfig.token),
        lastEventId: String(startAfter),
        onStatus: setStatus,
        onMessage: (msg) => {
          if (msg.event === "resync") return;
          try {
            const record = parseEventRecord(JSON.parse(msg.data));
            if (!record) return;
            add([record]);
            invalidator.note(record.type);
            if (record.type === "CLIPBOARD_REQUEST") offerClipboard(record.payload);
          } catch {
            // A malformed frame is dropped; the audit log remains the source of truth.
          }
        },
      });
    })();

    return () => {
      cancelled = true;
      stop?.();
      invalidator.dispose();
    };
  }, [qc]);
}
