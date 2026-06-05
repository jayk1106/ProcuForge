from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import APISettings, get_api_settings
from api.logging_config import configure_app_logging
from api.routers import health, products, test, vendor_threads, workflow, ws as ws_router
from api.ws import manager as ws_manager
from api.ws.context import init_ws_context

load_dotenv()
configure_app_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Capture the main event loop so sync publishers (ADK callbacks running
    # on BackgroundTasks worker threads) can bridge onto it safely.
    ws_manager.bind_loop(asyncio.get_running_loop())
    # Pre-build the WS context registry so factories can construct DTOs
    # without dragging the FastAPI dependency graph into deep call sites.
    init_ws_context()

    settings = get_api_settings()
    if settings.environment != "development":
        missing: list[str] = []
        if not settings.workflow_default_user_id:
            missing.append("WORKFLOW_DEFAULT_USER_ID")
        if not settings.workflow_default_organization_id:
            missing.append("WORKFLOW_DEFAULT_ORGANIZATION_ID")
        if missing:
            raise RuntimeError(
                "Missing required env vars for non-development environments: "
                + ", ".join(missing)
            )

    yield
    # Resource teardown goes here.


def create_app(settings: APISettings | None = None) -> FastAPI:
    """Build the FastAPI application.

    Exposed as a factory so tests and alternative entrypoints can construct
    isolated app instances with custom settings.
    """
    settings = settings or get_api_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=settings.app_description,
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(test.router, prefix=settings.api_v1_prefix)
    app.include_router(products.router, prefix=settings.api_v1_prefix)
    app.include_router(workflow.router, prefix=settings.api_v1_prefix)
    app.include_router(vendor_threads.router, prefix=settings.api_v1_prefix)
    app.include_router(ws_router.router)

    return app


app = create_app()
