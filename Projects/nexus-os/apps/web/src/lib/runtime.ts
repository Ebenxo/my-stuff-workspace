import type { ApiConfig } from "@nexus/shared";

declare global {
  interface Window {
    /** Injected by the Tauri shell: the sidecar's URL and per-launch token. */
    __NEXUS__?: { baseUrl: string; token: string };
  }
}

/**
 * Where to reach the local API.
 * - Desktop: the shell injects window.__NEXUS__.
 * - Dev: same-origin `/api`; the Vite proxy adds the token so it never ships in the bundle.
 */
export function getRuntimeConfig(): ApiConfig {
  if (typeof window !== "undefined" && window.__NEXUS__) {
    return { baseUrl: window.__NEXUS__.baseUrl, token: window.__NEXUS__.token };
  }
  const env = import.meta.env as Record<string, string | undefined>;
  return { baseUrl: env["VITE_NEXUS_API_URL"] ?? "", token: env["VITE_NEXUS_API_TOKEN"] };
}
