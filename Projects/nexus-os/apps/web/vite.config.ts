import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const apiTarget = process.env["NEXUS_API_URL"] ?? "http://127.0.0.1:8765";
/** The browser preview answers the API in the page; its requests go to this made-up origin. */
const PREVIEW_ORIGIN = "https://nexus.preview";
// The token never enters the browser bundle in development: the dev server adds it to proxied requests.
const apiToken = process.env["NEXUS_API_TOKEN"];

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  // `vite build --mode browser-preview`: one self-contained page (see scripts/build_preview.py).
  ...(mode === "browser-preview"
    ? {
        base: "./",
        define: {
          "import.meta.env.VITE_NEXUS_PREVIEW": JSON.stringify("1"),
          "import.meta.env.VITE_NEXUS_API_URL": JSON.stringify(PREVIEW_ORIGIN),
        },
      }
    : {}),
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => {
            if (apiToken) proxyReq.setHeader("Authorization", `Bearer ${apiToken}`);
          });
        },
      },
    },
  },
  build:
    mode === "browser-preview"
      ? {
          outDir: "dist-preview",
          sourcemap: false,
          target: "es2022",
          assetsInlineLimit: 100_000_000, // fonts and images go inside the page
          rollupOptions: { output: { inlineDynamicImports: true } },
        }
      : { sourcemap: true, target: "es2022" },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
}));
