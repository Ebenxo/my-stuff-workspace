import { unwrap } from "@nexus/shared";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../lib/api";
import { errorMessage } from "../lib/queries";
import { useEvents } from "../stores/events";

interface Line {
  id: number;
  kind: "in" | "out" | "err";
  text: string;
}

const HELP = [
  "NEXUS command line (not a shell: agents and you act only through the app).",
  "  help              show this help",
  "  status            system health summary",
  "  events [n]        show the last n events (default 10)",
  "  verify            verify the audit-log hash chain",
  "  clear             clear this screen",
];

let counter = 0;
const line = (kind: Line["kind"], text: string): Line => ({ id: ++counter, kind, text });

export function Terminal() {
  const [lines, setLines] = useState<Line[]>(() => [line("out", "NEXUS terminal. Type `help`.")]);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [lines]);

  const push = (...next: Line[]) => setLines((l) => [...l, ...next]);

  async function run(raw: string) {
    const [cmd = "", ...args] = raw.trim().replace(/^\//, "").split(/\s+/);
    switch (cmd) {
      case "":
        return;
      case "help":
        return push(...HELP.map((t) => line("out", t)));
      case "clear":
        return setLines([]);
      case "status": {
        const h = await unwrap(api.GET("/api/health"));
        return push(
          line("out", `overall: ${h.status} (v${h.version})`),
          ...h.checks.map((c) => line(c.status === "ok" ? "out" : "err", `  ${c.label.padEnd(18)} ${c.status.padEnd(9)} ${c.detail}`)),
        );
      }
      case "events": {
        const n = Math.min(Math.max(Number.parseInt(args[0] ?? "10", 10) || 10, 1), 50);
        const recent = useEvents.getState().events.slice(-n);
        return push(...(recent.length ? recent.map((e) => line("out", `#${e.seq} ${new Date(e.ts).toLocaleTimeString([], { hour12: false })} ${e.type}`)) : [line("out", "no events yet")]));
      }
      case "verify": {
        const v = await unwrap(api.GET("/api/events/verify", { params: { query: {} } }));
        return push(
          v.ok
            ? line("out", `audit log OK: ${v.events_checked} events in ${v.chains_checked} chain(s)`)
            : line("err", `audit log BROKEN at event #${v.first_bad_seq}: ${v.detail ?? ""}`),
        );
      }
      default:
        return push(line("err", `unknown command: ${cmd}. Try \`help\`.`));
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const raw = value;
    setValue("");
    push(line("in", raw));
    setBusy(true);
    try {
      await run(raw);
    } catch (error) {
      push(line("err", errorMessage(error)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col font-mono text-xs">
      <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto px-3 py-2" role="log" aria-live="polite">
        {lines.map((l) => (
          <div
            key={l.id}
            className={
              l.kind === "in" ? "text-fg" : l.kind === "err" ? "whitespace-pre-wrap text-danger" : "whitespace-pre-wrap text-fg-muted"
            }
          >
            {l.kind === "in" ? <span className="mr-2 text-accent-text">nexus&gt;</span> : null}
            {l.text}
          </div>
        ))}
      </div>
      <form onSubmit={(e) => void onSubmit(e)} className="flex items-center gap-2 border-t border-line px-3 py-1.5">
        <label htmlFor="nexus-term" className="text-accent-text">
          nexus&gt;
        </label>
        <input
          id="nexus-term"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={busy}
          autoComplete="off"
          spellCheck={false}
          className="min-w-0 flex-1 bg-transparent text-fg placeholder:text-fg-subtle focus-visible:outline-none"
          placeholder="type a command"
        />
      </form>
    </div>
  );
}
