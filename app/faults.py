import argparse
import time
import uuid

import psycopg

from app.core.config import get_settings


def inject_idle_transaction(seconds: int) -> None:
    settings = get_settings()
    application_name = f"{settings.fault_application_prefix}{uuid.uuid4().hex[:12]}"
    try:
        with psycopg.connect(
            settings.database_url,
            application_name=application_name,
        ) as connection:
            connection.execute("SELECT 1").fetchone()
            print(
                f"Injected idle transaction {application_name}; "
                f"waiting up to {seconds} seconds for remediation"
            )
            time.sleep(seconds)
            connection.rollback()
    except psycopg.OperationalError:
        print(f"Fault session {application_name} was terminated by the remediation agent")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inject scoped reliability-lab failures")
    subparsers = parser.add_subparsers(dest="fault", required=True)
    idle = subparsers.add_parser(
        "idle-transaction",
        help="Open a tagged idle transaction that the remediation agent may terminate",
    )
    idle.add_argument("--seconds", type=int, default=120)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.seconds < 1:
        raise ValueError("seconds must be positive")
    inject_idle_transaction(args.seconds)


if __name__ == "__main__":
    main()
