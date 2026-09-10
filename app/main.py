from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api import router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.infrastructure.cache import CircuitBreaker, ExternalCache, MemoryStaleCache
from app.infrastructure.database import Database
from app.resilience import ResilientOrderService


def build_order_service(settings: Settings) -> tuple[Database, ResilientOrderService]:
    database = Database(
        settings.database_url,
        min_size=settings.pool_min_size,
        max_size=settings.pool_max_size,
        pool_timeout_seconds=settings.pool_timeout_seconds,
        query_timeout_ms=settings.query_timeout_ms,
    )
    cache = ExternalCache(
        settings.cache_url,
        ttl_seconds=settings.cache_ttl_seconds,
        breaker=CircuitBreaker(
            failure_threshold=settings.cache_failure_threshold,
            recovery_seconds=settings.cache_recovery_seconds,
        ),
    )
    stale_cache = MemoryStaleCache(stale_seconds=settings.stale_if_error_seconds)
    return database, ResilientOrderService(database, cache, stale_cache)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    database, service = build_order_service(settings)
    database.open()
    app.state.order_service = service
    try:
        yield
    finally:
        database.close()


configure_logging()
app = FastAPI(
    title="Cloud Reliability Lab",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
