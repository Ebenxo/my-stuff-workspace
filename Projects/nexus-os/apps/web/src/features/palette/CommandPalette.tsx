import { Dialog, DialogContent, Kbd, cn, toast } from "@nexus/ui";
import { CornerDownLeft, Search } from "lucide-react";
import { useDeferredValue, useMemo, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router";
import { useUniversalSearch } from "../../lib/memoryQueries";
import { useStartDemo } from "../../lib/objectiveQueries";
import { errorMessage, useProjects } from "../../lib/queries";
import { useOverlays } from "../../stores/overlays";
import { useUi } from "../../stores/ui";
import { searchHref } from "../memory/format";
import { paletteItems, type PaletteItem } from "./commands";

function PaletteBody({ onRun }: { onRun: (item: PaletteItem) => void }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const projects = useProjects();
  const deferred = useDeferredValue(query);
  const search = useUniversalSearch(deferred.trim().length >= 2 ? deferred : "");
  // Commands rank on what is typed right now (Enter straight after typing must pick from these);
  // only the search request waits for typing to settle.
  const items = useMemo(() => {
    const hits = (search.data?.hits ?? []).map((h) => ({ kind: h.kind, id: h.id, title: h.title, href: searchHref(h) }));
    return paletteItems(query, projects.data ?? [], query.trim().length >= 2 ? hits : []);
  }, [query, projects.data, search.data]);
  const current = Math.min(active, Math.max(0, items.length - 1));

  const groups = useMemo(() => {
    const out: { name: string; items: { item: PaletteItem; index: number }[] }[] = [];
    items.forEach((item, index) => {
      const last = out.at(-1);
      if (last && last.name === item.group) last.items.push({ item, index });
      else out.push({ name: item.group, items: [{ item, index }] });
    });
    return out;
  }, [items]);

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!items.length) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const step = e.key === "ArrowDown" ? 1 : -1;
      const next = (current + step + items.length) % items.length;
      setActive(next);
      document.getElementById(`palette-opt-${next}`)?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = items[current];
      if (item) onRun(item);
    }
  }

  return (
    <div>
      <div className="flex items-center gap-2 border-b border-line px-4">
        <Search className="size-4 shrink-0 text-fg-subtle" aria-hidden="true" />
        <input
          autoFocus
          role="combobox"
          aria-expanded="true"
          aria-controls="palette-list"
          aria-activedescendant={items.length ? `palette-opt-${current}` : undefined}
          aria-label="Type a command, a page or something to find"
          placeholder="Type a command, a page or something to find…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={onKeyDown}
          className="h-12 min-w-0 flex-1 bg-transparent text-sm text-fg placeholder:text-fg-subtle focus-visible:outline-none"
          spellCheck={false}
          autoComplete="off"
        />
      </div>
      <div id="palette-list" role="listbox" aria-label="Results" className="max-h-[min(60vh,26rem)] overflow-y-auto p-2">
        {items.length === 0 ? <p className="px-3 py-6 text-center text-[13px] text-fg-muted">Nothing matches.</p> : null}
        {groups.map((g) => (
          <div key={`${g.name}-${g.items[0]?.index}`} role="group" aria-label={g.name} className="mb-1">
            <p className="px-3 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-fg-subtle" aria-hidden="true">
              {g.name}
            </p>
            {g.items.map(({ item, index }) => (
              <div
                key={item.id}
                id={`palette-opt-${index}`}
                role="option"
                aria-selected={index === current}
                onMouseMove={() => index !== current && setActive(index)}
                onClick={() => onRun(item)}
                className={cn(
                  "flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-[13px]",
                  index === current ? "bg-accent/15 text-fg" : "text-fg-muted",
                )}
              >
                <span className="min-w-0 flex-1 truncate">{item.label}</span>
                {item.hint ? <span className="shrink-0 text-xs text-fg-subtle">{item.hint}</span> : null}
                {index === current ? <CornerDownLeft className="size-3.5 shrink-0 text-fg-subtle" aria-hidden="true" /> : null}
              </div>
            ))}
          </div>
        ))}
      </div>
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line px-4 py-2 text-[11px] text-fg-subtle">
        <span>
          <Kbd>↑</Kbd> <Kbd>↓</Kbd> move
        </span>
        <span>
          <Kbd>Enter</Kbd> choose
        </span>
        <span>
          <Kbd>Esc</Kbd> close
        </span>
      </p>
    </div>
  );
}

/** Ctrl/⌘+K: go anywhere or do anything by typing. Always mounted, so actions finish after it closes. */
export function CommandPalette() {
  const open = useOverlays((s) => s.palette);
  const setPalette = useOverlays((s) => s.setPalette);
  const setShortcuts = useOverlays((s) => s.setShortcuts);
  const navigate = useNavigate();
  const demo = useStartDemo();

  function run(item: PaletteItem) {
    setPalette(false);
    if (item.to) {
      void navigate(item.to);
      return;
    }
    const ui = useUi.getState();
    switch (item.action) {
      case "demo":
        toast.info("Setting up the demo…");
        demo.mutate(undefined, {
          onSuccess: (o) => void navigate(`/objectives/${o.id}`),
          onError: (e) => toast.error(errorMessage(e)),
        });
        return;
      case "toggle-activity":
        ui.setRight(!ui.rightOpen, "activity");
        return;
      case "toggle-bottom":
        ui.setBottom(!ui.bottomOpen);
        return;
      case "terminal":
        ui.setBottom(true, "terminal");
        window.setTimeout(() => document.getElementById("nexus-term")?.focus(), 50);
        return;
      case "shortcuts":
        setShortcuts(true);
        return;
      default:
        return;
    }
  }

  return (
    <Dialog open={open} onOpenChange={setPalette}>
      <DialogContent title="Command palette" hideTitle className="top-[12vh] max-w-xl translate-y-0 p-0">
        {open ? <PaletteBody onRun={run} /> : null}
      </DialogContent>
    </Dialog>
  );
}
