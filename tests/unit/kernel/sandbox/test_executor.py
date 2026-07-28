"""LocalSubprocessSandbox — a real OS subprocess backend, so these are
genuine (not mocked) executions; no Docker/testcontainers dependency,
unlike this codebase's database-writer tests. Every test invokes
``sys.executable`` (the interpreter already running pytest) rather than
a shell built-in, so the suite is portable across Windows and Linux
without relying on any specific shell.

Proves, per this step's own requirement, real (not happy-path-only)
behaviour: a secret present in the *test process's own* environment
never reaches the sandboxed child (ADR-0016 "no secrets"), shell
metacharacters are never interpreted (security_architecture.md §15 —
no ``shell=True``), a wall-clock timeout genuinely kills a hanging
process, and an output cap genuinely truncates and stops draining a
runaway stream. It also proves the backend's own :class:`SandboxGuarantees`
honestly reports what it does *not* enforce (network/filesystem
containment) — see :mod:`ai_os_kernel.sandbox.executor`'s own docstring
for why that matters more than a green test here would otherwise imply.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from ai_os_kernel.sandbox.errors import SandboxExecutionError
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sandbox.models import SandboxGuarantees

_PYTHON = sys.executable
_GENEROUS_TIMEOUT = 10.0
_GENEROUS_OUTPUT_CAP = 1_000_000


@pytest.fixture
def sandbox() -> LocalSubprocessSandbox:
    return LocalSubprocessSandbox()


@pytest.mark.asyncio
async def test_execute_returns_stdout_and_exit_code_of_a_successful_command(
    sandbox: LocalSubprocessSandbox, tmp_path: Path
) -> None:
    result = await sandbox.execute(
        command=[_PYTHON, "-c", "print('hello from the sandbox')"],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "hello from the sandbox"
    assert result.timed_out is False
    assert result.truncated is False
    assert result.duration_seconds >= 0.0


@pytest.mark.asyncio
async def test_execute_captures_a_nonzero_exit_code_without_raising(
    sandbox: LocalSubprocessSandbox, tmp_path: Path
) -> None:
    result = await sandbox.execute(
        command=[_PYTHON, "-c", "import sys; sys.exit(7)"],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    assert result.exit_code == 7


@pytest.mark.asyncio
async def test_execute_captures_stderr_separately_from_stdout(
    sandbox: LocalSubprocessSandbox, tmp_path: Path
) -> None:
    result = await sandbox.execute(
        command=[
            _PYTHON,
            "-c",
            "import sys; sys.stdout.write('to-stdout'); sys.stderr.write('to-stderr')",
        ],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    assert result.stdout == "to-stdout"
    assert result.stderr == "to-stderr"


@pytest.mark.asyncio
async def test_execute_runs_in_the_given_working_directory(
    sandbox: LocalSubprocessSandbox, tmp_path: Path
) -> None:
    result = await sandbox.execute(
        command=[_PYTHON, "-c", "import os; print(os.getcwd())"],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    reported_cwd = Path(result.stdout.strip())
    resolved_reported, resolved_expected = await asyncio.gather(
        asyncio.to_thread(reported_cwd.resolve), asyncio.to_thread(tmp_path.resolve)
    )
    assert resolved_reported == resolved_expected


@pytest.mark.asyncio
async def test_execute_kills_a_hanging_process_on_timeout(
    sandbox: LocalSubprocessSandbox, tmp_path: Path
) -> None:
    result = await sandbox.execute(
        command=[_PYTHON, "-c", "import time; time.sleep(30)"],
        working_directory=tmp_path,
        timeout_seconds=0.5,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    assert result.timed_out is True
    assert result.exit_code is None
    assert result.duration_seconds < 30.0


@pytest.mark.asyncio
async def test_execute_truncates_output_that_exceeds_the_cap(
    sandbox: LocalSubprocessSandbox, tmp_path: Path
) -> None:
    result = await sandbox.execute(
        command=[_PYTHON, "-c", "import sys; sys.stdout.write('A' * 1_000_000)"],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=100,
    )

    assert result.truncated is True
    assert len(result.stdout) <= 100


@pytest.mark.asyncio
async def test_execute_does_not_leak_a_secret_from_the_test_processs_own_environment(
    sandbox: LocalSubprocessSandbox, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real, load-bearing test this step's own requirement names:
    a secret genuinely present in the *parent* (test) process's
    environment must not reach the sandboxed child — proving
    ``enforces_secret_exclusion`` is real, not aspirational."""
    monkeypatch.setenv("AIOS_TEST_SECRET_TOKEN", "super-secret-value-must-not-leak")

    result = await sandbox.execute(
        command=[
            _PYTHON,
            "-c",
            "import os; print(repr(os.environ.get('AIOS_TEST_SECRET_TOKEN')))",
        ],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    assert "super-secret-value-must-not-leak" not in result.stdout
    assert result.stdout.strip() == "None"


@pytest.mark.asyncio
async def test_execute_does_not_leak_any_ambient_environment_variable_by_default(
    sandbox: LocalSubprocessSandbox, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Broader than the single-secret test above: no arbitrary ambient
    variable from the host process crosses into the sandbox unless the
    caller explicitly opts it in via ``env=``."""
    monkeypatch.setenv("AIOS_TEST_ARBITRARY_MARKER", "should-not-be-visible")

    result = await sandbox.execute(
        command=[_PYTHON, "-c", "import os; print('AIOS_TEST_ARBITRARY_MARKER' in os.environ)"],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    assert result.stdout.strip() == "False"


@pytest.mark.asyncio
async def test_execute_passes_through_only_explicitly_provided_env_vars(
    sandbox: LocalSubprocessSandbox, tmp_path: Path
) -> None:
    result = await sandbox.execute(
        command=[_PYTHON, "-c", "import os; print(os.environ.get('EXPLICIT_VAR'))"],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
        env={"EXPLICIT_VAR": "explicit-value"},
    )

    assert result.stdout.strip() == "explicit-value"


@pytest.mark.asyncio
async def test_execute_does_not_interpret_shell_metacharacters(
    sandbox: LocalSubprocessSandbox, tmp_path: Path
) -> None:
    """security_architecture.md §15: no ``shell=True``, ever. A literal
    shell-command-substitution-looking string in an argument must be
    printed verbatim, never evaluated."""
    payload = "$(echo INJECTED) `echo INJECTED` && echo INJECTED"

    result = await sandbox.execute(
        command=[_PYTHON, "-c", "import sys; print(sys.argv[1])", payload],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    # If a shell were interpreting this, the command substitutions and
    # `&&` would have run and "INJECTED" would appear on its own, not
    # embedded verbatim inside the original payload string.
    assert result.stdout.strip() == payload


@pytest.mark.asyncio
async def test_execute_rejects_an_empty_command(
    sandbox: LocalSubprocessSandbox, tmp_path: Path
) -> None:
    with pytest.raises(SandboxExecutionError, match="command must not be empty"):
        await sandbox.execute(
            command=[],
            working_directory=tmp_path,
            timeout_seconds=_GENEROUS_TIMEOUT,
            max_output_bytes=_GENEROUS_OUTPUT_CAP,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout_seconds", [0, -1.0])
async def test_execute_rejects_a_non_positive_timeout(
    sandbox: LocalSubprocessSandbox, tmp_path: Path, timeout_seconds: float
) -> None:
    with pytest.raises(SandboxExecutionError, match="timeout_seconds must be positive"):
        await sandbox.execute(
            command=[_PYTHON, "-c", "pass"],
            working_directory=tmp_path,
            timeout_seconds=timeout_seconds,
            max_output_bytes=_GENEROUS_OUTPUT_CAP,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("max_output_bytes", [0, -1])
async def test_execute_rejects_a_non_positive_max_output_bytes(
    sandbox: LocalSubprocessSandbox, tmp_path: Path, max_output_bytes: int
) -> None:
    with pytest.raises(SandboxExecutionError, match="max_output_bytes must be positive"):
        await sandbox.execute(
            command=[_PYTHON, "-c", "pass"],
            working_directory=tmp_path,
            timeout_seconds=_GENEROUS_TIMEOUT,
            max_output_bytes=max_output_bytes,
        )


@pytest.mark.asyncio
async def test_execute_rejects_a_nonexistent_working_directory(
    sandbox: LocalSubprocessSandbox, tmp_path: Path
) -> None:
    missing = tmp_path / "does-not-exist"

    with pytest.raises(SandboxExecutionError, match="does not exist or is not a directory"):
        await sandbox.execute(
            command=[_PYTHON, "-c", "pass"],
            working_directory=missing,
            timeout_seconds=_GENEROUS_TIMEOUT,
            max_output_bytes=_GENEROUS_OUTPUT_CAP,
        )


@pytest.mark.asyncio
async def test_execute_raises_a_clear_error_when_the_executable_does_not_exist(
    sandbox: LocalSubprocessSandbox, tmp_path: Path
) -> None:
    with pytest.raises(SandboxExecutionError, match="failed to start sandboxed command"):
        await sandbox.execute(
            command=["this-executable-does-not-exist-anywhere"],
            working_directory=tmp_path,
            timeout_seconds=_GENEROUS_TIMEOUT,
            max_output_bytes=_GENEROUS_OUTPUT_CAP,
        )


@pytest.mark.asyncio
async def test_execute_delivers_stdin_bytes_to_the_command(
    sandbox: LocalSubprocessSandbox, tmp_path: Path
) -> None:
    result = await sandbox.execute(
        command=[_PYTHON, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
        stdin=b"hello via stdin",
    )

    assert result.stdout == "hello via stdin"


@pytest.mark.asyncio
async def test_execute_does_not_hang_when_stdin_is_none_and_the_command_reads_it(
    sandbox: LocalSubprocessSandbox, tmp_path: Path
) -> None:
    """No ``stdin`` supplied means the child's stdin is ``DEVNULL``, not
    inherited from this test process — a read must see immediate EOF,
    never block waiting for input nobody will ever supply."""
    result = await sandbox.execute(
        command=[_PYTHON, "-c", "import sys; sys.stdout.write(repr(sys.stdin.read()))"],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    assert result.stdout == "''"
    assert result.timed_out is False


@pytest.mark.asyncio
async def test_execute_does_not_fail_when_the_command_never_reads_stdin(
    sandbox: LocalSubprocessSandbox, tmp_path: Path
) -> None:
    """Delivery is best-effort: a command that exits without reading
    (any of) its stdin must not turn into a sandbox-level failure."""
    result = await sandbox.execute(
        command=[_PYTHON, "-c", "print('done')"],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
        stdin=b"nobody will ever read this",
    )

    assert result.stdout.strip() == "done"
    assert result.exit_code == 0


def test_local_subprocess_sandbox_declares_its_real_guarantees_honestly(
    sandbox: LocalSubprocessSandbox,
) -> None:
    """The guarantees matrix must truthfully report that this backend
    does not provide network or filesystem containment — the whole
    point of :class:`~ai_os_kernel.sandbox.models.SandboxGuarantees`,
    per this module's own docstring, is that nothing downstream can
    mistake this backend for a full ADR-0016 Tier 1 implementation."""
    assert sandbox.guarantees == SandboxGuarantees(
        enforces_timeout=True,
        enforces_output_cap=True,
        enforces_secret_exclusion=True,
        enforces_network_isolation=False,
        enforces_filesystem_containment=False,
    )
