"""Shared real, locally bound Kernel server helper — the identical
`_postgres_fixture.py`'s own role, but for a real, running Kernel ASGI
app rather than a real Postgres container.

Used by more than one workspace member's own tests (`tools/aios`,
`capability_packs/voice_jarvis`) — first duplicated inline in each,
then extracted here once a second real consumer made the duplication
a genuine problem (a real `mypy` "Duplicate module named conftest"
collision between two identically-shaped, independently-written
fixture files), not merely aesthetic.
"""

from __future__ import annotations

import socket
import threading
import time

import uvicorn
from fastapi import FastAPI


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


class RunningKernel:
    def __init__(self, base_url: str, server: uvicorn.Server, thread: threading.Thread) -> None:
        self.base_url = base_url
        self._server = server
        self._thread = thread

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=10)


def start_live_kernel(app: FastAPI) -> RunningKernel:
    """Starts a real, already-built Kernel ASGI app on a real,
    locally bound socket, in a real background thread — the caller
    owns building ``app`` (via ``ai_os_kernel.bootstrap.build_app``)
    so this helper stays independent of any one caller's own
    ``PlatformConfig`` shape."""
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    return RunningKernel(f"http://127.0.0.1:{port}", server, thread)
