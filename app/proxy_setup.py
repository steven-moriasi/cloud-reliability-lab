from app.core.config import get_settings
from app.infrastructure.toxiproxy import PROXIES, ToxiproxyClient


def main() -> None:
    client = ToxiproxyClient(get_settings().toxiproxy_url)
    client.wait_until_available()
    for definition in PROXIES.values():
        client.ensure_proxy(definition)


if __name__ == "__main__":
    main()
