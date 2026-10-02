import { Spinner } from "@nexus/ui";
import { Outlet } from "react-router";
import { useEventStream } from "../features/events/useEventStream";
import { Onboarding } from "../features/onboarding/Onboarding";
import { CommandPalette } from "../features/palette/CommandPalette";
import { ShortcutsDialog } from "../features/shortcuts/ShortcutsDialog";
import { useShortcuts } from "../features/shortcuts/useShortcuts";
import { useSettings } from "../lib/queries";
import { IS_PREVIEW } from "../preview/flag";
import { PreviewBanner } from "../preview/PreviewBanner";
import { useUi } from "../stores/ui";
import { BottomPanel } from "./BottomPanel";
import { RightPanel } from "./RightPanel";
import { Sidebar } from "./Sidebar";
import { StatusBar } from "./StatusBar";
import { Topbar } from "./Topbar";

export function AppShell() {
  useEventStream();
  useShortcuts();
  const { rightOpen, bottomOpen } = useUi();
  const settings = useSettings();
  if (settings.isPending) {
    return (
      <div className="flex h-full items-center justify-center bg-canvas">
        <Spinner label="Starting NEXUS" />
      </div>
    );
  }
  // First run. (If settings cannot be read, the app still opens: its pages show the error.)
  if (settings.data && !settings.data.onboarding_completed) return <Onboarding settings={settings.data} />;
  return (
    <div className="flex h-full bg-canvas">
      <a
        href="#main"
        onClick={(e) => {
          // Focus the page directly: with hash-based routes (the browser preview) "#main" would be a route.
          e.preventDefault();
          document.getElementById("main")?.focus();
        }}
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-1.5 focus:text-accent-fg"
      >
        Skip to content
      </a>
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        {IS_PREVIEW ? <PreviewBanner /> : null}
        <Topbar />
        <div className="flex min-h-0 flex-1">
          <main id="main" tabIndex={-1} className="min-w-0 flex-1 overflow-y-auto focus-visible:outline-none">
            <Outlet />
          </main>
          {rightOpen ? <RightPanel /> : null}
        </div>
        {bottomOpen ? <BottomPanel /> : null}
        <StatusBar />
      </div>
      <CommandPalette />
      <ShortcutsDialog />
    </div>
  );
}
