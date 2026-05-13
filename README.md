# ApplySlave

Filling out the same form 200 times is not a job. It's a bug in the hiring process.

Local-first resume auto-apply tool: discovers jobs via public ATS APIs
(Greenhouse, Lever, Ashby, Workable), uses a local LLM to fill external
application forms, and ships as a cross-platform desktop app
(macOS / Windows / Linux).

## Status — v2 active

Working monorepo with green tests end-to-end. v1 `src/` is kept for reference
only.

| Layer                    | Tests passing                                      |
| ------------------------ | -------------------------------------------------- |
| shared (models, protocols) | 7/7                                              |
| profile-store (SQLite, PDF parse) | 6/6                                       |
| job-discovery (4 ATS clients + aggregator) | 14/14                            |
| applicator (Playwright + form-filler + LLM glue) | 11/11                      |
| orchestrator (state machine, retry, logger) | 9/9                             |
| services/backend (FastAPI) | 8/8                                              |
| **Total**                | **55/55**                                          |

Design docs for the current direction live in [`docs-v2/`](./docs-v2).

## Repository Layout

```
packages/
├── shared/          # Pydantic models + Protocol definitions
├── profile-store/   # SQLite storage + PDF resume parsing
├── job-discovery/   # Greenhouse / Lever / Ashby / Workable API clients
├── applicator/      # Playwright browser + llama-cpp-python + form filling
└── orchestrator/    # State machine + job queue + result logger

services/
└── backend/         # FastAPI HTTP/WebSocket service (localhost:8765)

apps/
└── applyslave-desktop/   # Tauri 2 + React + TypeScript + TanStack Query
    ├── src/               # React pages + API client
    └── src-tauri/         # Rust shell (manages Python subprocess)

docs-v2/             # Architecture, API contract, packaging, plan
src/                 # v1 Python code (legacy, not on the active path)
```

## Toolchain

| Tool        | Version tested | Install                         |
| ----------- | -------------- | ------------------------------- |
| Python      | 3.12+          | via `uv`                        |
| `uv`        | 0.11+          | `brew install uv`               |
| Node.js     | 22.x           | `brew install node@22`          |
| `pnpm`      | 11.x           | `brew install pnpm`             |
| Rust        | 1.95+          | `rustup` (<https://rustup.rs>)  |

## Development

### One-time setup

```bash
# Python workspace + deps
uv sync --all-packages

# Playwright browsers
uv run playwright install chromium

# Frontend deps
cd apps/applyslave-desktop
pnpm install
cd -
```

### Run tests

```bash
uv run pytest                    # all 55 tests
uv run pytest packages/shared   # one package
```

### Run the app (one command)

```bash
cd apps/applyslave-desktop
pnpm tauri dev
```

This spawns a native macOS window, starts Vite for hot-reload, and launches
the Python backend as a child process of the Tauri shell. On Ctrl-C (or
closing the window) the whole tree — Tauri, Vite, uv, Python — shuts down
cleanly.

### Run pieces separately (for faster iteration)

```bash
# Terminal 1 – Python backend
uv run applyslave-backend --port 8765

# Terminal 2 – Frontend only (browser, no Tauri shell)
cd apps/applyslave-desktop
pnpm exec vite
# open http://localhost:1420
```

### Build a production app

```bash
cd apps/applyslave-desktop
pnpm tauri build
```

Produces `src-tauri/target/release/bundle/dmg/ApplySlave_*.dmg` (once
code-signing is set up). Note: the current build invokes `uv run ...` at
runtime, so the shipped `.dmg` still expects a Python workspace at the
build-time path. Fully standalone packaging is in
[`docs-v2/packaging-strategy.md`](./docs-v2/packaging-strategy.md).

### Smoke-test the real ATS integration

```bash
uv run python scripts/smoke_greenhouse.py
# → "Fetched N engineering jobs from Figma" (hits the real Greenhouse API)
```

## What works today

- **Profile management**: save / load structured user profile in SQLite,
  upload PDF resume, auto-parse common fields (name, email, phone, links).
- **Job discovery**: fan out across Greenhouse + Lever + Ashby + Workable
  public APIs (30+ seed companies in `companies.yaml`), filter + dedupe.
- **Backend API**: FastAPI service with endpoints for profile, discovery,
  applications, model lifecycle, plus a WebSocket hub for progress events.
- **Browser automation**: persistent-context Chromium with stealth scripts,
  DOM extractor with label resolution, mechanical action executor.
- **Form-filler**: rule-based deterministic mapping (covers common fields
  without LLM) + LLM fallback wired through a `LLMClient` protocol.
- **Orchestrator**: batched apply with per-job status persistence,
  exponential-backoff retry, event callbacks.
- **Frontend**: three pages (Profile, Discover, Applications) wired with
  TanStack Query + Tailwind + React Router.

## What's scaffolded but needs the model

- **LLM inference**: code paths exist but require downloading
  Qwen2.5-7B-Instruct (~4GB). Call `POST /api/model/download` or let the
  UI drive the first-run flow.
- **ApplicatorEngine end-to-end**: works against the fixture test form;
  will work against real external apply pages once the LLM fallback is
  exercised in real traffic.

## Next steps

Continue with `docs-v2/implementation-plan.md`:

- Hook `ApplicatorEngine` into the backend so `/api/applications` actually
  fires the pipeline instead of just queueing records.
- Wire Tauri's Rust shell to spawn the backend subprocess on app start
  (see `docs-v2/packaging-strategy.md`).
- Build the `.dmg` / `.exe` / `.AppImage` packaging pipeline.
