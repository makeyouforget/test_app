#!/usr/bin/env python3

import os
import sys
import urllib.request

PORT = os.environ.get("HEALTHCHECK_PORT", "8000")
URL = f"http://127.0.0.1:{PORT}/readyz"


def main() -> int:
    try:
        with urllib.request.urlopen(URL, timeout=3) as resp:
            return 0 if resp.status == 200 else 1
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())