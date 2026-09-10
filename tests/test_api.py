from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from app.api import get_order_service
from app.domain.errors import DatabaseUnavailableError
from app.domain.models import DataSource, OrderSummary
from app.main import app
from app.resilience import SummaryResult


@dataclass
class FakeService:
    source: DataSource = DataSource.DATABASE
    database_available: bool = True
    cache_available: bool = True
    unavailable_tenants: set[int] = field(default_factory=set)

    def get_summary(self, tenant_id: int) -> SummaryResult:
        if tenant_id in self.unavailable_tenants:
            raise DatabaseUnavailableError("unavailable")
        return SummaryResult(
            summary=OrderSummary(
                tenant_id=tenant_id,
                order_count=12,
                total_cents=34500,
            ),
            source=self.source,
        )

    def dependency_status(self) -> tuple[bool, bool]:
        return self.database_available, self.cache_available


def client_for(service: FakeService) -> TestClient:
    app.dependency_overrides[get_order_service] = lambda: service
    return TestClient(app)


def test_health_is_independent_of_dependencies() -> None:
    response = client_for(FakeService(database_available=False)).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_readiness_allows_cache_degradation() -> None:
    response = client_for(FakeService(cache_available=False)).get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "dependencies": {"database": "healthy", "cache": "degraded"},
    }


def test_readiness_fails_when_database_is_unavailable() -> None:
    response = client_for(FakeService(database_available=False)).get("/ready")

    assert response.status_code == 503
    assert response.json()["dependencies"]["database"] == "unavailable"


def test_order_summary_reports_database_source() -> None:
    response = client_for(FakeService()).get("/api/tenants/7/orders/summary")

    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": 7,
        "order_count": 12,
        "total_cents": 34500,
        "source": "database",
    }


def test_stale_summary_is_explicitly_marked() -> None:
    response = client_for(FakeService(source=DataSource.STALE)).get(
        "/api/tenants/7/orders/summary"
    )

    assert response.status_code == 200
    assert response.headers["warning"] == '110 reliability-lab "Response is stale"'
    assert response.json()["source"] == "stale"


def test_summary_returns_generic_unavailability() -> None:
    response = client_for(FakeService(unavailable_tenants={7})).get(
        "/api/tenants/7/orders/summary"
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Order summary is temporarily unavailable"}


def test_tenant_identifier_is_validated() -> None:
    response = client_for(FakeService()).get("/api/tenants/0/orders/summary")

    assert response.status_code == 422
