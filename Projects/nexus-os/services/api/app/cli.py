"""``nexus`` command line: serve, migrate, doctor."""

from __future__ import annotations

import argparse
import platform
import sys

from app import __version__, migrate
from app.core.secrets import build_secret_store
from app.core.settings import Settings


def _serve(settings: Settings) -> int:
    import uvicorn

    settings.ensure_home()
    migrate.upgrade(settings.sync_db_url)
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )
    return 0


def _doctor(settings: Settings) -> int:
    settings.ensure_home()
    store = build_secret_store(settings.home)
    print(f"NEXUS API {__version__}")
    print(f"python      {sys.version.split()[0]} on {platform.platform()}")
    print(f"home        {settings.home}")
    print(f"database    {settings.db_path} (schema {migrate.current_revision(settings.sync_db_url)})")
    print(f"secrets     {store.describe()}")
    print(f"bind        {settings.host}:{settings.port}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nexus", description="NEXUS OS local API")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve", help="run migrations and start the API")
    sub.add_parser("migrate", help="apply database migrations")
    sub.add_parser("doctor", help="print environment diagnostics")
    args = parser.parse_args(argv)
    settings = Settings()
    if args.cmd == "serve":
        return _serve(settings)
    if args.cmd == "migrate":
        settings.ensure_home()
        migrate.upgrade(settings.sync_db_url)
        print(f"schema at {migrate.current_revision(settings.sync_db_url)}")
        return 0
    return _doctor(settings)


if __name__ == "__main__":
    raise SystemExit(main())
