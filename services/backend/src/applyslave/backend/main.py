"""FastAPI entry point for the ApplySlave backend service."""

from __future__ import annotations

import argparse

from fastapi import FastAPI

app = FastAPI(title="ApplySlave Backend", version="0.1.0")


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Health check used by the Tauri shell to know when the backend is ready."""
    return {"status": "ok", "version": "0.1.0"}


def run() -> None:
    """CLI entry point: `applyslave-backend --port 8765`."""
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    run()
