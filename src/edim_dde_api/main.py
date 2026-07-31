"""FastAPI application entrypoint."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from edim_dde_ai import set_llm_provider
from edim_dde_ai.errors import ChainInvokerError
from edim_dde_domain import (
    FoundryLLMNotConfiguredError,
    bootstrap_agents,
)
from edim_dde_domain.llm import get_foundry_llm_provider
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from edim_dde_api import __version__
from edim_dde_api.middleware import DatabricksUserTokenMiddleware
from edim_dde_api.routes import router


def _cors_origins() -> list[str]:
    """Explicit browser origins from ``EDIM_CORS_ORIGINS`` (comma-separated).

    Empty (default) disables cross-origin browser access. Never combine
    ``allow_origins=["*"]`` with credentials — Starlette would reflect any
    request Origin.
    """
    raw = os.environ.get("EDIM_CORS_ORIGINS", "").strip()
    if not raw:
        return []
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    bootstrap_agents()

    class _LazyFoundry:
        """Resolve Foundry on first invoke so /health works before LLM env is set."""

        def invoke(
            self,
            messages: list[tuple[str, str]],
            *,
            config: dict | None = None,
        ) -> str:
            return get_foundry_llm_provider().invoke(messages, config=config)

    set_llm_provider(_LazyFoundry())
    yield


app = FastAPI(
    title="EDIM DDE API",
    description=(
        "Thin FastAPI over edim-dde-domain YAML agents "
        "(Spark RCA + cluster tuning)."
    ),
    version=__version__,
    lifespan=lifespan,
)

_origins = _cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=bool(_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(DatabricksUserTokenMiddleware)
app.include_router(router)


@app.exception_handler(FoundryLLMNotConfiguredError)
async def foundry_not_configured_handler(
    _request: Request, exc: FoundryLLMNotConfiguredError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc), "error_code": "FOUNDRY_LLM_NOT_CONFIGURED"},
    )


@app.exception_handler(ChainInvokerError)
async def chain_invoker_handler(
    _request: Request, exc: ChainInvokerError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc), "error_code": "LLM_CHAIN_ERROR"},
    )


def main() -> None:
    import uvicorn

    uvicorn.run("edim_dde_api.main:app", host="0.0.0.0", port=8080, reload=True)


if __name__ == "__main__":
    main()
