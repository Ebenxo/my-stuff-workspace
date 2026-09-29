# NEXUS OS desktop shell (Tauri 2)

Wraps the web app (`apps/web`) in a native window and runs the Python API as a supervised child process.

## Status — read this first

| Part | Status |
|---|---|
| `sidecar/` (spawn API, free port, random token, health wait, shutdown, JS-safe init script) | **Built and unit-tested** (`pnpm --filter @nexus/desktop test:sidecar`, 8 tests) |
| `src-tauri/` (window, injection, lifecycle glue) | **Written, not compiled.** The build container has no webkit2gtk/GTK, so `cargo check` cannot run here. Syntax is checked with `rustfmt`; API usage has not been exercised |
| Icons | Generated with `tauri icon` from the logo |
| Production packaging of the Python API | **Not done.** See below |
| OS keychain integration | Handled by the Python API (`keyring`); not exercised on Windows/macOS here |

## How it works

1. `src-tauri/src/lib.rs` picks a free loopback port and a random 256-bit token (`nexus-sidecar`), and starts the API with `NEXUS_PORT`, `NEXUS_API_TOKEN`, `NEXUS_HOME` (the OS app-data dir).
2. It waits for `GET /api/health/ping`, aborting cleanly if the process dies or times out.
3. It opens the window with an initialization script setting `window.__NEXUS__ = { baseUrl, token }`. The web app reads it in `apps/web/src/lib/runtime.ts`. The token is never written to disk by the shell and never appears in the bundle.
4. When the window is destroyed the sidecar is dropped, which stops the API.

The API only accepts the `Host` it was told about and the Tauri origins (`tauri://localhost`, `http://tauri.localhost`), and requires the bearer token on every call except `/api/health/ping`.

## Run in development

Prerequisites: Rust toolchain, Tauri 2 system dependencies for your OS (<https://v2.tauri.app/start/prerequisites/>), `uv`, `pnpm`.

```bash
pnpm install
pnpm --filter @nexus/desktop dev      # runs the web dev server and starts the API with uv
```

## Production packaging (open work)

`NEXUS_API_BIN` tells the shell to run a bundled API executable instead of `uv`. Producing that executable (PyInstaller or `uv`-based embedding, then registering it as a Tauri `externalBin` per target triple) is the remaining packaging task; until then the desktop shell is a development host. Track it in `docs/ROADMAP.md`.

## Security notes

- Capabilities are minimal (`core:default` only): the window has no shell, filesystem or opener access. All side effects go through the API's permission pipeline.
- The CSP limits network access to the app itself and `http://127.0.0.1:*`.
