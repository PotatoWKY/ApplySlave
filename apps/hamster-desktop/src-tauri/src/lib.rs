mod backend;

use std::sync::Arc;

use backend::{PythonBackend, BACKEND_PORT};
use tauri::{Manager, RunEvent, WindowEvent};

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

    // Install a signal handler so Ctrl-C in `tauri dev`, SIGTERM from the
    // terminal, or a parent process death all clean up the Python child.
    // Tauri's RunEvent::Exit only fires on graceful window close, not on
    // signals.
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
            move |app| {
                // Treat "last window closed" as a request to quit the whole
                // app. By default on macOS the red × just hides the window
                // and keeps the process resident in the Dock, which is bad
                // for us — the backend owns ~2.3 GB of LLM weights, plus
                // the user's mental model is "closing the window quits
                // the app".
                let app_handle = app.handle().clone();
                if let Some(window) = app.get_webview_window("main") {
                    window.on_window_event(move |event| {
                        if matches!(event, WindowEvent::CloseRequested { .. }) {
                            log::info!(
                                "Main window close requested — quitting app"
                            );
                            app_handle.exit(0);
                        }
                    });
                }

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
                // Fires on Cmd-Q, "Quit Hamster" menu, app.exit(), or
                // the last window closing (because of our setup above).
                RunEvent::ExitRequested { .. } | RunEvent::Exit => {
                    log::info!("Exit event received — killing backend");
                    backend.kill();
                }
                _ => {}
            }
        });
}
