import { EmptyState, Tabs, TabsContent, TabsList, TabsTrigger } from "@nexus/ui";
import { ChevronDown, TerminalSquare } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import { ActivityList } from "../features/events/ActivityList";
import { isErrorEvent } from "../features/events/describe";
import { ToolCallList } from "../features/tools/ToolCallList";
import { useEvents } from "../stores/events";
import { useUi, type BottomTab } from "../stores/ui";
import { Terminal } from "./Terminal";

function Feed({ errorsOnly }: { errorsOnly?: boolean }) {
  const events = useEvents((s) => s.events);
  const shown = useMemo(() => (errorsOnly ? events.filter(isErrorEvent) : events), [events, errorsOnly]);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [shown.length]);
  return (
    <div ref={ref} className="h-full overflow-y-auto">
      {shown.length === 0 ? (
        <EmptyState title={errorsOnly ? "No errors" : "No events yet"} description={errorsOnly ? "Failures and denied actions appear here." : undefined} />
      ) : (
        <ActivityList events={shown} />
      )}
    </div>
  );
}

export function BottomPanel() {
  const { bottomTab, bottomHeight, setBottom, setBottomHeight } = useUi();

  function startResize(e: React.PointerEvent<HTMLDivElement>) {
    e.preventDefault();
    const startY = e.clientY;
    const startH = bottomHeight;
    const move = (ev: PointerEvent) => setBottomHeight(startH + (startY - ev.clientY));
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  return (
    <section aria-label="Bottom panel" style={{ height: bottomHeight }} className="flex shrink-0 flex-col border-t border-line bg-surface">
      <div
        role="separator"
        aria-orientation="horizontal"
        aria-label="Resize panel"
        tabIndex={0}
        onPointerDown={startResize}
        onKeyDown={(e) => {
          if (e.key === "ArrowUp") setBottomHeight(bottomHeight + 24);
          if (e.key === "ArrowDown") setBottomHeight(bottomHeight - 24);
        }}
        className="h-1 shrink-0 cursor-row-resize bg-transparent transition-colors hover:bg-accent/40 focus-visible:bg-accent/60"
      />
      <Tabs value={bottomTab} onValueChange={(v) => setBottom(true, v as BottomTab)} className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-line pr-2">
          <TabsList className="border-b-0">
            <TabsTrigger value="events">Events</TabsTrigger>
            <TabsTrigger value="tools">Tools</TabsTrigger>
            <TabsTrigger value="errors">Errors</TabsTrigger>
            <TabsTrigger value="terminal">
              <span className="inline-flex items-center gap-1.5">
                <TerminalSquare className="size-3.5" aria-hidden="true" />
                Terminal
              </span>
            </TabsTrigger>
          </TabsList>
          <button
            type="button"
            aria-label="Close bottom panel"
            onClick={() => setBottom(false)}
            className="rounded-md p-1.5 text-fg-subtle transition-colors hover:bg-raised hover:text-fg"
          >
            <ChevronDown className="size-4" />
          </button>
        </div>
        <TabsContent value="events" className="min-h-0 flex-1">
          <Feed />
        </TabsContent>
        <TabsContent value="tools" className="min-h-0 flex-1 overflow-y-auto">
          <ToolCallList limit={60} />
        </TabsContent>
        <TabsContent value="errors" className="min-h-0 flex-1">
          <Feed errorsOnly />
        </TabsContent>
        <TabsContent value="terminal" className="min-h-0 flex-1">
          <Terminal />
        </TabsContent>
      </Tabs>
    </section>
  );
}
