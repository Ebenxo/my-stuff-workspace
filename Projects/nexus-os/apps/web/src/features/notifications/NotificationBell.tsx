import { formatRelativeTime } from "@nexus/shared";
import { Button, EmptyState, ErrorState, Popover, PopoverContent, PopoverTrigger, Skeleton } from "@nexus/ui";
import { Bell } from "lucide-react";
import { errorMessage, useMarkNotificationsRead, useNotifications, useUnreadCount } from "../../lib/queries";

export function NotificationBell() {
  const unread = useUnreadCount();
  const list = useNotifications();
  const mark = useMarkNotificationsRead();
  const count = unread.data?.count ?? 0;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={count ? `Notifications, ${count} unread` : "Notifications"}>
          <span className="relative">
            <Bell />
            {count > 0 ? (
              <span className="absolute -right-1.5 -top-1.5 grid size-4 place-items-center rounded-full bg-accent text-[10px] font-semibold text-accent-fg">
                {count > 9 ? "9+" : count}
              </span>
            ) : null}
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(22rem,calc(100vw-2rem))]">
          <div className="flex items-center justify-between border-b border-line px-3 py-2">
            <h2 className="text-[13px] font-medium">Notifications</h2>
            <Button
              size="sm"
              variant="ghost"
              disabled={count === 0}
              loading={mark.isPending}
              onClick={() => mark.mutate("all")}
            >
              Mark all read
            </Button>
          </div>
          <div className="max-h-80 overflow-y-auto">
            {list.isPending ? (
              <div className="space-y-2 p-3">
                <Skeleton className="h-10" />
                <Skeleton className="h-10" />
              </div>
            ) : list.isError ? (
              <ErrorState message={errorMessage(list.error)} onRetry={() => void list.refetch()} />
            ) : list.data.length === 0 ? (
              <EmptyState title="You're all caught up" description="Approvals, completed work and failures will show up here." />
            ) : (
              <ul>
                {list.data.map((n) => (
                  <li key={n.id} className="border-b border-line last:border-0">
                    <button
                      type="button"
                      onClick={() => !n.read_at && mark.mutate(n.id)}
                      className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-raised"
                    >
                      <span
                        className={`mt-1.5 size-2 shrink-0 rounded-full ${n.read_at ? "bg-transparent" : "bg-accent"}`}
                        aria-hidden="true"
                      />
                      <span className="min-w-0">
                        <span className="block truncate text-[13px] font-medium text-fg">{n.title}</span>
                        {n.body ? <span className="block truncate text-xs text-fg-muted">{n.body}</span> : null}
                        <span className="text-[11px] text-fg-subtle">{formatRelativeTime(n.created_at)}</span>
                        {!n.read_at ? <span className="sr-only"> unread</span> : null}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
      </PopoverContent>
    </Popover>
  );
}
