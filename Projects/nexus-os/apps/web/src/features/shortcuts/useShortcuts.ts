import { useEffect } from "react";
import { useNavigate } from "react-router";
import { useOverlays } from "../../stores/overlays";
import { useUi } from "../../stores/ui";
import { isTypingTarget, resolveKey, type ShortcutAction } from "./keys";

const CHORD_MS = 1200;

/** App-wide keyboard shortcuts (see keys.ts). Mounted once, by the app shell. */
export function useShortcuts(): void {
  const navigate = useNavigate();

  useEffect(() => {
    let pendingG = false;
    let timer: number | undefined;

    function perform(action: ShortcutAction) {
      const overlays = useOverlays.getState();
      const ui = useUi.getState();
      if (action === "palette") overlays.setPalette(!overlays.palette);
      else if (action === "shortcuts") overlays.setShortcuts(true);
      else if (action === "toggle-bottom") ui.setBottom(!ui.bottomOpen);
      else if (action === "toggle-activity") ui.setRight(!ui.rightOpen, "activity");
      else if (action === "search") {
        const box = document.getElementById("top-search");
        if (box && box.offsetParent !== null) box.focus();
        else void navigate("/search");
      } else if (action.startsWith("go:")) void navigate(action.slice(3));
    }

    function onKeyDown(e: KeyboardEvent) {
      if (e.defaultPrevented || e.isComposing) return;
      // Inside an open dialog only the modifier shortcuts apply (letters belong to the dialog).
      const typing = isTypingTarget(e.target) || document.querySelector('[role="dialog"]') !== null;
      const result = resolveKey(e, { pendingG, typing });
      window.clearTimeout(timer);
      pendingG = result.pendingG;
      if (pendingG) timer = window.setTimeout(() => (pendingG = false), CHORD_MS);
      if (!result.action) return;
      e.preventDefault();
      perform(result.action);
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.clearTimeout(timer);
    };
  }, [navigate]);
}
