import { Dialog, DialogContent, Kbd } from "@nexus/ui";
import { useMemo } from "react";
import { useOverlays } from "../../stores/overlays";
import { isMac, shortcutList } from "./keys";

export function ShortcutsDialog() {
  const open = useOverlays((s) => s.shortcuts);
  const setShortcuts = useOverlays((s) => s.setShortcuts);
  const groups = useMemo(() => shortcutList(isMac()), []);
  return (
    <Dialog open={open} onOpenChange={setShortcuts}>
      <DialogContent title="Keyboard shortcuts" description="Letters work when you are not typing in a field." className="max-w-lg">
        <div className="max-h-[65vh] space-y-5 overflow-y-auto pr-1">
          {groups.map((g) => (
            <section key={g.group}>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-fg-subtle">{g.group}</h3>
              <dl className="space-y-1.5">
                {g.items.map((s) => (
                  <div key={s.label} className="flex items-center gap-3 text-[13px]">
                    <dt className="flex shrink-0 items-center gap-1">
                      {s.keys.map((k, i) => (
                        <Kbd key={`${k}-${i}`}>{k}</Kbd>
                      ))}
                    </dt>
                    <dd className="text-fg-muted">{s.label}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
