"""FastAPI application assembly."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_audit, routes_filings, routes_research
from app.config import get_settings
from app.db.database import init_db
from app.logging_config import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db()
    logger.info(
        "Application started",
        extra={"extra_fields": {"llm_provider": settings.llm_provider}},
    )
    yield


app = FastAPI(
    title="Investment Research Evidence Agent",
    description=(
        "AI-assisted research on public SEC filings with evidence verification, "
        "human review, and a full audit trail. For research and education only — "
        "this tool does not provide investment advice."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_filings.router)
app.include_router(routes_research.router)
app.include_router(routes_audit.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "llm_provider": get_settings().llm_provider}
