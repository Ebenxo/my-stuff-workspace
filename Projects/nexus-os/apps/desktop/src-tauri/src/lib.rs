//! NEXUS OS desktop shell.
//!
//! UNVERIFIED: this glue could not be compiled in the build container (no webkit2gtk/GTK).
//! The process-supervision logic it uses lives in `nexus-sidecar`, which is unit-tested.
//!
//! Flow: pick a free loopback port and a random per-launch token -> start the Python API with
//! them -> wait until it answers -> open the window with `window.__NEXUS__` injected so the web
//! app knows where the API is. The token exists only in memory and in that one window.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Duration;

use nexus_sidecar::{free_port, new_token, Sidecar, SidecarConfig};
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

struct ApiState(Mutex<Option<Sidecar>>);

/// Production builds set NEXUS_API_BIN to the bundled API executable (see apps/desktop/README.md).
/// Development runs the API from the repository with `uv`.
fn api_command() -> (Vec<String>, Option<PathBuf>) {
    if let Ok(bin) = std::env::var("NEXUS_API_BIN") {
        return (vec![bin, "serve".into()], None);
    }
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..");
    let command = ["uv", "run", "--project", "services/api", "nexus", "serve"]
        .iter()
        .map(|s| s.to_string())
        .collect();
    (command, Some(repo_root))
}

pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let home = app.path().app_data_dir()?;
            let (command, cwd) = api_command();
            let sidecar = Sidecar::start(SidecarConfig {
                command,
                cwd,
                home,
                port: free_port()?,
                token: new_token()?,
                extra_env: HashMap::new(),
                startup_timeout: Duration::from_secs(45),
            })?;
            let init_script = sidecar.init_script();
            app.manage(ApiState(Mutex::new(Some(sidecar))));

            WebviewWindowBuilder::new(app, "main", WebviewUrl::default())
                .title("NEXUS OS")
                .inner_size(1440.0, 900.0)
                .min_inner_size(960.0, 640.0)
                .initialization_script(&init_script)
                .build()?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.try_state::<ApiState>() {
                    if let Ok(mut guard) = state.0.lock() {
                        // Dropping the sidecar stops the API process.
                        guard.take();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running NEXUS OS");
}
