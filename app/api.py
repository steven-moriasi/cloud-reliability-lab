from dataclasses import asdict
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.domain.errors import DatabaseUnavailableError
from app.domain.models import DataSource, DependencyState
from app.resilience import ResilientOrderService

router = APIRouter()


class SummaryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: int
    order_count: int
    total_cents: int
    source: DataSource


class DependencyResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    database: DependencyState
    cache: DependencyState


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    dependencies: DependencyResponse


def get_order_service(request: Request) -> ResilientOrderService:
    return cast(ResilientOrderService, request.app.state.order_service)


OrderService = Annotated[ResilientOrderService, Depends(get_order_service)]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
def ready(service: OrderService, response: Response) -> ReadinessResponse:
    database_available, cache_available = service.dependency_status()
    dependencies = DependencyResponse(
        database=(
            DependencyState.HEALTHY
            if database_available
            else DependencyState.UNAVAILABLE
        ),
        cache=(
            DependencyState.HEALTHY
            if cache_available
            else DependencyState.DEGRADED
        ),
    )
    if not database_available:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="unavailable", dependencies=dependencies)
    readiness = "ready" if cache_available else "degraded"
    return ReadinessResponse(status=readiness, dependencies=dependencies)


@router.get("/api/tenants/{tenant_id}/orders/summary", response_model=SummaryResponse)
def order_summary(
    tenant_id: Annotated[int, Field(ge=1)],
    service: OrderService,
    response: Response,
) -> SummaryResponse:
    try:
        result = service.get_summary(tenant_id)
    except DatabaseUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Order summary is temporarily unavailable",
        ) from error
    if result.source is DataSource.STALE:
        response.headers["Warning"] = '110 reliability-lab "Response is stale"'
    return SummaryResponse(**asdict(result.summary), source=result.source)
