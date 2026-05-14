# ApplySlave

Filling out the same form 200 times is not a job. It's a bug in the hiring process.

Local-first resume auto-apply tool: discovers jobs via public ATS APIs
(Greenhouse, Lever, Ashby, Workable), uses a local LLM to parse resumes and
fill application forms, and ships as a single `.dmg` — no Python, no terminal,
no API keys required.

## Quick start (end user)

1. Download `applyslave-desktop_0.1.0_aarch64.dmg`
2. Drag to Applications
3. First launch: macOS will say "can't verify developer" → go to **System Settings → Privacy & Security → Open Anyway**
4. App opens → upload your resume → AI extracts everything locally → start discovering jobs

No accounts needed. No data leaves your machine.

## What it does

- **Profile**: upload a PDF resume → local Qwen3-4B LLM extracts name, email, phone, experience, education, skills. Editable inline.
- **Discovery**: searches 603 verified companies across 4 ATS platforms in parallel, filters by keyword + location.
- **Apply** (WIP): Playwright-based form filler that maps your profile onto external application pages.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ ApplySlave.app (.dmg, 83MB)                         │
│                                                     │
│  applyslave-desktop (9.9MB)    Tauri 2 + React      │
│       │ spawns                                      │
│       ▼                                             │
│  applyslave-backend (80MB)     PyInstaller binary   │
│       │ contains                                    │
│       ├── FastAPI server (localhost:8765)            │
│       ├── 4 ATS clients (Greenhouse/Lever/Ashby/WK) │
│       ├── llama-cpp-python (Metal GPU)              │
│       └── Playwright (for form submission)          │
│                                                     │
│  ~/Library/Application Support/ApplySlave/          │
│       ├── models/qwen3-4b-instruct-*.gguf (2.3GB)  │
│       ├── resumes/                                  │
│       └── applyslave.db (SQLite)                    │
└─────────────────────────────────────────────────────┘
```

## Company coverage

603 companies verified via public ATS APIs (auto-maintained by `scripts/expand_companies.py`):

| ATS | Companies | Examples |
| --- | --- | --- |
| Greenhouse | 262 | Anthropic, Stripe, Databricks, Pinterest, Lyft, Airbnb, Discord, Reddit |
| Lever | 77 | Netflix, Spotify, Palantir, Kraken |
| Ashby | 209 | OpenAI, Vercel, Cursor, Linear, Ramp, Sentry, Supabase |
| Workable | 55 | Rippling, Deel, Revolut, Wise, Personio |

To refresh the list (harvests from 20 community-maintained GitHub repos + validates each slug):

```bash
.venv/bin/python scripts/expand_companies.py
```

## Repository layout

```
packages/
├── shared/          # Pydantic models + Protocol definitions
├── profile-store/   # SQLite storage + PDF resume parsing
├── job-discovery/   # ATS API clients + companies.yaml (603 slugs)
├── applicator/      # Playwright + llama-cpp-python + form filling
└── orchestrator/    # State machine + job queue + result logger

services/
└── backend/         # FastAPI HTTP/WebSocket service

apps/
└── applyslave-desktop/
    ├── src/              # React pages (Profile, Discover, Applications)
    └── src-tauri/
        ├── src/          # Rust shell (subprocess management, cleanup)
        └── binaries/     # PyInstaller backend binary (for packaging)

scripts/
├── expand_companies.py   # Harvest + verify ATS slugs
├── backend_entry.py      # PyInstaller entry point
├── debug_llm_failure.py  # Standalone LLM repro script
└── bench_llm_*.py        # LLM timing benchmarks
```

## Development

### Prerequisites

| Tool | Version | Install |
| --- | --- | --- |
| Python | 3.12+ | via `uv` |
| `uv` | 0.11+ | `brew install uv` |
| Node.js | 22.x | `brew install node@22` |
| `pnpm` | 11.x | `brew install pnpm` |
| Rust | 1.95+ | `rustup` (https://rustup.rs) |

### One-time setup

```bash
uv sync --all-packages
cd apps/applyslave-desktop && pnpm install && cd -
```

### Run in dev mode

```bash
cd apps/applyslave-desktop
pnpm tauri dev
```

Opens a native window with hot-reload. Backend starts automatically via `uv run`.
Closing the window (red ×) or Cmd+Q kills everything cleanly.

### Run tests

```bash
uv run pytest   # all packages
```

### Run backend standalone

```bash
uv run applyslave-backend --port 8765
```

## Packaging (build a .dmg)

Three steps:

```bash
# 1. Build the Python backend as a standalone binary
.venv/bin/pyinstaller applyslave-backend.spec --noconfirm

# 2. Copy to Tauri's sidecar directory
cp dist/applyslave-backend apps/applyslave-desktop/src-tauri/binaries/applyslave-backend-aarch64-apple-darwin

# 3. Build the Tauri app bundle
cd apps/applyslave-desktop
pnpm tauri build
```

Output: `apps/applyslave-desktop/src-tauri/target/release/bundle/dmg/applyslave-desktop_0.1.0_aarch64.dmg` (~83MB)

### What's in the .dmg

- `applyslave-desktop` (Tauri shell, 9.9MB) — manages window + spawns backend
- `applyslave-backend` (PyInstaller binary, 80MB) — Python + FastAPI + all deps bundled

### No code signing (current state)

The `.dmg` is not signed or notarized. Users need to:
1. Open the app
2. Get the "can't verify developer" dialog
3. Go to System Settings → Privacy & Security → Open Anyway

To sign for public distribution: requires Apple Developer ID ($99/year) + `codesign` + `notarytool`.

### Process lifecycle

| Event | What happens |
| --- | --- |
| App opens | Tauri spawns `applyslave-backend` as a child process |
| Red × / Cmd+Q / Dock Quit | Tauri sends SIGTERM to backend process group → backend dies |
| App force-quit (Activity Monitor) | Backend's parent-pid watchdog detects Tauri is gone → self-exits within 3s |
| Stale port on next launch | Tauri POSTs `/api/system/shutdown` to evict the old process before spawning new |

## LLM model

The app uses **Qwen3-4B-Instruct** (Q4_K_M quantization, ~2.3GB) for resume parsing.
Runs locally on Apple Metal GPU. First inference ~30s (shader compilation), subsequent ~5-10s.

Model location: `~/Library/Application Support/ApplySlave/models/`

Download: triggered automatically on first resume upload, or manually via `POST /api/model/download`.

## What's next

- **Auto-apply pipeline**: wire the Playwright form-filler to actually submit applications
- **More ATS adapters**: Microsoft/Amazon/Meta careers pages (custom, not public ATS)
- **Cloud job search API** (optional): JSearch/Adzuna for broader coverage beyond the 603 known companies
- **Windows/Linux builds**: same architecture, just need PyInstaller cross-compile + different Tauri target triples
