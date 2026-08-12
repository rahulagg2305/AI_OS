"""The Sandbox Executor boundary (ADR-0016) and its first real backend.

**``SandboxExecutor`` is a Protocol precisely so a second backend can be
added later with no change to any caller** (ADR-0004: interface-driven,
configuration over code) — this step's own explicit requirement. Every
parameter of :meth:`SandboxExecutor.execute` is something a future
``DockerSandbox``/OCI backend needs too (a command, a working directory,
a wall-clock timeout, a per-stream output cap, an explicit environment);
nothing here is shaped only for a subprocess.

**``LocalSubprocessSandbox`` is a real, working backend — and an
honestly incomplete one.** ADR-0016's own "Alternatives Considered"
rejects "Direct subprocess execution with a restricted user" outright:
"It shares the kernel, filesystem namespace, and network namespace with
the platform, and offers no meaningful containment for hostile code."
This backend does not change that fact — a plain OS subprocess cannot
be given a private network namespace or a filesystem jail without
namespace- or container-level tooling this step explicitly excludes
("no Docker backend implementation ... yet"). What it *does* provide,
fully and genuinely:

- **Secret exclusion (real, not best-effort).** The child process never
  inherits ``os.environ``. Its environment is built from nothing but a
  small, explicit, execution-necessary allowlist (``PATH``, and on
  Windows the handful of variables the OS loader itself needs —
  ``SYSTEMROOT``, ``PATHEXT``) plus whatever the caller explicitly
  passes via ``env``. A credential present in the host process's own
  environment simply is not copied — there is no leak to prevent
  because there is no inheritance to begin with.
- **A real wall-clock timeout.** stdout, stderr, and process exit are
  all raced against one shared deadline; if it elapses first, the
  process is killed and ``timed_out=True`` is reported. No partial
  output is preserved on a timeout — keeping that path simple and its
  behaviour easy to reason about, rather than best-effort salvaging
  output from a process that had to be killed.
- **A real per-stream output cap, enforced eagerly, not just noticed.**
  stdout and stderr are read concurrently, each capped independently at
  ``max_output_bytes``. The moment either stream reports its cap was
  hit, the process is killed immediately (rather than left running,
  blocked writing to a pipe this sandbox has stopped draining, until
  the unrelated wall-clock timeout eventually catches it) — reported as
  ``truncated=True, timed_out=False``, a distinct outcome from a real
  timeout.
- **No ``shell=True``, ever** (security_architecture.md §15).
  ``command`` is a ``Sequence[str]`` executed directly via
  ``asyncio.create_subprocess_exec`` — there is no shell to interpret
  metacharacters, so a value like ``"$(whoami)"`` in an argument is
  passed through literally, never evaluated.
- **Optional ``stdin`` bytes, delivered concurrently with output
  draining, never inherited from the host.** A caller with real data
  to hand the command (the Software Engineering pack's Build Agent
  writing LLM-produced file content, for one) passes it as ``stdin``
  rather than smuggling it through an argument (argv length limits,
  shell-quoting risk) or an environment variable (OS-level size
  limits). When absent, the child's stdin is ``DEVNULL`` — the
  identical "no ambient inheritance" principle already applied to
  ``os.environ``, extended to this stream too. Delivery is best-effort
  from this sandbox's own point of view: a command that exits or
  closes its stdin before reading everything (a legitimate outcome, not
  a bug) does not fail the call.

What it does **not** provide — declared truthfully via
:attr:`LocalSubprocessSandbox.guarantees`, never silently assumed:

- **No network isolation.** Nothing here prevents the executed command
  from opening a socket. This backend must never be used to run
  genuinely untrusted or hostile code for that reason alone — it exists
  to prove the Protocol shape and to serve development/testing, not to
  satisfy ADR-0016 Tier 1 for real. Real network denial (``--network=none``)
  is a container-level control — :class:`~ai_os_kernel.sandbox.
  docker_executor.DockerSandbox` now provides it for real.
- **No filesystem containment.** ``working_directory`` sets the
  child's starting current working directory and is validated to exist
  — it is not a jail. A command executed here can still read or write
  paths outside it via an absolute path or ``..``, exactly the
  containment ADR-0016 assigns to the container's read-only root and
  single writable mount, not to application-level cwd-setting —
  :class:`~ai_os_kernel.sandbox.docker_executor.DockerSandbox` now
  provides that containment for real.
- **No memory/CPU/PID limits.** ADR-0016 lists these as configuration
  on the OCI runtime; enforcing them for a bare subprocess needs
  platform-specific primitives (POSIX ``resource.setrlimit``, Windows
  Job Objects) this backend still does not implement —
  :class:`~ai_os_kernel.sandbox.docker_executor.DockerSandbox` now
  enforces all three as real configuration on the container runtime,
  exactly the "configuration line, not new code" outcome this docstring
  once only anticipated.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import platform
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from ai_os_kernel.sandbox.errors import SandboxExecutionError
from ai_os_kernel.sandbox.models import SandboxGuarantees, SandboxResult

# Read chunk size for draining stdout/stderr — large enough to be
# efficient, small enough that a per-stream cap is enforced promptly
# rather than after one huge read.
_READ_CHUNK_BYTES = 65536


def _finished_result[T, R](task: asyncio.Task[T], default: R) -> T | R:
    """``task.result()`` if it genuinely completed, else ``default`` —
    used after a kill-triggered cleanup where some tasks resolved
    before the signal and others were cancelled by it."""
    if task.done() and not task.cancelled():
        return task.result()
    return default


class SandboxExecutor(Protocol):
    """Persistence-free execution boundary for Tier 1 untrusted work —
    the seam a fake implementation substitutes in unit tests (ADR-0004:
    interface-driven, configuration over code), and the seam a future
    ``DockerSandbox``/OCI backend implements identically."""

    @property
    def guarantees(self) -> SandboxGuarantees:
        """Which ADR-0016 Tier 1 controls this implementation actually
        enforces at the OS level — see :class:`~ai_os_kernel.sandbox.
        models.SandboxGuarantees` for why this exists."""
        ...

    @property
    def python_command(self) -> tuple[str, ...]:
        """The portable argv prefix that invokes a Python interpreter
        *inside whatever this backend actually runs commands in* —
        added to resolve a real, discovered gap: a caller (the
        Software Engineering pack's Build/Documentation/pipeline code)
        that hardcodes ``sys.executable`` is naming the *host's* own
        interpreter path, which is meaningless inside a container image
        with an entirely separate filesystem. Each backend knows the
        one correct answer for itself — :class:`LocalSubprocessSandbox`
        runs directly on the host, so ``sys.executable`` genuinely is
        the right, portable answer there; a container backend's own
        image supplies its own interpreter under its own name on its
        own ``PATH``, which is never the host's path. A caller asks its
        *injected* sandbox for this instead of guessing, which is what
        makes the same agent code work unmodified against either
        backend."""
        ...

    async def execute(
        self,
        *,
        command: Sequence[str],
        working_directory: Path,
        timeout_seconds: float,
        max_output_bytes: int,
        env: Mapping[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> SandboxResult: ...


async def _read_capped(stream: asyncio.StreamReader, limit: int) -> tuple[bytes, bool]:
    """Drain ``stream`` up to ``limit`` bytes. Returns the bytes read and
    whether the stream was still producing output when the cap was hit
    (``truncated``). Stops draining once the cap is reached — see this
    module's own docstring for why that is safe (the caller's overall
    timeout remains the backstop)."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await stream.read(_READ_CHUNK_BYTES)
        if not chunk:
            return b"".join(chunks), False
        remaining = limit - total
        if remaining <= 0:
            return b"".join(chunks), True
        if len(chunk) > remaining:
            chunks.append(chunk[:remaining])
            return b"".join(chunks), True
        chunks.append(chunk)
        total += len(chunk)


async def _write_stdin_best_effort(process: asyncio.subprocess.Process, data: bytes) -> None:
    """Deliver ``data`` to ``process``'s stdin, then close it. Never
    raises: a command that exits or stops reading before every byte is
    delivered is a legitimate outcome (it may not need all of it), not
    a failure of this sandbox's own job — see this module's own
    docstring's "Optional stdin" section."""
    if process.stdin is None:
        return
    try:
        process.stdin.write(data)
        await process.stdin.drain()
    except (BrokenPipeError, ConnectionResetError):
        return
    finally:
        if not process.stdin.is_closing():
            process.stdin.close()


def _minimal_execution_env(extra: Mapping[str, str] | None) -> dict[str, str]:
    """The smallest environment a subprocess needs to actually run,
    plus whatever the caller explicitly opts in via ``extra`` — never
    the host process's own ``os.environ``. See this module's own
    docstring's "Secret exclusion" section."""
    env: dict[str, str] = {}
    path = os.environ.get("PATH")
    if path is not None:
        env["PATH"] = path
    if platform.system() == "Windows":
        for name in ("SYSTEMROOT", "PATHEXT", "COMSPEC"):
            value = os.environ.get(name)
            if value is not None:
                env[name] = value
    if extra:
        env.update(extra)
    return env


_LOCAL_SUBPROCESS_GUARANTEES = SandboxGuarantees(
    enforces_timeout=True,
    enforces_output_cap=True,
    enforces_secret_exclusion=True,
    enforces_network_isolation=False,
    enforces_filesystem_containment=False,
)


class LocalSubprocessSandbox:
    """The development/testing :class:`SandboxExecutor` backend: a real
    OS subprocess, no container. See this module's own docstring for
    exactly which ADR-0016 Tier 1 controls this backend does and does
    not enforce — :attr:`guarantees` reports the same thing
    programmatically."""

    @property
    def guarantees(self) -> SandboxGuarantees:
        return _LOCAL_SUBPROCESS_GUARANTEES

    @property
    def python_command(self) -> tuple[str, ...]:
        """``sys.executable`` — this backend runs commands directly on
        the host, using the same interpreter as the calling process, so
        the host's own interpreter path is exactly correct here (unlike
        a container backend, where it would be meaningless)."""
        return (sys.executable,)

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
        if not command:
            raise SandboxExecutionError("command must not be empty")
        if timeout_seconds <= 0:
            raise SandboxExecutionError(f"timeout_seconds must be positive, got {timeout_seconds}")
        if max_output_bytes <= 0:
            raise SandboxExecutionError(
                f"max_output_bytes must be positive, got {max_output_bytes}"
            )
        # A stat() call, run off the event loop thread (ASYNC240) rather
        # than accepted as a brief blocking call — this project depends
        # on neither trio nor anyio, so asyncio.to_thread is the correct
        # fix, not a suppression.
        if not await asyncio.to_thread(working_directory.is_dir):
            raise SandboxExecutionError(
                f"working_directory {working_directory!r} does not exist or is not a directory"
            )

        sandbox_env = _minimal_execution_env(env)
        start = time.monotonic()

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(working_directory),
                env=sandbox_env,
                stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise SandboxExecutionError(
                f"failed to start sandboxed command {command!r}: {exc}"
            ) from exc

        if process.stdout is None or process.stderr is None:
            # Unreachable given stdout=PIPE, stderr=PIPE are always
            # passed to create_subprocess_exec above, but narrows the
            # type for mypy --strict without a bare `assert`
            # (ruff S101 is enforced outside tests, per pyproject.toml).
            raise SandboxExecutionError("subprocess was not created with piped stdout/stderr")

        extra_tasks: set[asyncio.Task[None]] = set()
        if stdin is not None:
            extra_tasks.add(asyncio.ensure_future(_write_stdin_best_effort(process, stdin)))

        stdout_task: asyncio.Task[tuple[bytes, bool]] = asyncio.ensure_future(
            _read_capped(process.stdout, max_output_bytes)
        )
        stderr_task: asyncio.Task[tuple[bytes, bool]] = asyncio.ensure_future(
            _read_capped(process.stderr, max_output_bytes)
        )
        wait_task: asyncio.Task[int] = asyncio.ensure_future(process.wait())
        read_tasks = (stdout_task, stderr_task)
        pending: set[asyncio.Task[tuple[bytes, bool]] | asyncio.Task[int] | asyncio.Task[None]] = {
            stdout_task,
            stderr_task,
            wait_task,
            *extra_tasks,
        }

        # A stream that exceeds its cap is treated as an immediate,
        # actionable signal — kill the process as soon as that is
        # known, rather than passively waiting out the full timeout
        # while the child blocks writing to a pipe this sandbox has
        # stopped draining. Looping on FIRST_COMPLETED (bounded by the
        # overall deadline) is what lets a fast cap breach be reported
        # as `truncated=True, timed_out=False` instead of being
        # indistinguishable from a real timeout.
        deadline = time.monotonic() + timeout_seconds
        cap_exceeded = False
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            _, pending = await asyncio.wait(
                pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
            )
            if any(task.result()[1] for task in read_tasks if task.done()):
                cap_exceeded = True
                break

        if cap_exceeded or pending:
            # Kill *before* cancelling: on Windows' ProactorEventLoop, a
            # Task cancelled while blocked on a pending subprocess-pipe
            # read does not reliably unblock — the underlying OS read
            # only completes once the pipe actually produces data or
            # closes. Killing first closes both pipe ends, which lets
            # every pending read (and the process-exit wait) resolve
            # promptly on its own; cancel() below is then only cleanup.
            if not wait_task.done():
                process.kill()
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

        # Close the child's transport deterministically instead of
        # leaving it to garbage collection (R-015, 2026-08-12).
        #
        # `asyncio` never closes a subprocess transport for you. Left to
        # GC, `_ProactorBasePipeTransport.__del__` on Windows emits an
        # "unclosed transport" ResourceWarning, and formatting its own
        # `repr()` for that warning calls `fileno()` on a pipe that is
        # already closed, which raises. Because it happens in a
        # finaliser it is an *unraisable* exception, so pytest attributes
        # it to whichever unrelated test is running during that GC pass —
        # which is why two innocent, unrelated tests in
        # `tests/unit/kernel/llm_gateway/adapters/test_local_adapter.py`
        # failed on separate full-suite runs while that file passes 27/27
        # in isolation.
        #
        # Verbatim from a real `tests/unit` run, before this call:
        #     Exception ignored in: <function
        #       _ProactorBasePipeTransport.__del__>
        #     ...  _warn(f"unclosed transport {self!r}", ResourceWarning)
        #     ...  info.append(f'fd={self._sock.fileno()}')
        #     ValueError: I/O operation on closed pipe
        # pytest listed `test_execute_delivers_stdin_bytes_to_the_command`
        # -- this executor's own stdin path -- among the active tests.
        #
        # `_transport` is private only because `asyncio.subprocess.Process`
        # exposes no public equivalent; closing it is the documented
        # remedy and is idempotent, so the clean path is covered too.
        # Suppressed because failing to close a pipe must never turn a
        # genuinely successful command into an error.
        transport = getattr(process, "_transport", None)
        if transport is not None:
            with contextlib.suppress(Exception):
                transport.close()

        if cap_exceeded:
            stdout_bytes, stdout_truncated = _finished_result(stdout_task, (b"", True))
            stderr_bytes, stderr_truncated = _finished_result(stderr_task, (b"", True))
            exit_code = _finished_result(wait_task, None)
            timed_out = False
        elif pending:
            stdout_bytes, stderr_bytes = b"", b""
            stdout_truncated = stderr_truncated = False
            exit_code = None
            timed_out = True
        else:
            stdout_bytes, stdout_truncated = stdout_task.result()
            stderr_bytes, stderr_truncated = stderr_task.result()
            exit_code = wait_task.result()
            timed_out = False

        duration = time.monotonic() - start
        return SandboxResult(
            exit_code=exit_code,
            stdout=stdout_bytes.decode(errors="replace"),
            stderr=stderr_bytes.decode(errors="replace"),
            timed_out=timed_out,
            truncated=stdout_truncated or stderr_truncated,
            duration_seconds=duration,
        )
