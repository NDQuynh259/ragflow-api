"""Development server runner with hot reload for Windows & Linux."""

import sys
from pathlib import Path

from watchfiles import PythonFilter, run_process


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    watch_dirs = [
        str(root / "apps"),
        str(root / "core"),
        str(root / "packages"),
    ]
    port = sys.argv[1] if len(sys.argv) > 1 else "8000"
    target = f"uvicorn chat_api.main:app --host 127.0.0.1 --port {port}"
    print(f"[INFO] Starting dev server with watchfiles on port {port}...")
    run_process(*watch_dirs, target=target, watch_filter=PythonFilter())


if __name__ == "__main__":
    main()
