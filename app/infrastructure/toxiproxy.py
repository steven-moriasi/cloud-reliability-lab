import time
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class ProxyDefinition:
    name: str
    listen: str
    upstream: str


PROXIES = {
    "database": ProxyDefinition(
        name="database",
        listen="0.0.0.0:15432",
        upstream="db:5432",
    ),
    "cache": ProxyDefinition(
        name="cache",
        listen="0.0.0.0:16379",
        upstream="cache:6379",
    ),
}


class ToxiproxyClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 5,
        client: httpx.Client | None = None,
    ) -> None:
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    def wait_until_available(self, attempts: int = 30) -> None:
        for _ in range(attempts):
            try:
                response = self._client.get("/version")
                response.raise_for_status()
                return
            except httpx.HTTPError:
                time.sleep(1)
        raise RuntimeError("Toxiproxy did not become available")

    def ensure_proxy(self, definition: ProxyDefinition) -> None:
        response = self._client.get(f"/proxies/{definition.name}")
        if response.status_code == 200:
            return
        if response.status_code != 404:
            response.raise_for_status()
        created = self._client.post(
            "/proxies",
            json={
                "name": definition.name,
                "listen": definition.listen,
                "upstream": definition.upstream,
                "enabled": True,
            },
        )
        created.raise_for_status()

    def set_enabled(self, proxy_name: str, *, enabled: bool) -> None:
        definition = self._definition(proxy_name)
        response = self._client.post(
            f"/proxies/{definition.name}",
            json={
                "listen": definition.listen,
                "upstream": definition.upstream,
                "enabled": enabled,
            },
        )
        response.raise_for_status()

    def add_latency(
        self,
        proxy_name: str,
        *,
        latency_ms: int,
        jitter_ms: int,
    ) -> None:
        definition = self._definition(proxy_name)
        self.clear_latency(proxy_name, missing_ok=True)
        response = self._client.post(
            f"/proxies/{definition.name}/toxics",
            json={
                "name": "latency",
                "type": "latency",
                "stream": "downstream",
                "toxicity": 1,
                "attributes": {
                    "latency": latency_ms,
                    "jitter": jitter_ms,
                },
            },
        )
        response.raise_for_status()

    def clear_latency(self, proxy_name: str, *, missing_ok: bool = False) -> None:
        definition = self._definition(proxy_name)
        response = self._client.delete(
            f"/proxies/{definition.name}/toxics/latency"
        )
        if missing_ok and response.status_code == 404:
            return
        response.raise_for_status()

    @staticmethod
    def _definition(proxy_name: str) -> ProxyDefinition:
        try:
            return PROXIES[proxy_name]
        except KeyError as error:
            raise ValueError(f"Unknown proxy: {proxy_name}") from error
