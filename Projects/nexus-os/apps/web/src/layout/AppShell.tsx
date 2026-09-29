import { Outlet } from "react-router";
import { useEventStream } from "../features/events/useEventStream";
import { useUi } from "../stores/ui";
import { BottomPanel } from "./BottomPanel";
import { RightPanel } from "./RightPanel";
import { Sidebar } from "./Sidebar";
import { StatusBar } from "./StatusBar";
import { Topbar } from "./Topbar";

export function AppShell() {
  useEventStream();
  const { rightOpen, bottomOpen } = useUi();
  return (
    <div className="flex h-full bg-canvas">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-1.5 focus:text-accent-fg"
      >
        Skip to content
      </a>
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
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
    </div>
  );
}
