import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const apiTarget = process.env["NEXUS_API_URL"] ?? "http://127.0.0.1:8765";
// The token never enters the browser bundle in development: the dev server adds it to proxied requests.
const apiToken = process.env["NEXUS_API_TOKEN"];

export default defineConfig({
  plugins: [react(), tailwindcss()],
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
  build: { sourcemap: true, target: "es2022" },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
