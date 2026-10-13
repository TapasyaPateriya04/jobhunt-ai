"""Start the local API: ``python -m api``.

Binds to 127.0.0.1 so nothing on the network can reach the resume or the database.
``JOBHUNT_API_PORT`` (default 8787) moves the port when something else holds it.
"""
from __future__ import annotations

import os

DEFAULT_PORT = 8787
HOST = "127.0.0.1"  # loopback only, on purpose: see SECURITY.md


def port() -> int:
    try:
        return int(os.getenv("JOBHUNT_API_PORT") or DEFAULT_PORT)
    except ValueError:
        return DEFAULT_PORT


def main() -> None:
    import uvicorn

    uvicorn.run("api.main:app", host=HOST, port=port(), reload=False, log_level="info")


if __name__ == "__main__":
    main()
