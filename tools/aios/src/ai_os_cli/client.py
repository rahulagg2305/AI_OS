"""The one real HTTP client every command uses — a thin
:class:`httpx.Client` wrapper attaching the real, stored bearer token
and mapping a genuine timeout to this CLI's own real exit code (6).

This CLI's own tests point ``base_url`` at a real, locally bound
uvicorn server running the real Kernel ASGI app (the identical
"real local HTTP server, real socket" pattern this codebase already
uses pervasively — e.g. ``ai_os_kernel``'s own webhook/notification
tests) rather than a mocked transport.
"""

from __future__ import annotations

from typing import Any

import httpx

from ai_os_cli.config import CliConfig
from ai_os_cli.errors import EXIT_GENERAL_ERROR, EXIT_TIMEOUT, CliError, raise_for_response

_DEFAULT_TIMEOUT_SECONDS = 10.0


class AiosClient:
    def __init__(
        self,
        config: CliConfig,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        headers = {"Authorization": f"Bearer {config.token}"} if config.token else {}
        self._client = httpx.Client(
            base_url=config.base_url,
            headers=headers,
            timeout=timeout_seconds,
        )

    def request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None, **kwargs: Any
    ) -> httpx.Response:
        try:
            response = self._client.request(method, path, json=json, **kwargs)
        except httpx.TimeoutException as exc:
            raise CliError(f"request to '{path}' timed out", exit_code=EXIT_TIMEOUT) from exc
        except httpx.TransportError as exc:
            # Every other real transport failure (connection refused,
            # connection reset, DNS failure) — a genuine, expected
            # condition when the Kernel is unreachable, never a raw
            # traceback for something a script needs a clean, real
            # exit code for.
            raise CliError(
                f"could not reach the Kernel API for '{path}': {exc}", exit_code=EXIT_GENERAL_ERROR
            ) from exc
        raise_for_response(response)
        return response

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(
        self, path: str, *, json: dict[str, Any] | None = None, **kwargs: Any
    ) -> httpx.Response:
        return self.request("POST", path, json=json, **kwargs)

    def patch(
        self, path: str, *, json: dict[str, Any] | None = None, **kwargs: Any
    ) -> httpx.Response:
        return self.request("PATCH", path, json=json, **kwargs)

    def close(self) -> None:
        self._client.close()
