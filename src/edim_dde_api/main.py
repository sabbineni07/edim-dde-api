"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from edim_dde_api import __version__
from edim_dde_api.routes import router
from edim_dde_domain import bootstrap_agents


@asynccontextmanager
async def lifespan(_app: FastAPI):
    bootstrap_agents()
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
app.include_router(router)


def main() -> None:
    import uvicorn

    uvicorn.run("edim_dde_api.main:app", host="0.0.0.0", port=8080, reload=True)


if __name__ == "__main__":
    main()
