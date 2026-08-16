#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
import time

import psycopg2


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"wait-for-db: {name} is required", file=sys.stderr)
        sys.exit(2)
    return value


def main() -> int:
    host = _require("POSTGRES_HOST")
    port = os.environ.get("POSTGRES_PORT", "5432").strip() or "5432"
    dbname = _require("POSTGRES_DB")
    user = _require("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    if not password:
        print("wait-for-db: POSTGRES_PASSWORD is required", file=sys.stderr)
        sys.exit(2)

    timeout = float(os.environ.get("DB_WAIT_TIMEOUT", "30"))
    interval = float(os.environ.get("DB_WAIT_INTERVAL", "2"))
    connect_timeout = int(os.environ.get("DB_CONNECT_TIMEOUT", "5"))

    deadline = time.monotonic() + timeout
    attempt = 0
    target = f"{host}:{port}/{dbname}"

    print(f"wait-for-db: waiting for PostgreSQL at {target} (timeout {int(timeout)}s)")
    while True:
        attempt += 1
        try:
            with psycopg2.connect(
                host=host,
                port=port,
                dbname=dbname,
                user=user,
                password=password,
                connect_timeout=connect_timeout,
            ) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            print(f"wait-for-db: {target} is ready (attempt {attempt})")
            return 0
        except psycopg2.OperationalError as exc:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print(
                    f"wait-for-db: timeout after {int(timeout)}s waiting for {target}",
                    file=sys.stderr,
                )
                print(f"wait-for-db: last error: {exc}", file=sys.stderr)
                return 1
            print(
                f"wait-for-db: {target} not ready yet "
                f"({exc.__class__.__name__}); retry in {int(interval)}s "
                f"(attempt {attempt})"
            )
            time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())