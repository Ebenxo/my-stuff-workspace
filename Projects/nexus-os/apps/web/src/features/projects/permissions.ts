import type { PermissionLevel } from "@nexus/schemas";

export const PERMISSION_COPY: Record<PermissionLevel, { label: string; help: string }> = {
  cautious: {
    label: "Cautious",
    help: "Asks before any change. Reading is automatic.",
  },
  balanced: {
    label: "Balanced",
    help: "Changes inside the project workspace are automatic. Anything riskier asks first.",
  },
  permissive: {
    label: "Permissive",
    help: "Also allows higher-risk actions without asking, except deletions, sending data out, other always-ask actions, and anything proposed after reading untrusted content.",
  },
};
