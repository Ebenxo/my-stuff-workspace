import { Button, Dialog, DialogContent } from "@nexus/ui";
import { Menu, Search } from "lucide-react";
import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { NotificationBell } from "../features/notifications/NotificationBell";
import { Logo } from "./Logo";
import { NavList } from "./Sidebar";

function titleFor(pathname: string): string {
  if (pathname === "/") return "Command Center";
  if (pathname.startsWith("/projects")) return pathname === "/projects" ? "Projects" : "Project";
  if (pathname.startsWith("/settings")) return "Settings";
  if (pathname.startsWith("/agents") || pathname.startsWith("/runs")) return "Agents";
  if (pathname.startsWith("/objectives")) return "Objective";
  if (pathname.startsWith("/approvals")) return "Approvals";
  if (pathname.startsWith("/memory")) return "Memory";
  if (pathname.startsWith("/search")) return "Search";
  return "NEXUS";
}

/** The app-wide search box. It opens the Search page, which searches everything. */
function TopSearch() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  return (
    <form
      role="search"
      className="relative hidden w-64 md:block"
      onSubmit={(e) => {
        e.preventDefault();
        if (!text.trim()) return;
        void navigate(`/search?q=${encodeURIComponent(text.trim())}`);
        setText("");
      }}
    >
      <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-fg-subtle" aria-hidden="true" />
      <label htmlFor="top-search" className="sr-only">
        Search everything
      </label>
      <input
        id="top-search"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Search…"
        className="h-8 w-full rounded-md border border-line bg-surface pl-8 pr-2 text-[13px] text-fg placeholder:text-fg-subtle focus-visible:outline-2 focus-visible:outline-ring"
      />
    </form>
  );
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
        <TopSearch />
        <Button asChild variant="ghost" size="icon-sm" className="md:hidden" aria-label="Search">
          <Link to="/search">
            <Search />
          </Link>
        </Button>
        <NotificationBell />
      </div>
    </header>
  );
}
