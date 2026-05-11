from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import APISettings, get_api_settings
from api.logging_config import configure_app_logging
from api.routers import health, test, workflow

load_dotenv()
configure_app_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Resource setup (e.g. Firestore client, HTTP clients) goes here.
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
    app.include_router(workflow.router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
