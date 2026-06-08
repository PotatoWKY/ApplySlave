# Hamster

Filling out the same form 200 times is not a job. It's a bug in the hiring process.

Local-first resume auto-apply tool: discovers jobs via public ATS APIs
(Greenhouse, Lever, Ashby, Workable), uses a local LLM to parse resumes and
fill application forms, and ships as a single `.dmg` — no Python, no terminal,
no API keys required.

## Quick start (end user)

1. Download `hamster-desktop_0.1.0_aarch64.dmg`
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
│ Hamster.app (.dmg, 83MB)                         │
│                                                     │
│  hamster-desktop (9.9MB)    Tauri 2 + React      │
│       │ spawns                                      │
│       ▼                                             │
│  hamster-backend (80MB)     PyInstaller binary   │
│       │ contains                                    │
│       ├── FastAPI server (localhost:8765)            │
│       ├── 4 ATS clients (Greenhouse/Lever/Ashby/WK) │
│       ├── llama-cpp-python (Metal GPU)              │
│       └── Playwright (for form submission)          │
│                                                     │
│  ~/Library/Application Support/Hamster/          │
│       ├── models/qwen3-4b-instruct-*.gguf (2.3GB)  │
│       ├── resumes/                                  │
│       └── hamster.db (SQLite)                    │
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
└── hamster-desktop/
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
cd apps/hamster-desktop && pnpm install && cd -
```

### Run in dev mode

```bash
cd apps/hamster-desktop
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
uv run hamster-backend --port 8765
```

## Packaging (build a .dmg)

Three steps:

```bash
# 1. Build the Python backend as a standalone binary
.venv/bin/pyinstaller hamster-backend.spec --noconfirm

# 2. Copy to Tauri's sidecar directory
cp dist/hamster-backend apps/hamster-desktop/src-tauri/binaries/hamster-backend-aarch64-apple-darwin

# 3. Build the Tauri app bundle
cd apps/hamster-desktop
pnpm tauri build
```

Output: `apps/hamster-desktop/src-tauri/target/release/bundle/dmg/hamster-desktop_0.1.0_aarch64.dmg` (~83MB)

### What's in the .dmg

- `hamster-desktop` (Tauri shell, 9.9MB) — manages window + spawns backend
- `hamster-backend` (PyInstaller binary, 80MB) — Python + FastAPI + all deps bundled

### No code signing (current state)

The `.dmg` is not signed or notarized. Users need to:
1. Open the app
2. Get the "can't verify developer" dialog
3. Go to System Settings → Privacy & Security → Open Anyway

To sign for public distribution: requires Apple Developer ID ($99/year) + `codesign` + `notarytool`.

### Process lifecycle

| Event | What happens |
| --- | --- |
| App opens | Tauri spawns `hamster-backend` as a child process |
| Red × / Cmd+Q / Dock Quit | Tauri sends SIGTERM to backend process group → backend dies |
| App force-quit (Activity Monitor) | Backend's parent-pid watchdog detects Tauri is gone → self-exits within 3s |
| Stale port on next launch | Tauri POSTs `/api/system/shutdown` to evict the old process before spawning new |

## LLM model

The app uses **Qwen3-4B-Instruct** (Q4_K_M quantization, ~2.3GB) for resume parsing.
Runs locally on Apple Metal GPU. First inference ~30s (shader compilation), subsequent ~5-10s.

Model location: `~/Library/Application Support/Hamster/models/`

Download: triggered automatically on first resume upload, or manually via `POST /api/model/download`.

## What's next

- **Live submission**: the apply pipeline is wired end-to-end (queue → worker → Playwright form-fill → screenshot) but stops at a dry-run gate; flipping it to actually click submit still needs pre-submit confirmation-page verification and per-application approval
- **More ATS adapters**: Microsoft/Amazon/Meta careers pages (custom, not public ATS)
- **Windows/Linux builds**: same architecture, just need PyInstaller cross-compile + different Tauri target triples

## JSearch API setup (for non-tech jobs / broader coverage)

The 603 companies in our local list are mostly tech companies (sourced from SWE job repos). For non-tech roles (financial analyst, marketing, operations) or companies that use Workday/iCIMS/Taleo (banks, Fortune 500, retail), you need JSearch — a wrapper around Google Jobs that covers all job boards and ATS platforms.

**Free tier**: 200 searches/month (plenty for personal use)

### Setup steps

1. Go to: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
2. Sign up for a RapidAPI account (Google/GitHub login works)
3. Subscribe to the "Basic" plan (free, 200 requests/month)
4. Copy your API key from the page (`X-RapidAPI-Key: xxxxxxxx`)
5. Paste it into the app's Settings page → JSearch section (stored locally in `settings.json`)

### What it covers that our local list doesn't

| Our local ATS list (603 companies) | JSearch (Google Jobs aggregation) |
| --- | --- |
| Greenhouse, Lever, Ashby, Workable only | All ATS platforms including Workday, iCIMS, Taleo, SuccessFactors |
| Mostly tech/startup companies | All industries (finance, healthcare, retail, consulting) |
| Free, unlimited, no API key | Free tier 200/month, needs key |
| Real-time per-company fetch | Google's crawl (slight delay) |

### Privacy

Only the search query ("financial analyst Seattle") is sent to RapidAPI. Your resume, profile, and application history stay 100% local.
