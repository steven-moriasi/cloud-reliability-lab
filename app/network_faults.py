import argparse

from app.core.config import get_settings
from app.infrastructure.toxiproxy import ToxiproxyClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Control network failures through Toxiproxy")
    parser.add_argument("dependency", choices=["database", "cache"])
    parser.add_argument("action", choices=["down", "up", "latency", "clear-latency"])
    parser.add_argument("--latency-ms", type=int, default=500)
    parser.add_argument("--jitter-ms", type=int, default=50)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = ToxiproxyClient(get_settings().toxiproxy_url)
    if args.action == "down":
        client.set_enabled(args.dependency, enabled=False)
    elif args.action == "up":
        client.set_enabled(args.dependency, enabled=True)
    elif args.action == "latency":
        if args.latency_ms < 1 or args.jitter_ms < 0:
            raise ValueError("Latency must be positive and jitter cannot be negative")
        client.add_latency(
            args.dependency,
            latency_ms=args.latency_ms,
            jitter_ms=args.jitter_ms,
        )
    else:
        client.clear_latency(args.dependency)
    print(f"{args.dependency}: {args.action}")


if __name__ == "__main__":
    main()
