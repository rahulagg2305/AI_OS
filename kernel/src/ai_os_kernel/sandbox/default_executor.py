"""Config-driven selection of the default :class:`~ai_os_kernel.sandbox.
executor.SandboxExecutor` — the decision this step exists to make real:
**`DockerSandbox` is now the genuine default Tier 1 backend**, with
`LocalSubprocessSandbox` remaining explicitly available (environments
without Docker, or fast unit tests that do not need real containment).

**Selection mechanism: one environment variable, read once at
construction time — not live Docker-availability probing.** `AIOS_
SANDBOX_BACKEND` (`"docker"`, the default, or `"local"`) follows this
project's own established `AIOS_*` bootstrap-config convention
(`configuration_management.md` §4's own minimal env-var list) — the
identical shape `AIOS_SECRET_BACKEND` already uses to pick a Secrets
Manager backend. This is deliberately *not* "try Docker, catch a
failure, fall back to Local": that would be a new, silent fallback
behaviour this step's own approved framing explicitly excludes ("Do not
build a Docker-unavailable fallback beyond what already exists").
Constructing either backend does zero I/O (both classes' own
constructors are already documented as synchronous and I/O-free) — if
`AIOS_SANDBOX_BACKEND` resolves to `"docker"` and no daemon is actually
reachable, the *existing*, already-built error path fires the moment a
caller's first `execute()` call is made: a clear, typed
:class:`~ai_os_kernel.sandbox.docker_executor.DockerSandboxUnavailableError`,
exactly as it already did before this module existed. Choosing `"local"`
explicitly remains the one supported way to opt out, per this step's own
framing — not a mechanism this module invents on a caller's behalf.

**Why this decision has to live inside each entrypoint's own
constructor default, not "wherever the pack is composed."**
:class:`~ai_os_kernel.workflow_engine.entrypoint_loader.EntrypointLoader`
— the real, `catalog.agents`-driven production path
(:class:`~ai_os_kernel.workflow_engine.registry.SqlAgentRegistry`) —
always constructs an entrypoint with zero arguments (`cls()`). There is
no composition-root call site that could instead pass a different
`sandbox=` argument for the *real* resolution path; the only place the
decision can take effect is inside each entrypoint's own bare-default
resolution (`sandbox or build_default_sandbox_executor()`), which is
exactly where the Software Engineering pack's own
``BuildAgentEntrypoint``/``TestAgentEntrypoint``/``DocumentationAgentEntrypoint``
now call this function.
"""

from __future__ import annotations

import os

from ai_os_kernel.sandbox.docker_executor import DockerSandbox
from ai_os_kernel.sandbox.errors import SandboxExecutionError
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox, SandboxExecutor

ENV_VAR = "AIOS_SANDBOX_BACKEND"
_DEFAULT_BACKEND = "docker"
_KNOWN_BACKENDS = ("docker", "local")


class UnknownSandboxBackendError(SandboxExecutionError):
    """`AIOS_SANDBOX_BACKEND` was set to a value this module does not
    recognize. Raised clearly, rather than silently falling back to
    either backend — a typo in this variable should fail loudly, not
    quietly select the wrong Tier 1 posture."""


def _resolve_backend_name() -> str:
    value = os.environ.get(ENV_VAR, _DEFAULT_BACKEND).strip().lower()
    if value not in _KNOWN_BACKENDS:
        raise UnknownSandboxBackendError(
            f"{ENV_VAR}={value!r} is not recognized; expected one of {_KNOWN_BACKENDS}"
        )
    return value


def build_default_sandbox_executor() -> SandboxExecutor:
    """Returns a real `DockerSandbox()` unless `AIOS_SANDBOX_BACKEND=local`
    is set, in which case a real `LocalSubprocessSandbox()` is returned
    instead. See this module's own docstring for the full reasoning."""
    if _resolve_backend_name() == "local":
        return LocalSubprocessSandbox()
    return DockerSandbox()


def default_python_command() -> tuple[str, ...]:
    """The portable interpreter invocation for whichever backend
    :func:`build_default_sandbox_executor` would construct right now —
    for callers (the delivery pipeline's own `output_transforms`
    callable, which derives a `runCommand` from a persisted step output
    dict and has no sandbox instance of its own to ask) that need the
    command without constructing a full executor. Delegates to the
    executor's own :attr:`~ai_os_kernel.sandbox.executor.SandboxExecutor.
    python_command` rather than duplicating the backend-to-command
    mapping a second time."""
    return build_default_sandbox_executor().python_command


__all__ = [
    "ENV_VAR",
    "UnknownSandboxBackendError",
    "build_default_sandbox_executor",
    "default_python_command",
]
