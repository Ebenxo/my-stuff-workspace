import { Tooltip, cn } from "@nexus/ui";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { NavLink } from "react-router";
import { useUi } from "../stores/ui";
import { Logo } from "./Logo";
import { NAV_ITEMS } from "./nav";

export function NavList({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  return (
    <nav aria-label="Primary" className="flex flex-col gap-0.5 px-2">
      {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => {
        const link = (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "flex h-9 items-center gap-3 rounded-md px-2.5 text-[13px] font-medium transition-colors",
                collapsed && "justify-center px-0",
                isActive
                  ? "bg-raised text-fg shadow-[inset_2px_0_0_var(--nx-accent)]"
                  : "text-fg-muted hover:bg-raised/60 hover:text-fg",
              )
            }
          >
            <Icon className="size-4 shrink-0" aria-hidden="true" />
            {collapsed ? <span className="sr-only">{label}</span> : <span>{label}</span>}
          </NavLink>
        );
        return collapsed ? (
          <Tooltip key={to} label={label}>
            {link}
          </Tooltip>
        ) : (
          link
        );
      })}
    </nav>
  );
}

export function Sidebar() {
  const collapsed = useUi((s) => s.sidebarCollapsed);
  const toggle = useUi((s) => s.toggleSidebar);
  return (
    <aside
      className={cn(
        "hidden shrink-0 flex-col border-r border-line bg-surface transition-[width] duration-200 md:flex",
        collapsed ? "w-14" : "w-56",
      )}
    >
      <div className={cn("flex h-12 items-center border-b border-line", collapsed ? "justify-center" : "px-4")}>
        <Logo collapsed={collapsed} />
      </div>
      <div className="flex-1 overflow-y-auto py-3">
        <NavList collapsed={collapsed} />
      </div>
      <div className="border-t border-line p-2">
        <button
          type="button"
          onClick={toggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "flex h-8 w-full items-center gap-2 rounded-md px-2.5 text-[13px] text-fg-subtle transition-colors hover:bg-raised hover:text-fg",
            collapsed && "justify-center px-0",
          )}
        >
          {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
          {collapsed ? null : <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
