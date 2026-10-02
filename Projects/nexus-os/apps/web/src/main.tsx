import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./index.css";

import { IS_PREVIEW } from "./preview/flag";

async function start(): Promise<void> {
  const container = document.getElementById("root");
  if (!container) throw new Error("Root element missing");
  if (IS_PREVIEW) {
    // No API behind the browser preview: answer it in the page before anything asks.
    const { installPreview } = await import("./preview/install");
    await installPreview();
  }
  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void start();
