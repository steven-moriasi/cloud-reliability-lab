import httpx
import pytest

from app.infrastructure.toxiproxy import PROXIES, ToxiproxyClient


def test_proxy_outage_request_is_scoped() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    client = ToxiproxyClient(
        "http://toxiproxy",
        client=httpx.Client(
            base_url="http://toxiproxy",
            transport=httpx.MockTransport(handler),
        ),
    )

    client.set_enabled("cache", enabled=False)

    assert requests[0].url.path == "/proxies/cache"
    assert requests[0].method == "POST"
    assert requests[0].content.decode() == (
        '{"listen":"0.0.0.0:16379","upstream":"cache:6379","enabled":false}'
    )


def test_unknown_proxy_is_rejected() -> None:
    client = ToxiproxyClient("http://toxiproxy")

    try:
        client.set_enabled("unrelated-service", enabled=False)
    except ValueError as error:
        assert str(error) == "Unknown proxy: unrelated-service"
    else:
        raise AssertionError("Expected an unknown proxy to be rejected")


def test_wait_and_existing_proxy_need_no_creation() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    client = ToxiproxyClient(
        "http://toxiproxy",
        client=httpx.Client(
            base_url="http://toxiproxy",
            transport=httpx.MockTransport(handler),
        ),
    )

    client.wait_until_available(attempts=1)
    client.ensure_proxy(PROXIES["database"])

    assert [request.url.path for request in requests] == [
        "/version",
        "/proxies/database",
    ]


def test_missing_proxy_is_created() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(404)
        return httpx.Response(201, json={})

    client = ToxiproxyClient(
        "http://toxiproxy",
        client=httpx.Client(
            base_url="http://toxiproxy",
            transport=httpx.MockTransport(handler),
        ),
    )

    client.ensure_proxy(PROXIES["cache"])

    assert [request.method for request in requests] == ["GET", "POST"]
    assert requests[1].url.path == "/proxies"


def test_latency_is_replaced_and_can_be_cleared() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "DELETE":
            return httpx.Response(404)
        return httpx.Response(200, json={})

    client = ToxiproxyClient(
        "http://toxiproxy",
        client=httpx.Client(
            base_url="http://toxiproxy",
            transport=httpx.MockTransport(handler),
        ),
    )

    client.add_latency("database", latency_ms=500, jitter_ms=50)

    assert [request.method for request in requests] == ["DELETE", "POST"]
    assert requests[1].url.path == "/proxies/database/toxics"


def test_wait_fails_after_attempt_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    client = ToxiproxyClient(
        "http://toxiproxy",
        client=httpx.Client(
            base_url="http://toxiproxy",
            transport=httpx.MockTransport(handler),
        ),
    )
    monkeypatch.setattr("app.infrastructure.toxiproxy.time.sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="did not become available"):
        client.wait_until_available(attempts=2)
