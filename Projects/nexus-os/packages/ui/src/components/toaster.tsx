import { Toaster as Sonner, toast } from "sonner";

export { toast };

export function Toaster() {
  return (
    <Sonner
      theme="dark"
      position="bottom-right"
      toastOptions={{
        style: {
          background: "var(--nx-overlay)",
          border: "1px solid var(--nx-line-strong)",
          color: "var(--nx-fg)",
        },
      }}
    />
  );
}
