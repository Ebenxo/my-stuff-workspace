import type { ComponentProps } from "react";
import { cn } from "./cn";

const field =
  "w-full rounded-md border border-control bg-canvas px-3 text-sm text-fg placeholder:text-fg-subtle " +
  "transition-colors hover:border-fg-subtle focus-visible:border-ring disabled:opacity-50";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(field, "h-9", className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(field, "min-h-20 resize-y py-2", className)} {...props} />;
}

export function Label({ className, ...props }: ComponentProps<"label">) {
  return <label className={cn("mb-1.5 block text-[13px] font-medium text-fg-muted", className)} {...props} />;
}

export function FieldError({ children }: { children?: React.ReactNode }) {
  return children ? (
    <p role="alert" className="mt-1.5 text-[13px] text-danger">
      {children}
    </p>
  ) : null;
}
