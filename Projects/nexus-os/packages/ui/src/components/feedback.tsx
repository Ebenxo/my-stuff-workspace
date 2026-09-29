import { AlertTriangle } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { Button } from "./button";
import { cn } from "./cn";

export function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "animate-[nx-pulse_1.6s_ease-in-out_infinite] rounded-md bg-raised",
        className,
      )}
      {...props}
    />
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 px-6 py-10 text-center", className)}>
      {icon ? <div className="mb-1 text-fg-subtle [&_svg]:size-6">{icon}</div> : null}
      <p className="text-sm font-medium text-fg">{title}</p>
      {description ? <p className="max-w-sm text-[13px] text-fg-muted">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  className,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn("flex flex-col items-center gap-2 px-6 py-8 text-center", className)}
    >
      <AlertTriangle className="size-5 text-danger" aria-hidden="true" />
      <p className="text-sm font-medium text-fg">{title}</p>
      {message ? <p className="max-w-md text-[13px] text-fg-muted">{message}</p> : null}
      {onRetry ? (
        <Button size="sm" onClick={onRetry} className="mt-1">
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded border border-line-strong bg-raised px-1 font-mono text-[11px] text-fg-muted",
        className,
      )}
    >
      {children}
    </kbd>
  );
}

export type StatusTone = "ok" | "warn" | "bad" | "idle" | "live";

const dot: Record<StatusTone, string> = {
  ok: "bg-success",
  warn: "bg-warning",
  bad: "bg-danger",
  idle: "bg-fg-subtle",
  live: "bg-accent-text animate-[nx-pulse_1.4s_ease-in-out_infinite]",
};

export function StatusDot({ tone, label }: { tone: StatusTone; label: string }) {
  return (
    <span className="inline-flex items-center" role="img" aria-label={label} title={label}>
      <span className={cn("size-2 rounded-full", dot[tone])} />
    </span>
  );
}
