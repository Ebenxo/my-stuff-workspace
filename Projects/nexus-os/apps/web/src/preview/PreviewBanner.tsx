import { Info } from "lucide-react";
import { previewStorage } from "./install";

const SAVED = {
  account: "Saved to your Claude account; only you can see it.",
  browser: "Saved in this browser.",
  none: "Not saved: storage is not available here.",
} as const;

/** Says plainly what the browser preview can and cannot do. */
export function PreviewBanner() {
  return (
    <div role="note" className="flex items-start gap-2 border-b border-accent/30 bg-accent/10 px-4 py-2 text-[13px] text-fg">
      <Info className="mt-0.5 size-4 shrink-0 text-accent-text" aria-hidden="true" />
      <p>
        <strong className="font-medium">Browser preview.</strong> The Timeline, Ideas &amp; notes, projects and settings work here. {SAVED[previewStorage()]}{" "}
        <span className="text-fg-muted">Agents, AI models and workflows need NEXUS running on your computer.</span>
      </p>
    </div>
  );
}
