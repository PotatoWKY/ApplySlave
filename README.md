# ApplySlave

Filling out the same form 200 times is not a job. It's a bug in the hiring process.

Local-first resume auto-apply tool: talks to public ATS APIs (Greenhouse, Lever,
Ashby, Workable), uses a local LLM to fill external application forms, and ships
as a cross-platform desktop app (macOS / Windows / Linux).

## Status

Architecture in transition. Two worlds live side by side:

- `src/` — v1 Python CLI with LinkedIn hardcoded entry (kept for reference)
- `packages/`, `services/`, `apps/` — v2 monorepo (active)

Design docs for the current direction are in [`docs-v2/`](./docs-v2).

## Repository Layout (v2)

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
└── applyslave-desktop/   # Tauri 2 + React + TypeScript desktop app
    ├── src/               # React + TanStack Query + Tailwind CSS
    └── src-tauri/         # Rust shell: manages Python subprocess

docs-v2/             # Architecture, API contract, packaging, plan
src/                 # v1 Python code (legacy reference)
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

### Python backend

```bash
# Sync all workspace packages in editable mode
uv sync --all-packages

# Run backend HTTP server
uv run applyslave-backend --port 8765

# Health check
curl http://localhost:8765/api/health
# → {"status":"ok","version":"0.1.0"}
```

### Desktop app

```bash
cd apps/applyslave-desktop

# Install frontend deps (first time)
pnpm install

# Dev mode: starts Vite HMR + Tauri shell; hot-reload on save
pnpm tauri dev

# Production build (creates .dmg / .exe / .AppImage)
pnpm tauri build
```

The Tauri shell expects the Python backend running on `localhost:8765`. In
development, start the backend in a separate terminal with `uv run
applyslave-backend`. Later, Tauri will spawn it as a managed subprocess
automatically (see [docs-v2/packaging-strategy.md](./docs-v2/packaging-strategy.md)).

## Next steps

See [`docs-v2/implementation-plan.md`](./docs-v2/implementation-plan.md) for the
phased roadmap. Currently at **Phase 1.0 (scaffolding) complete** — ready to
start implementing packages.
