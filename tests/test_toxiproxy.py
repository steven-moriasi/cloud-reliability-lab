import httpx

from app.infrastructure.toxiproxy import ToxiproxyClient


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
