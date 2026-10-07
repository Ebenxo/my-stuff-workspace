import { Info } from "lucide-react";
import { previewHasModel, previewStorage } from "./install";

const SAVED = {
  account: "Saved to your Claude account; only you can see it.",
  browser: "Saved in this browser.",
  none: "Not saved: storage is not available here.",
} as const;

/** Says plainly what the browser preview can and cannot do. */
export function PreviewBanner() {
  const model = previewHasModel();
  return (
    <div role="note" className="flex items-start gap-2 border-b border-accent/30 bg-accent/10 px-4 py-2 text-[13px] text-fg">
      <Info className="mt-0.5 size-4 shrink-0 text-accent-text" aria-hidden="true" />
      <p>
        <strong className="font-medium">Browser preview.</strong>{" "}
        {model
          ? "Claude, on your own claude.ai account, is the model: objectives, agents and workflows run here (you are asked once to allow it)."
          : "No model is available in this view, so objectives, agents and workflow agent steps cannot run; open it on claude.ai to use Claude."}{" "}
        {SAVED[previewStorage()]}{" "}
        <span className="hidden text-fg-muted sm:inline">
          Agents here cannot browse the web, run code or touch your computer; tools, schedules, MCP servers and other AI providers need
          NEXUS running on your computer.
        </span>
      </p>
    </div>
  );
}
