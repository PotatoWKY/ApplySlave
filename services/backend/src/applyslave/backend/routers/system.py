"""System-level endpoints: health, model status, model download."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import uuid

from fastapi import APIRouter, BackgroundTasks, Request, status
from pydantic import BaseModel

from applyslave.applicator.llm import ModelManager
from applyslave.backend.dependencies import get_data_dir

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["system"])


def _model_manager() -> ModelManager:
    return ModelManager(data_dir=get_data_dir())


class HealthResponse(BaseModel):
    status: str
    version: str
    model_installed: bool
    model_name: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    manager = _model_manager()
    return HealthResponse(
        status="ok",
        version="0.1.0",
        model_installed=manager.is_installed(),
        model_name=manager.model_name,
    )


class ModelDownloadResponse(BaseModel):
    task_id: str


class ModelStatusResponse(BaseModel):
    installed: bool
    downloading: bool
    model_name: str


@router.post(
    "/model/download",
    response_model=ModelDownloadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_model_download(
    request: Request,
    background_tasks: BackgroundTasks,
) -> ModelDownloadResponse:
    manager = _model_manager()
    ws_hub = request.app.state.ws_hub
    state = request.app.state.model_download_state
    if state.get("in_progress"):
        return ModelDownloadResponse(task_id=state["task_id"])
    task_id = f"model-dl-{uuid.uuid4().hex[:8]}"
    state["in_progress"] = True
    state["task_id"] = task_id
    background_tasks.add_task(_run_download, task_id, manager, ws_hub, state)
    return ModelDownloadResponse(task_id=task_id)


@router.get("/model/status", response_model=ModelStatusResponse)
async def model_status(request: Request) -> ModelStatusResponse:
    manager = _model_manager()
    state = request.app.state.model_download_state
    return ModelStatusResponse(
        installed=manager.is_installed(),
        downloading=bool(state.get("in_progress")),
        model_name=manager.model_name,
    )


@router.delete("/model", status_code=status.HTTP_200_OK)
async def delete_model(request: Request) -> dict:
    """Delete the downloaded model file to free disk space (~2.3GB).

    Also invalidates the cached LLM client in the profile router so the
    next resume upload will see the model as missing instead of trying
    to use a now-dangling mmap.
    """
    manager = _model_manager()
    state = request.app.state.model_download_state
    if state.get("in_progress"):
        return {
            "deleted": False,
            "reason": "model is currently downloading; wait for it to finish "
            "or restart the app",
        }
    if not manager.is_installed():
        # Still clean up any leftover .part file from an aborted download.
        partial = manager.model_path.with_suffix(".gguf.part")
        if partial.exists():
            partial.unlink()
            return {"deleted": True, "removed_partial": True}
        return {"deleted": False, "reason": "model not installed"}

    # Drop the cached client first so any in-flight references release
    # their mmap before we unlink the file. Done by reaching into the
    # profile router's module global — keeps the wiring obvious.
    from applyslave.backend.routers import profile as profile_router

    old_client = profile_router._CACHED_LLM_CLIENT
    profile_router._CACHED_LLM_CLIENT = None

    # Explicitly close the Llama instance to release the mmap'd memory
    # (~2.3GB) immediately rather than waiting for GC. llama-cpp-python's
    # Llama object holds a ctypes pointer to the C++ model; setting
    # _llama to None drops the only reference and triggers __del__ which
    # calls llama_free. We also del the client to break any ref cycles.
    if old_client is not None:
        if hasattr(old_client, "close"):
            old_client.close()
        del old_client

    manager.model_path.unlink()
    # Also clean up any partial download artifacts
    partial = manager.model_path.with_suffix(".gguf.part")
    if partial.exists():
        partial.unlink()
    logger.info("Deleted model at %s", manager.model_path)
    return {"deleted": True, "path": str(manager.model_path)}


@router.post(
    "/system/shutdown",
    status_code=status.HTTP_202_ACCEPTED,
)
async def shutdown() -> dict:
    """Exit this backend process cleanly.

    The Tauri shell calls this before spawning a new backend so any
    leftover process from a previous (possibly force-killed) session
    releases port 8765 before we try to bind.
    """

    async def _self_kill() -> None:
        # Small delay so the HTTP response flushes before we die.
        await asyncio.sleep(0.2)
        os.kill(os.getpid(), signal.SIGTERM)

    asyncio.create_task(_self_kill())
    return {"status": "shutting_down"}


async def _run_download(
    task_id: str,
    manager: ModelManager,
    ws_hub,
    state: dict,
) -> None:
    loop = asyncio.get_event_loop()
    last_emit_time = [loop.time()]

    def progress(downloaded: int, total: int | None) -> None:
        now = loop.time()
        if now - last_emit_time[0] < 1:
            return
        last_emit_time[0] = now
        asyncio.run_coroutine_threadsafe(
            ws_hub.broadcast(
                {
                    "type": "model_download_progress",
                    "task_id": task_id,
                    "downloaded_bytes": downloaded,
                    "total_bytes": total,
                }
            ),
            loop,
        )

    try:
        await manager.download(progress=progress)
        await ws_hub.broadcast(
            {"type": "model_download_completed", "task_id": task_id}
        )
    except Exception as error:  # noqa: BLE001
        logger.exception("Model download failed")
        await ws_hub.broadcast(
            {
                "type": "model_download_failed",
                "task_id": task_id,
                "error": str(error),
            }
        )
    finally:
        state["in_progress"] = False
        state["task_id"] = None
