"""FastAPI entry point wiring all routers together."""

from __future__ import annotations

import argparse
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from applyslave.backend.routers import applications, discovery, profile, system
from applyslave.backend.websocket_hub import WebSocketHub

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ws_hub = WebSocketHub()
        app.state.model_download_state = {"in_progress": False, "task_id": None}
        logger.info("Backend started")
        yield
        logger.info("Backend stopping")

    app = FastAPI(
        title="ApplySlave Backend",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Tauri app loads from tauri://localhost (or similar); allow anything in
    # development. In production the backend is only reachable on loopback.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(profile.router)
    app.include_router(discovery.router)
    app.include_router(applications.router)
    app.include_router(system.router)

    @app.websocket("/api/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        hub: WebSocketHub = websocket.app.state.ws_hub
        await hub.connect(websocket)
        try:
            while True:
                # We don't process inbound messages today; just keep the
                # connection open. FastAPI needs us to read to detect
                # disconnects.
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            await hub.disconnect(websocket)

    return app


app = create_app()


def run() -> None:
    """CLI entry: ``applyslave-backend --port 8765``."""
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    uvicorn.run(
        "applyslave.backend.main:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    run()
