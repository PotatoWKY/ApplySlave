mod backend;

use std::sync::Arc;

use backend::{PythonBackend, BACKEND_PORT};
use tauri::RunEvent;

/// Exposed to the frontend so JS knows where the backend lives without
/// duplicating the port constant.
#[tauri::command]
fn backend_port() -> u16 {
    BACKEND_PORT
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Route log::* through the standard env_logger so stderr has timestamps
    // and levels. RUST_LOG=info is the default when nothing is set.
    let _ = env_logger::Builder::from_env(
        env_logger::Env::default().default_filter_or("info"),
    )
    .try_init();

    let backend_handle = Arc::new(PythonBackend::new());

    // Install a signal handler so Ctrl-C in `tauri dev` cleans up the
    // Python child. Tauri's RunEvent::Exit only fires on graceful window
    // close, not on SIGINT/SIGTERM.
    {
        let backend = Arc::clone(&backend_handle);
        let _ = ctrlc::set_handler(move || {
            log::info!("Received interrupt, shutting down backend");
            backend.kill();
            std::process::exit(0);
        });
    }

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(Arc::clone(&backend_handle))
        .setup({
            let backend = Arc::clone(&backend_handle);
            move |_app| {
                if let Err(error) = backend.spawn() {
                    log::error!("Failed to start Python backend: {}", error);
                    // Don't prevent the UI from opening — the health pill
                    // will show "offline" and the user sees a readable
                    // error in the dev console.
                }
                Ok(())
            }
        })
        .invoke_handler(tauri::generate_handler![backend_port])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run({
            let backend = Arc::clone(&backend_handle);
            move |_app_handle, event| match event {
                RunEvent::ExitRequested { .. } | RunEvent::Exit => {
                    backend.kill();
                }
                _ => {}
            }
        });
}
