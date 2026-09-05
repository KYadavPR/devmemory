"""
Dashboard launcher for test_app.
Finds an open port (starting at 8765) and launches uvicorn server.
"""

import os
import sys
import socket

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import uvicorn
from devmemory.web.app import create_app
from devmemory import DevMemoryProject


def _find_free_port(start_port=8765, max_attempts=10):
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start_port


if __name__ == "__main__":
    port = _find_free_port(8765)
    print(f"\nStarting DevMemory Dashboard for test_app at http://127.0.0.1:{port} ...\n")
    app = create_app(current_dir)
    uvicorn.run(app, host="127.0.0.1", port=port)
