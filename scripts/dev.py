"""Development server runner with hot reload for Windows & Linux."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from watchfiles import PythonFilter, run_process

from core.logging import setup_logging


def run_server(port: int = 8000) -> None:
    """Run uvicorn server with unified root logging."""
    import uvicorn

    setup_logging()
    uvicorn.run("chat_api.main:app", host="127.0.0.1", port=port, log_config=None)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
        run_server(port)
        return

    setup_logging()
    logger = logging.getLogger("dev")

    root = Path(__file__).resolve().parent.parent
    watch_dirs = [
        str(root / "apps"),
        str(root / "core"),
        str(root / "packages"),
    ]
    port = sys.argv[1] if len(sys.argv) > 1 else "8000"
    target = f"{sys.executable} scripts/dev.py --serve {port}"
    logger.info("Starting dev server with watchfiles on port %s...", port)
    run_process(*watch_dirs, target=target, watch_filter=PythonFilter())


if __name__ == "__main__":
    main()
