"""Refresh qrsadakat DuckDNS without putting the token in argv or logs."""

import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


TOKEN_FILE = Path(os.environ.get("QRSADAKAT_DUCKDNS_TOKEN_FILE", "/root/secrets/qrsadakat-duckdns-token"))


def main() -> int:
    try:
        token = TOKEN_FILE.read_text().strip()
        if not token:
            raise ValueError("empty token")
        query = urllib.parse.urlencode({"domains": "qrsadakat", "token": token})
        with urllib.request.urlopen("https://www.duckdns.org/update?" + query, timeout=20) as response:
            result = response.read(32).decode().strip()
        if result != "OK":
            print("DuckDNS update rejected", file=sys.stderr)
            return 1
        print("DuckDNS update OK")
        return 0
    except Exception as error:
        # urllib errors may contain the full URL, including the token.
        print("DuckDNS update failed: " + type(error).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
