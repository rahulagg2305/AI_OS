"""``DockerSandbox`` — the real ADR-0016 Tier 1 :class:`~ai_os_kernel.
sandbox.executor.SandboxExecutor` backend this package's own docstring
and :class:`~ai_os_kernel.sandbox.executor.LocalSubprocessSandbox`'s own
docstring both name as the deferred hardening path.

**Conforms to the existing ``SandboxExecutor`` Protocol unchanged — no
caller needs to change to use it.** :class:`DockerSandbox` implements
the identical ``guarantees``/``execute()`` shape
:class:`~ai_os_kernel.sandbox.executor.LocalSubprocessSandbox` already
does; :class:`~ai_os_kernel.workflow_engine.sandboxed_tool.SandboxedCommandTool`
and every agent in the ``software-engineering`` pack already accept an
injected ``sandbox: SandboxExecutor | None`` — this backend is a drop-in
substitute at that seam, not a redesign of it (ADR-0004).

**Every ADR-0016 Tier 1 control this class's own docstring claims is
genuinely enforced by the Docker Engine itself, not merely attempted:**

- **Network: disabled.** ``network_mode="none"`` — the container gets no
  network interface beyond loopback. Nothing this backend runs can open
  a socket to anything, including the host.
- **Filesystem: contained.** ``read_only=True`` (the container's own
  root filesystem) plus exactly one bind mount — the caller's own
  ``working_directory``, mounted read-write at a fixed in-container path
  (:data:`_CONTAINER_WORKDIR`) — and one ``tmpfs`` mount for scratch
  space (ADR-0016: "``tmpfs`` for scratch"), since a fully read-only
  root would otherwise break ordinary temp-file use. No other host path
  is ever mounted, and there is no parameter to add one — "no per-tool
  override mechanism" is this step's own explicit constraint.
- **Identity: non-root.** ``user`` defaults to UID:GID ``65534:65534``
  ("nobody"/"nogroup" on virtually every Linux distribution) —
  configurable, but never root, and never omitted.
- **Capabilities and privilege escalation: dropped.**
  ``cap_drop=["ALL"]``, ``security_opt=["no-new-privileges"]``.
  ``privileged`` is never set (there is no parameter for it) and the
  default seccomp profile is always retained — this class exposes no
  way to request ``seccomp=unconfined`` or ``--privileged``, matching
  this step's own explicit "no escape hatch" constraint.
- **Resource limits: real.** ``mem_limit``, ``nano_cpus`` (fractional
  CPU count), and ``pids_limit`` are all passed to the Docker Engine
  itself — genuine OS/cgroup-level enforcement, unlike
  ``LocalSubprocessSandbox``'s own documented absence of these (that
  class's own docstring: "enforcing them for a bare subprocess needs
  platform-specific primitives ... left for ... the container backend
  that makes it a configuration line rather than new code" — this is
  that configuration line).
- **Host access: none beyond the one explicit mount.** No Docker socket
  is ever mounted into the container; no other host path is bind-mounted.
- **Secrets: never ambiently present.** Unlike a plain subprocess (which
  inherits nothing here either, but *could* if ``env=None`` were passed
  to a naive ``Popen``), a container's ``environment`` is always exactly
  and only what this backend explicitly constructs — the identical
  "explicit allowlist, never host ``os.environ``" principle
  :func:`~ai_os_kernel.sandbox.executor._minimal_execution_env` already
  established, reused here directly.
- **Lifetime: ephemeral, always removed.** Every :meth:`execute` call
  creates one new container and removes it in a ``finally`` block —
  never reused across calls or across workflow steps.
- **Wall-clock timeout and output cap: both real**, though enforced
  differently than :class:`LocalSubprocessSandbox`'s own live,
  eager-kill-on-cap-exceeded discipline — see :meth:`execute`'s own
  docstring for the honest mechanical difference. The *outcome*
  guarantee is identical either way: a caller never receives more than
  ``max_output_bytes`` per stream, and the container is always killed by
  ``timeout_seconds``.

**Resolved (2026-07-28): the real, load-bearing ``sys.executable``
limitation this class's own docstring used to record here.** This
pack's own agents (``BuildAgentEntrypoint``, ``TestAgentEntrypoint``,
``DocumentationAgentEntrypoint``) and its own pipeline composition
(``ai_os_pack_software_engineering.pipeline``) previously constructed
``command`` sequences using ``sys.executable`` — the *host's own*
absolute interpreter path (e.g. ``C:\\...\\python.exe`` or a venv path
under the Kernel's own working tree). That path never existed inside
this backend's own container filesystem, which has an entirely
different, minimal image. The fix: :attr:`python_command` (below) — a
new property on the ``SandboxExecutor`` Protocol itself, so each
backend declares its own correct, portable interpreter invocation
(``sys.executable`` for :class:`~ai_os_kernel.sandbox.executor.
LocalSubprocessSandbox`, ``python3`` here) and every caller asks its
*injected* sandbox instead of guessing. This class's own tests already
used commands portable by construction (``python3``/``sh`` resolved via
the container image's own ``PATH``) — the same fact that made this
property's own value obvious once the seam existed to hold it.
``DockerSandbox`` is now genuinely wired in as this pack's own real
default backend (see ``ai_os_kernel.sandbox.default_executor``),
``LocalSubprocessSandbox`` remaining explicitly selectable via
``AIOS_SANDBOX_BACKEND=local`` — see that module's own docstring for the
config-driven selection mechanism and its reasoning.

**Client library: the official ``docker`` (docker-py) SDK.** Already an
effective transitive dependency of this project's own dev tooling
(``testcontainers``); now a real, declared dependency of
``ai-os-kernel`` itself, since this module imports it directly in
production code, not test-only code. It ships no inline type
annotations and no ``py.typed`` marker — ``pyproject.toml``'s own
``[[tool.mypy.overrides]]`` for ``docker.*`` records this honestly
(``ignore_missing_imports``), the identical "declare the gap; do not
silently suppress project-wide" treatment already given to other
per-module mypy carve-outs in this codebase.

**"Docker not available" is a clear, typed error, never a crash or a
silent fallback.** Constructing :class:`DockerSandbox` does no I/O at
all (the identical "zero-argument, synchronous, no I/O" constructor
discipline every lazily-built component in this codebase already
follows) — the underlying ``docker.DockerClient`` is built, and the
daemon's own reachability is confirmed via a real ``ping()``, only on
the first :meth:`execute` call, lock-guarded so concurrent first calls
build exactly one shared client. Any failure at that point — no daemon
running, no socket/named pipe reachable, a malformed ``DOCKER_HOST`` —
is caught and re-raised as :class:`DockerSandboxUnavailableError`
(a :class:`~ai_os_kernel.sandbox.errors.SandboxExecutionError`
subclass) with a clear, specific message, never an unhandled
``docker.errors.DockerException``/``requests`` exception reaching the
caller.

**Image, resource limits, and the non-root user are named, documented,
overridable defaults — not hardcoded, unconfigurable magic values.**
:data:`_DEFAULT_IMAGE` (``python:3.12-slim``, tag-pinned, matching this
project's own Python 3.12 requirement) is a first-cut choice; digest
pinning (security_architecture.md §10: "Minimal, pinned by digest") is
recorded as a real, later hardening step once a specific image is
chosen for production use, the identical "documented hardening path,
not a redesign" treatment ADR-0016 itself already gives gVisor.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import docker
import docker.errors
import requests.exceptions

from ai_os_kernel.sandbox.errors import SandboxExecutionError
from ai_os_kernel.sandbox.models import SandboxGuarantees, SandboxResult

# Named, documented first-cut values (ADR-0016: "all from configuration")
# — real limits, not tuned against production workloads yet. All are
# constructor overrides, never hardcoded past construction.
_DEFAULT_IMAGE = "python:3.12-slim"
_DEFAULT_MEMORY_LIMIT = "512m"
_DEFAULT_NANO_CPUS = 1_000_000_000  # 1.0 CPU
_DEFAULT_PIDS_LIMIT = 128
_DEFAULT_USER = "65534:65534"  # nobody:nogroup — never root
_DEFAULT_TMPFS_SIZE = "64m"

_CONTAINER_WORKDIR = "/workspace"
_CONTAINER_TMPDIR = "/tmp"  # noqa: S108 — the in-container tmpfs mount point, not a host path

# The portable interpreter invocation for this backend's own image
# (see `python_command` below): `_DEFAULT_IMAGE`'s official Debian-based
# Python image always provides `python3` on PATH — the image's own
# interpreter, never the host's. A caller-overridden `image` is expected
# to be Python-based too (this backend's own docstring: "matching this
# project's own Python 3.12 requirement"); a non-Python image has no
# reason to go through this property at all.
_CONTAINER_PYTHON_COMMAND: tuple[str, ...] = ("python3",)


class DockerSandboxUnavailableError(SandboxExecutionError):
    """The Docker daemon could not be reached at all — no socket/named
    pipe, no running daemon, or a malformed client configuration. Raised
    in place of letting a raw ``docker.errors.DockerException``/
    ``requests`` exception reach the caller, so "Docker is not
    installed/running here" is always a clear, typed, specific error,
    per this step's own explicit requirement."""


def _minimal_container_env(extra: Mapping[str, str] | None) -> dict[str, str]:
    """Identical philosophy to :func:`~ai_os_kernel.sandbox.executor.
    _minimal_execution_env`: never the host's own ``os.environ`` — a
    container never receives it ambiently anyway (Docker does not
    inherit host environment variables the way a bare ``Popen`` can),
    but this stays explicit and minimal regardless, for the same reason
    that module already gives: an explicit allowlist is a checkable
    guarantee, not an accident of what a container runtime happens not
    to do today."""
    return dict(extra) if extra else {}


_DOCKER_SANDBOX_GUARANTEES = SandboxGuarantees(
    enforces_timeout=True,
    enforces_output_cap=True,
    enforces_secret_exclusion=True,
    enforces_network_isolation=True,
    enforces_filesystem_containment=True,
)


class DockerSandbox:
    """The real ADR-0016 Tier 1 :class:`~ai_os_kernel.sandbox.executor.
    SandboxExecutor` backend — see this module's own docstring for the
    full guarantee-by-guarantee reasoning.

    Every constructor parameter is a named, documented, overridable
    default — never a hidden, unconfigurable magic value — and there is
    deliberately no parameter that would weaken isolation (no "disable
    network isolation for this instance," no "mount an extra host
    path"): this step's own explicit constraint is "one consistent
    Tier 1 posture," not a configurable one.
    """

    def __init__(
        self,
        *,
        image: str = _DEFAULT_IMAGE,
        mem_limit: str = _DEFAULT_MEMORY_LIMIT,
        nano_cpus: int = _DEFAULT_NANO_CPUS,
        pids_limit: int = _DEFAULT_PIDS_LIMIT,
        user: str = _DEFAULT_USER,
        tmpfs_size: str = _DEFAULT_TMPFS_SIZE,
    ) -> None:
        self._image = image
        self._mem_limit = mem_limit
        self._nano_cpus = nano_cpus
        self._pids_limit = pids_limit
        self._user = user
        self._tmpfs_size = tmpfs_size
        self._client: docker.DockerClient | None = None
        self._client_lock = asyncio.Lock()

    @property
    def guarantees(self) -> SandboxGuarantees:
        return _DOCKER_SANDBOX_GUARANTEES

    @property
    def python_command(self) -> tuple[str, ...]:
        """``python3`` — resolved via this backend's own container
        image's own ``PATH``, never the host's ``sys.executable`` (which
        does not exist inside the container's filesystem at all). This
        is the fix for the real, previously-recorded limitation this
        module's own docstring named: agent code that hardcoded
        ``sys.executable`` could not run against this backend. A caller
        that asks its injected sandbox for ``python_command`` instead
        works unmodified against both backends."""
        return _CONTAINER_PYTHON_COMMAND

    async def execute(
        self,
        *,
        command: Sequence[str],
        working_directory: Path,
        timeout_seconds: float,
        max_output_bytes: int,
        env: Mapping[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> SandboxResult:
        """Runs ``command`` inside one new, ephemeral container, then
        removes it — never reused.

        **Timeout and output cap, honestly.** ``container.wait()`` is
        raced against ``timeout_seconds``: on timeout, the container is
        killed and ``timed_out=True`` is reported, with no partial
        output preserved — the identical outcome
        :class:`~ai_os_kernel.sandbox.executor.LocalSubprocessSandbox`'s
        own docstring already commits to ("keeping that path simple and
        its behaviour easy to reason about"). When the command finishes
        within the deadline, its full stdout/stderr are fetched from the
        Docker Engine's own log buffer and truncated client-side to
        ``max_output_bytes`` per stream. This is mechanically different
        from ``LocalSubprocessSandbox``'s own live, eager-kill-the-
        instant-the-cap-is-hit draining loop — a container that produces
        an enormous amount of output before either finishing or hitting
        the wall-clock timeout is not killed early by the cap alone here
        — but the **outcome** guarantee this class's own ``guarantees``
        reports is identical: the caller never receives more than
        ``max_output_bytes`` per stream, ever. The wall-clock timeout
        remains a hard backstop regardless.
        """
        if not command:
            raise SandboxExecutionError("command must not be empty")
        if timeout_seconds <= 0:
            raise SandboxExecutionError(f"timeout_seconds must be positive, got {timeout_seconds}")
        if max_output_bytes <= 0:
            raise SandboxExecutionError(
                f"max_output_bytes must be positive, got {max_output_bytes}"
            )
        if not await asyncio.to_thread(working_directory.is_dir):
            raise SandboxExecutionError(
                f"working_directory {working_directory!r} does not exist or is not a directory"
            )

        client = await self._ensure_client()
        container_env = _minimal_container_env(env)
        start = time.monotonic()

        container = await asyncio.to_thread(
            self._create_and_start_container,
            client,
            command,
            working_directory,
            container_env,
            stdin,
        )
        try:
            timed_out = False
            exit_code: int | None
            try:
                status = await asyncio.to_thread(container.wait, timeout=timeout_seconds)
                exit_code = int(status.get("StatusCode", 0))
            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
                timed_out = True
                exit_code = None
                await asyncio.to_thread(self._kill_ignoring_errors, container)

            if timed_out:
                stdout_text, stderr_text, truncated = "", "", False
            else:
                stdout_bytes, stdout_truncated = await asyncio.to_thread(
                    self._capped_logs, container, "stdout", max_output_bytes
                )
                stderr_bytes, stderr_truncated = await asyncio.to_thread(
                    self._capped_logs, container, "stderr", max_output_bytes
                )
                stdout_text = stdout_bytes.decode(errors="replace")
                stderr_text = stderr_bytes.decode(errors="replace")
                truncated = stdout_truncated or stderr_truncated
        finally:
            await asyncio.to_thread(self._remove_ignoring_errors, container)

        duration = time.monotonic() - start
        return SandboxResult(
            exit_code=exit_code,
            stdout=stdout_text,
            stderr=stderr_text,
            timed_out=timed_out,
            truncated=truncated,
            duration_seconds=duration,
        )

    async def _ensure_client(self) -> docker.DockerClient:
        async with self._client_lock:
            if self._client is None:
                self._client = await asyncio.to_thread(self._build_and_ping_client)
        return self._client

    def _build_and_ping_client(self) -> docker.DockerClient:
        try:
            client = docker.from_env()
            client.ping()
        except (docker.errors.DockerException, requests.exceptions.ConnectionError) as exc:
            raise DockerSandboxUnavailableError(
                "the Docker daemon is not reachable — DockerSandbox requires a running "
                f"Docker (or Docker-API-compatible) daemon: {exc}"
            ) from exc
        return client

    def _create_and_start_container(
        self,
        client: docker.DockerClient,
        command: Sequence[str],
        working_directory: Path,
        env: Mapping[str, str],
        stdin: bytes | None,
    ) -> Any:
        create_kwargs: dict[str, Any] = {
            "image": self._image,
            "command": list(command),
            "working_dir": _CONTAINER_WORKDIR,
            "environment": dict(env),
            "user": self._user,
            "network_mode": "none",
            "read_only": True,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges"],
            "mem_limit": self._mem_limit,
            "nano_cpus": self._nano_cpus,
            "pids_limit": self._pids_limit,
            "volumes": {
                str(working_directory.resolve()): {"bind": _CONTAINER_WORKDIR, "mode": "rw"}
            },
            "tmpfs": {_CONTAINER_TMPDIR: f"size={self._tmpfs_size}"},
            "stdin_open": stdin is not None,
            # Deliberately `detach=False` here, even though this class
            # always manages the container asynchronously itself (create
            # -> attach -> start -> wait -> logs -> remove) regardless of
            # this flag's value — a real, discovered Windows/npipe-specific
            # bug this step's own live verification caught. docker-py's
            # `ContainerConfig` only sets the container's own `StdinOnce`
            # field (and `AttachStdout`/`AttachStderr`) when `detach` is
            # falsy; with `detach=True`, `StdinOnce` stays `False`, and
            # closing the attach socket's write side (`shutdown`/`close`)
            # never reaches the container as stdin EOF on this transport —
            # a command reading until EOF (`cat`, or this pack's own
            # write-file script's `sys.stdin.buffer.read()`) hangs until
            # the wall-clock timeout instead. `detach=False` fixes this
            # (verified directly against a real daemon) and has no other
            # effect on this class's own control flow, which never uses
            # docker-py's own blocking/attached run behaviour either way.
            "detach": False,
        }
        try:
            container = client.containers.create(**create_kwargs)
        except docker.errors.ImageNotFound:
            # Unlike `docker run`, the Docker Engine API's own container
            # create call does not implicitly pull a missing image —
            # pull it explicitly, once, and retry exactly once. A
            # missing image is expected on a fresh host/CI runner, not
            # an error condition in itself.
            try:
                client.images.pull(self._image)
                container = client.containers.create(**create_kwargs)
            except docker.errors.APIError as exc:
                raise SandboxExecutionError(
                    f"sandbox image {self._image!r} is not available locally and could not "
                    f"be pulled: {exc}"
                ) from exc
        except docker.errors.APIError as exc:
            raise SandboxExecutionError(f"failed to create sandboxed container: {exc}") from exc

        # The stdin socket must be attached *before* the container starts,
        # not after — attaching afterward races with the container's own
        # process (which may already be blocked reading, or may have
        # already hit EOF, by the time a post-start attach call completes).
        # A real, discovered bug this step's own live verification caught:
        # attaching after `start()` made `cat` hang until the wall-clock
        # timeout instead of ever seeing this data.
        sock = None
        if stdin is not None:
            sock = self._attach_stdin_socket_best_effort(client, container)

        try:
            container.start()
        except docker.errors.APIError as exc:
            raise SandboxExecutionError(f"failed to start sandboxed container: {exc}") from exc

        if sock is not None and stdin is not None:
            self._write_stdin_best_effort(sock, stdin)
        return container

    @staticmethod
    def _attach_stdin_socket_best_effort(client: docker.DockerClient, container: Any) -> Any | None:
        """Attaches a raw stdin socket to ``container`` before it starts —
        best-effort: a real container run should not fail outright just
        because this platform/version-sensitive attach call did not
        succeed (the wall-clock timeout remains the backstop either way)."""
        try:
            return client.api.attach_socket(container.id, params={"stdin": 1, "stream": 1})
        except Exception:  # noqa: BLE001 — best-effort, documented above
            return None

    @staticmethod
    def _write_stdin_best_effort(sock: Any, data: bytes) -> None:
        """Delivers ``data`` over ``sock`` (already attached to the now-
        running container's own stdin), then closes the write side —
        never raises, the identical "a command that stops reading early
        is a legitimate outcome, not a failure of this sandbox's own job"
        contract :func:`~ai_os_kernel.sandbox.executor._write_stdin_best_effort`
        already establishes for the subprocess backend."""
        try:
            raw = getattr(sock, "_sock", sock)
            try:
                raw.sendall(data)
            finally:
                with contextlib.suppress(OSError):
                    raw.shutdown(1)  # SHUT_WR — signal end-of-input, keep reading open
                sock.close()
        except Exception:  # noqa: BLE001 — best-effort delivery, documented above
            return

    @staticmethod
    def _capped_logs(container: Any, stream: str, limit: int) -> tuple[bytes, bool]:
        """Fetches ``stream`` ("stdout" or "stderr") from the Docker
        Engine's own log buffer and truncates client-side to ``limit``
        bytes — see :meth:`execute`'s own docstring for why this is a
        client-side truncation rather than a live, eager-kill read loop."""
        raw = container.logs(stdout=stream == "stdout", stderr=stream == "stderr", stream=False)
        data = bytes(raw)
        if len(data) > limit:
            return data[:limit], True
        return data, False

    @staticmethod
    def _kill_ignoring_errors(container: Any) -> None:
        with contextlib.suppress(docker.errors.APIError):
            container.kill()

    @staticmethod
    def _remove_ignoring_errors(container: Any) -> None:
        with contextlib.suppress(docker.errors.APIError):
            container.remove(force=True)


__all__ = ["DockerSandbox", "DockerSandboxUnavailableError"]
