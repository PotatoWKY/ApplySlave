//! Manage the Python backend subprocess from the Tauri shell.
//!
//! In dev mode we invoke `uv run applyslave-backend` from the workspace root,
//! which uses the already-synced venv. In a packaged build we'll instead
//! point at the bundled Python runtime + site-packages under the Resources
//! dir. That bundled path is left as a TODO — the dev path is what we run
//! day to day, and the same shape of Command + wait-for-health will be
//! reused once the bundle exists.

use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

pub const BACKEND_PORT: u16 = 8765;
const HEALTH_DEADLINE_SECS: u64 = 30;
const HEALTH_POLL_MS: u64 = 250;

pub struct PythonBackend {
    child: Mutex<Option<Child>>,
}

impl PythonBackend {
    pub const fn new() -> Self {
        Self {
            child: Mutex::new(None),
        }
    }

    pub fn spawn(&self) -> Result<(), String> {
        let workspace_root = workspace_root();
        log::info!("Spawning backend from {:?}", workspace_root);

        // If a previous app session was force-killed and its backend is
        // still holding port 8765, politely ask it to exit before we try
        // to bind. Keeps the new session from failing with "address in
        // use" errors.
        evict_stale_backend();

        let parent_pid = std::process::id();
        let mut command = Command::new("uv");
        command
            .arg("run")
            .arg("applyslave-backend")
            .arg("--port")
            .arg(BACKEND_PORT.to_string())
            .arg("--parent-pid")
            .arg(parent_pid.to_string())
            .current_dir(&workspace_root)
            // Inherit stdio so developers see backend logs while iterating.
            // In packaged builds we'll redirect these to a file.
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit());

        // Put the child in its own process group so `kill -- -pid` takes
        // down the whole tree (uv + its Python child). Without this, killing
        // uv leaves the Python process as an orphan still listening on 8765.
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            // Safety: setsid is reentrant and signal-safe; we call it in
            // the child only after fork.
            unsafe {
                command.pre_exec(|| {
                    libc_setsid();
                    Ok(())
                });
            }
        }

        let child = command.spawn().map_err(|error| {
            format!(
                "Failed to launch backend via uv. Is uv installed and the \
                 workspace synced? Run `uv sync --all-packages` in {:?}. \
                 Original error: {}",
                workspace_root, error
            )
        })?;

        let pid = child.id();
        self.child.lock().unwrap().replace(child);
        log::info!("Backend pid={}, waiting for health check", pid);

        wait_for_health()?;
        log::info!("Backend healthy on port {}", BACKEND_PORT);
        Ok(())
    }

    pub fn kill(&self) {
        let Some(mut child) = self.child.lock().unwrap().take() else {
            return;
        };
        let pid = child.id();

        // On unix: kill the whole process group so uv's Python child dies too
        #[cfg(unix)]
        {
            // Negative pid means "this process group"
            let group_pid = -(pid as i32);
            let result = unsafe { libc_kill(group_pid, 15 /* SIGTERM */) };
            if result != 0 {
                log::warn!("Failed to SIGTERM process group {}: errno", pid);
            }
            // Give it a tick to shut down gracefully, then force
            thread::sleep(Duration::from_millis(300));
            let _ = unsafe { libc_kill(group_pid, 9 /* SIGKILL */) };
        }
        #[cfg(not(unix))]
        {
            match child.kill() {
                Ok(()) => log::info!("Killed backend pid={}", pid),
                Err(error) => {
                    log::warn!("Failed to kill backend pid={}: {}", pid, error)
                }
            }
        }

        // Reap so we don't leave a zombie
        let _ = child.wait();
        log::info!("Backend pid={} reaped", pid);
    }
}

/// Find the workspace root (the repo dir) by walking up from the crate dir.
///
/// `CARGO_MANIFEST_DIR` is set by Cargo to the directory containing
/// Cargo.toml for the crate being built. We bake it in at compile time so
/// the resulting binary doesn't depend on the cwd at runtime.
fn workspace_root() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    // src-tauri -> applyslave-desktop -> apps -> repo root
    manifest_dir
        .parent()
        .and_then(|p| p.parent())
        .and_then(|p| p.parent())
        .map(PathBuf::from)
        .expect("CARGO_MANIFEST_DIR should have at least 3 parents")
}

/// Wait until the backend accepts a TCP connection on the health port.
///
/// We don't do a full HTTP GET — just prove the socket is listening. The
/// first request from the JS side will be the real functional smoke test.
fn wait_for_health() -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_secs(HEALTH_DEADLINE_SECS);
    let addr = format!("127.0.0.1:{}", BACKEND_PORT);

    while Instant::now() < deadline {
        if TcpStream::connect_timeout(
            &addr.parse().expect("hard-coded addr parses"),
            Duration::from_millis(500),
        )
        .is_ok()
        {
            // Give uvicorn a tick to finish booting after the socket opens
            thread::sleep(Duration::from_millis(200));
            return Ok(());
        }
        thread::sleep(Duration::from_millis(HEALTH_POLL_MS));
    }

    Err(format!(
        "Backend did not start within {}s on port {}",
        HEALTH_DEADLINE_SECS, BACKEND_PORT
    ))
}

/// Best-effort: if a previous session's backend is still bound to our port,
/// ask it to exit before we try to bring up a new one. We ignore errors —
/// if nothing's bound we just continue, and if something else unrelated is
/// on the port the spawn step will surface the real "address in use" error.
fn evict_stale_backend() {
    let addr = format!("127.0.0.1:{}", BACKEND_PORT);
    let Ok(socket_addr) = addr.parse() else {
        return;
    };
    let Ok(mut stream) =
        TcpStream::connect_timeout(&socket_addr, Duration::from_millis(200))
    else {
        return;
    };
    let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));

    // The backend exposes POST /api/system/shutdown for graceful exit. If
    // that route isn't there (older build), the connection will just time
    // out and we fall through.
    let request = format!(
        "POST /api/system/shutdown HTTP/1.1\r\n\
         Host: 127.0.0.1:{}\r\n\
         Connection: close\r\n\
         Content-Length: 0\r\n\r\n",
        BACKEND_PORT
    );
    let _ = stream.write_all(request.as_bytes());
    let mut buf = [0u8; 64];
    let _ = stream.read(&mut buf);

    // Give it a moment to actually release the port
    thread::sleep(Duration::from_millis(400));
    log::info!("Evicted stale backend on port {}", BACKEND_PORT);
}

// --- libc extern bindings (avoid a full libc crate dep for just 2 calls) ---

#[cfg(unix)]
extern "C" {
    fn setsid() -> i32;
    fn kill(pid: i32, sig: i32) -> i32;
}

#[cfg(unix)]
unsafe fn libc_setsid() {
    setsid();
}

#[cfg(unix)]
unsafe fn libc_kill(pid: i32, sig: i32) -> i32 {
    kill(pid, sig)
}
