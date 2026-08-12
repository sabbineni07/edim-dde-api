"""FastAPI application entrypoint."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from edim_dde_ai import (
    configure_observability_from_env,
    configure_retrieval_from_env,
    configure_state_store_from_env,
    set_llm_provider,
    sync_registered_agents_to_store,
)
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
from edim_dde_api.guide import mount_guide
from edim_dde_api.middleware import DatabricksUserTokenMiddleware, RequestIdMiddleware
from edim_dde_api.request_context import configure_request_id_logging
from edim_dde_api.routes import api_v1, router
from edim_dde_api.safe_logging import log_exception_once, safe_exc_message


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
    import logging

    log = logging.getLogger(__name__)
    configure_request_id_logging()
    # BL-013: load Key Vault secrets into env (no overwrite of existing values).
    try:
        from edim_dde_domain.security import load_key_vault_secrets

        load_key_vault_secrets()
        # Re-read env after vault inject (Foundry SP → EDIM_FOUNDRY_*).
        from edim_dde_domain.config import clear_settings_cache
        from edim_dde_domain.llm.foundry import clear_foundry_llm_provider_cache

        clear_settings_cache()
        clear_foundry_llm_provider_cache()
    except Exception as exc:  # noqa: BLE001 — startup should still allow /health
        log_exception_once(
            log,
            "Key Vault bootstrap skipped/failed",
            exc,
            level=logging.WARNING,
        )

    # Pluggable observability: EDIM_OBSERVABILITY=none|langsmith|mlflow|auto
    try:
        configure_observability_from_env()
    except Exception as exc:  # noqa: BLE001
        log_exception_once(
            log,
            "Observability configure failed; continuing with no-op",
            exc,
            level=logging.WARNING,
        )

    # Control-plane store: EDIM_STATE_STORE=memory|postgres|cosmos|redis
    try:
        configure_state_store_from_env()
    except Exception as exc:  # noqa: BLE001
        log_exception_once(
            log,
            "State store configure failed; continuing with memory",
            exc,
            level=logging.WARNING,
        )

    # Retrieval plane: EDIM_RETRIEVAL=none|memory|faiss|azure_ai_search|databricks_vector
    try:
        configure_retrieval_from_env()
    except Exception as exc:  # noqa: BLE001
        log_exception_once(
            log,
            "Retrieval configure failed; continuing with none",
            exc,
            level=logging.WARNING,
        )

    # Product P1: warn (default) or fail fast (EDIM_STRICT_STARTUP=1) on env gaps.
    try:
        from edim_dde_domain.startup import validate_runtime_env

        validate_runtime_env()
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001
        log_exception_once(
            log,
            "Startup env validation failed unexpectedly",
            exc,
            level=logging.WARNING,
        )

    bootstrap_agents()

    # Mirror Git-loaded agent YAML metadata into the durable catalog (if any).
    try:
        sync_registered_agents_to_store(actor="api-lifespan")
    except Exception as exc:  # noqa: BLE001
        log_exception_once(
            log,
            "Agent catalog sync failed",
            exc,
            level=logging.WARNING,
        )

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
app.add_middleware(RequestIdMiddleware)
app.include_router(router)
app.include_router(api_v1)
mount_guide(app)


@app.exception_handler(FoundryLLMNotConfiguredError)
async def foundry_not_configured_handler(
    _request: Request, exc: FoundryLLMNotConfiguredError
) -> JSONResponse:
    # Logged once here (not also in routes) — bubbles from Foundry provider.
    import logging

    log_exception_once(
        logging.getLogger(__name__),
        "Foundry LLM not configured",
        exc,
        level=logging.WARNING,
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": safe_exc_message(exc),
            "error_code": "FOUNDRY_LLM_NOT_CONFIGURED",
        },
    )


@app.exception_handler(ChainInvokerError)
async def chain_invoker_handler(
    _request: Request, exc: ChainInvokerError
) -> JSONResponse:
    import logging

    log_exception_once(
        logging.getLogger(__name__),
        "LLM chain invoke failed",
        exc,
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "LLM chain failed; see server logs for details",
            "error_code": "LLM_CHAIN_ERROR",
        },
    )


def main() -> None:
    import uvicorn

    uvicorn.run("edim_dde_api.main:app", host="0.0.0.0", port=8080, reload=True)


if __name__ == "__main__":
    main()
