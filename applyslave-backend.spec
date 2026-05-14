# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the ApplySlave backend binary.

Produces a single-file executable at dist/applyslave-backend that bundles:
- Python interpreter
- All applyslave.* packages (shared, profile_store, job_discovery, applicator, orchestrator, backend)
- FastAPI + uvicorn + httpx + pydantic + pyyaml + llama-cpp-python
- companies.yaml data file

Does NOT bundle:
- The LLM model file (2.3GB, downloaded at first run)
- Playwright browsers (not needed for discovery; will be handled separately for applicator)

Run: .venv/bin/pyinstaller applyslave-backend.spec
"""

import os
from pathlib import Path

block_cipher = None

ROOT = Path(os.getcwd())

# Data files that need to be bundled (importlib.resources reads them at runtime)
datas = [
    (
        str(ROOT / "packages" / "job-discovery" / "src" / "applyslave" / "job_discovery" / "companies.yaml"),
        "applyslave/job_discovery",
    ),
]

# Hidden imports that PyInstaller's analysis misses (dynamic imports, plugins)
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "applyslave.shared",
    "applyslave.profile_store",
    "applyslave.job_discovery",
    "applyslave.applicator",
    "applyslave.orchestrator",
    "applyslave.backend",
    "applyslave.backend.routers",
    "applyslave.backend.routers.profile",
    "applyslave.backend.routers.discovery",
    "applyslave.backend.routers.applications",
    "applyslave.backend.routers.system",
    "applyslave.backend.dependencies",
    "applyslave.backend.websocket_hub",
    "applyslave.applicator.llm",
    "applyslave.applicator.llm.client",
    "applyslave.applicator.llm.model_manager",
    "applyslave.applicator.llm.resume_extractor",
    "applyslave.applicator.llm.prompt_builder",
    "applyslave.job_discovery.factory",
    "applyslave.job_discovery.aggregator",
    "applyslave.job_discovery.sources.greenhouse",
    "applyslave.job_discovery.sources.lever",
    "applyslave.job_discovery.sources.ashby",
    "applyslave.job_discovery.sources.workable",
    # pydantic internals
    "pydantic",
    "pydantic.deprecated",
    "pydantic.deprecated.decorator",
    "email_validator",
    # httpx / httpcore
    "httpx",
    "httpcore",
    "httpcore._async",
    "httpcore._sync",
    "h11",
    "anyio",
    "anyio._backends",
    "anyio._backends._asyncio",
    "sniffio",
    # starlette / fastapi internals
    "starlette.responses",
    "starlette.routing",
    "starlette.middleware",
    "starlette.middleware.cors",
    "multipart",
    "multipart.multipart",
    # yaml
    "yaml",
]

a = Analysis(
    ["scripts/backend_entry.py"],
    pathex=[
        str(ROOT / "packages" / "shared" / "src"),
        str(ROOT / "packages" / "profile-store" / "src"),
        str(ROOT / "packages" / "job-discovery" / "src"),
        str(ROOT / "packages" / "applicator" / "src"),
        str(ROOT / "packages" / "orchestrator" / "src"),
        str(ROOT / "services" / "backend" / "src"),
    ],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy stuff we don't need in the binary
        "tkinter",
        "matplotlib",
        "numpy.testing",
        "scipy",
        "pandas",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="applyslave-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    target_arch="arm64",
)
