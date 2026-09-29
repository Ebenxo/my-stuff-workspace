import { Button, Dialog, DialogContent } from "@nexus/ui";
import { Menu } from "lucide-react";
import { useState } from "react";
import { useLocation } from "react-router";
import { NotificationBell } from "../features/notifications/NotificationBell";
import { Logo } from "./Logo";
import { NavList } from "./Sidebar";

function titleFor(pathname: string): string {
  if (pathname === "/") return "Command Center";
  if (pathname.startsWith("/projects")) return pathname === "/projects" ? "Projects" : "Project";
  if (pathname.startsWith("/settings")) return "Settings";
  return "NEXUS";
}

export function Topbar() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b border-line bg-canvas px-3 md:px-4">
      <Dialog open={open} onOpenChange={setOpen}>
        <Button variant="ghost" size="icon-sm" className="md:hidden" aria-label="Open navigation" onClick={() => setOpen(true)}>
          <Menu />
        </Button>
        <DialogContent
          title="Navigation"
          className="left-0 top-0 h-full max-w-64 translate-x-0 translate-y-0 rounded-none border-y-0 border-l-0 p-0 pt-4"
        >
          <div className="px-4 pb-4">
            <Logo />
          </div>
          <NavList collapsed={false} onNavigate={() => setOpen(false)} />
        </DialogContent>
      </Dialog>
      <h1 className="text-sm font-medium text-fg">{titleFor(pathname)}</h1>
      <div className="ml-auto flex items-center gap-1">
        <NotificationBell />
      </div>
    </header>
  );
}
