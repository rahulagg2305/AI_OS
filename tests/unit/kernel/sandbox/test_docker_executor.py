"""Unit tests for :class:`~ai_os_kernel.sandbox.docker_executor.DockerSandbox`
— the internal call-construction/timeout/output-capping logic only,
using ``unittest.mock`` against the third-party ``docker`` SDK.

**A deliberate, narrow, first use of a mocking library in this
codebase.** Every other test in this project prefers a real, Protocol-
conformant fake over a mock (ADR-0004/ADR-0015: "a deterministic
Protocol implementation is a legitimate substitute," never mock the
database, and every prior `SandboxExecutor` test in this project runs a
*real* OS subprocess). That approach does not transfer here: `docker`'s
own client/container classes are third-party, not a Protocol this
project owns, and there is no way to write a genuine, in-process "fake
Docker daemon" the way `WorkflowInstanceRepository` has a real
in-memory fake. The choice is therefore between mocking this one
module's own use of a third-party SDK, or having zero coverage at all
for its call-construction logic whenever a real daemon is unavailable
(which it was, again, for this entire session — see
`tests/integration/sandbox/test_docker_sandbox_live.py` for the real,
unmocked proof of the guarantees that actually matter: network
isolation and filesystem containment against a genuine daemon).

These tests verify exactly one thing each: that `DockerSandbox`'s own
Python logic constructs the right Docker API calls and interprets their
results correctly — never that Docker itself behaves as configured
(only a real daemon can prove that; see the integration test above).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import docker.errors
import pytest
import requests.exceptions

from ai_os_kernel.sandbox.docker_executor import DockerSandbox, DockerSandboxUnavailableError
from ai_os_kernel.sandbox.errors import SandboxExecutionError
from ai_os_kernel.sandbox.models import SandboxGuarantees

_GENEROUS_TIMEOUT = 10.0
_GENEROUS_OUTPUT_CAP = 1_000_000


def _mock_container(*, exit_code: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> MagicMock:
    container = MagicMock()
    container.wait.return_value = {"StatusCode": exit_code}

    def _logs(*, stdout: bool = True, stderr: bool = True, stream: bool = False) -> bytes:  # noqa: FBT001, FBT002
        if stdout:
            return stdout_bytes
        if stderr:
            return stderr_bytes
        return b""

    stdout_bytes, stderr_bytes = stdout, stderr
    container.logs.side_effect = _logs
    return container


def _mock_client(container: MagicMock) -> MagicMock:
    client = MagicMock()
    client.containers.create.return_value = container
    return client


def test_docker_sandbox_constructs_with_zero_arguments() -> None:
    sandbox = DockerSandbox()

    assert sandbox.guarantees == SandboxGuarantees(
        enforces_timeout=True,
        enforces_output_cap=True,
        enforces_secret_exclusion=True,
        enforces_network_isolation=True,
        enforces_filesystem_containment=True,
    )


def test_docker_sandbox_python_command_is_python3_not_the_hosts_sys_executable() -> None:
    """The fix for the real, previously-recorded ``sys.executable``
    limitation this class's own docstring named: this backend's own
    container image supplies its interpreter under this name, never the
    host's own path."""
    assert DockerSandbox().python_command == ("python3",)


def test_docker_sandbox_reports_a_materially_fuller_guarantee_matrix_than_local() -> None:
    """The whole point of this step, made concrete and checkable."""
    from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox

    docker_guarantees = DockerSandbox().guarantees
    local_guarantees = LocalSubprocessSandbox().guarantees

    docker_true_count = sum(docker_guarantees.model_dump().values())
    local_true_count = sum(local_guarantees.model_dump().values())
    assert docker_true_count > local_true_count
    assert docker_guarantees.enforces_network_isolation is True
    assert docker_guarantees.enforces_filesystem_containment is True


@pytest.mark.asyncio
async def test_execute_rejects_an_empty_command(tmp_path: Path) -> None:
    with pytest.raises(SandboxExecutionError, match="must not be empty"):
        await DockerSandbox().execute(
            command=[], working_directory=tmp_path, timeout_seconds=1, max_output_bytes=1
        )


@pytest.mark.asyncio
async def test_execute_rejects_a_nonpositive_timeout(tmp_path: Path) -> None:
    with pytest.raises(SandboxExecutionError, match="timeout_seconds must be positive"):
        await DockerSandbox().execute(
            command=["echo"], working_directory=tmp_path, timeout_seconds=0, max_output_bytes=1
        )


@pytest.mark.asyncio
async def test_execute_rejects_a_nonpositive_output_cap(tmp_path: Path) -> None:
    with pytest.raises(SandboxExecutionError, match="max_output_bytes must be positive"):
        await DockerSandbox().execute(
            command=["echo"], working_directory=tmp_path, timeout_seconds=1, max_output_bytes=0
        )


@pytest.mark.asyncio
async def test_execute_rejects_a_nonexistent_working_directory(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    with pytest.raises(SandboxExecutionError, match="does not exist or is not a directory"):
        await DockerSandbox().execute(
            command=["echo"], working_directory=missing, timeout_seconds=1, max_output_bytes=1
        )


@pytest.mark.asyncio
async def test_execute_wraps_a_docker_unavailable_daemon_in_a_clear_typed_error(
    tmp_path: Path,
) -> None:
    with (
        patch("docker.from_env", side_effect=docker.errors.DockerException("no daemon")),
        pytest.raises(DockerSandboxUnavailableError, match="not reachable"),
    ):
        await DockerSandbox().execute(
            command=["echo", "hi"],
            working_directory=tmp_path,
            timeout_seconds=_GENEROUS_TIMEOUT,
            max_output_bytes=_GENEROUS_OUTPUT_CAP,
        )


@pytest.mark.asyncio
async def test_execute_passes_every_required_tier1_control_to_the_docker_api(
    tmp_path: Path,
) -> None:
    """The single most important test in this file: proves this
    backend's own Python code genuinely asks the Docker Engine for
    every ADR-0016 Tier 1 control this class's own docstring claims —
    network disabled, read-only root, dropped capabilities, no new
    privileges, a non-root user, resource limits, and exactly one bind
    mount (the working directory, nothing else)."""
    container = _mock_container(exit_code=0, stdout=b"ok\n")
    client = _mock_client(container)

    with patch("docker.from_env", return_value=client):
        result = await DockerSandbox().execute(
            command=["echo", "ok"],
            working_directory=tmp_path,
            timeout_seconds=_GENEROUS_TIMEOUT,
            max_output_bytes=_GENEROUS_OUTPUT_CAP,
        )

    assert result.exit_code == 0
    assert result.stdout == "ok\n"

    _, kwargs = client.containers.create.call_args
    assert kwargs["network_mode"] == "none"
    assert kwargs["read_only"] is True
    assert kwargs["cap_drop"] == ["ALL"]
    assert kwargs["security_opt"] == ["no-new-privileges"]
    assert kwargs["user"] != "root" and kwargs["user"] != "0"
    assert kwargs["mem_limit"]
    assert kwargs["nano_cpus"] > 0
    assert kwargs["pids_limit"] > 0
    assert "privileged" not in kwargs
    assert kwargs["detach"] is False  # see docker_executor.py's own comment: a real,
    # discovered Windows/npipe stdin-EOF bug depends on this being False, not True
    volumes = kwargs["volumes"]
    assert len(volumes) == 1
    (host_path, mount_spec) = next(iter(volumes.items()))
    resolved_tmp_path = await asyncio.to_thread(tmp_path.resolve)
    assert Path(host_path) == resolved_tmp_path
    assert mount_spec["mode"] == "rw"
    container.start.assert_called_once()
    container.remove.assert_called_once()


@pytest.mark.asyncio
async def test_execute_kills_and_reports_timed_out_when_the_deadline_is_exceeded(
    tmp_path: Path,
) -> None:
    container = _mock_container()
    container.wait.side_effect = requests.exceptions.ReadTimeout("deadline exceeded")
    client = _mock_client(container)

    with patch("docker.from_env", return_value=client):
        result = await DockerSandbox().execute(
            command=["sleep", "999"],
            working_directory=tmp_path,
            timeout_seconds=_GENEROUS_TIMEOUT,
            max_output_bytes=_GENEROUS_OUTPUT_CAP,
        )

    assert result.timed_out is True
    assert result.exit_code is None
    assert result.stdout == ""
    assert result.stderr == ""
    container.kill.assert_called_once()
    container.remove.assert_called_once()


@pytest.mark.asyncio
async def test_execute_truncates_each_stream_independently_at_the_output_cap(
    tmp_path: Path,
) -> None:
    container = _mock_container(exit_code=0, stdout=b"x" * 100, stderr=b"y" * 100)
    client = _mock_client(container)

    with patch("docker.from_env", return_value=client):
        result = await DockerSandbox().execute(
            command=["echo"],
            working_directory=tmp_path,
            timeout_seconds=_GENEROUS_TIMEOUT,
            max_output_bytes=10,
        )

    assert result.truncated is True
    assert result.stdout == "x" * 10
    assert result.stderr == "y" * 10


@pytest.mark.asyncio
async def test_execute_removes_the_container_even_when_the_command_itself_errors(
    tmp_path: Path,
) -> None:
    container = _mock_container(exit_code=1)
    container.logs.side_effect = docker.errors.APIError("boom")
    client = _mock_client(container)

    with patch("docker.from_env", return_value=client), pytest.raises(docker.errors.APIError):
        await DockerSandbox().execute(
            command=["false"],
            working_directory=tmp_path,
            timeout_seconds=_GENEROUS_TIMEOUT,
            max_output_bytes=_GENEROUS_OUTPUT_CAP,
        )

    container.remove.assert_called_once()


def test_docker_sandbox_runtime_is_none_by_default() -> None:
    assert DockerSandbox().runtime is None


def test_docker_sandbox_runtime_is_introspectable_when_configured() -> None:
    assert DockerSandbox(runtime="runsc").runtime == "runsc"


@pytest.mark.asyncio
async def test_execute_omits_the_runtime_key_entirely_when_unconfigured(
    tmp_path: Path,
) -> None:
    """Zero-regression proof: an unconfigured `DockerSandbox` must send
    the Docker Engine exactly the call it always has — not `runtime=None`,
    which is a different (if likely harmless) wire shape than never
    having sent the key at all."""
    container = _mock_container(exit_code=0, stdout=b"ok\n")
    client = _mock_client(container)

    with patch("docker.from_env", return_value=client):
        await DockerSandbox().execute(
            command=["echo", "ok"],
            working_directory=tmp_path,
            timeout_seconds=_GENEROUS_TIMEOUT,
            max_output_bytes=_GENEROUS_OUTPUT_CAP,
        )

    _, kwargs = client.containers.create.call_args
    assert "runtime" not in kwargs


@pytest.mark.asyncio
async def test_execute_passes_the_configured_runtime_to_the_docker_api(
    tmp_path: Path,
) -> None:
    """The ADR-0016 hardening-path configuration line this step adds —
    proves the Python-level plumbing genuinely reaches the Docker API
    call; the real Docker Engine's own acceptance/rejection of a given
    runtime name is proven separately, against a real daemon, in
    `tests/integration/sandbox/test_docker_sandbox_live.py`."""
    container = _mock_container(exit_code=0, stdout=b"ok\n")
    client = _mock_client(container)

    with patch("docker.from_env", return_value=client):
        await DockerSandbox(runtime="runsc").execute(
            command=["echo", "ok"],
            working_directory=tmp_path,
            timeout_seconds=_GENEROUS_TIMEOUT,
            max_output_bytes=_GENEROUS_OUTPUT_CAP,
        )

    _, kwargs = client.containers.create.call_args
    assert kwargs["runtime"] == "runsc"


def test_docker_sandbox_client_is_built_lazily_not_at_construction() -> None:
    """Construction does zero I/O — the identical "synchronous, no I/O
    constructor" discipline every lazily-built component in this
    codebase already follows."""
    with patch("docker.from_env") as from_env:
        DockerSandbox()
        from_env.assert_not_called()


@pytest.mark.asyncio
async def test_execute_accepts_stdin_without_raising_even_when_delivery_fails(
    tmp_path: Path,
) -> None:
    """Stdin delivery is best-effort — a socket/attach failure must
    never fail the overall call, the identical contract
    LocalSubprocessSandbox's own stdin delivery already honours."""
    container = _mock_container(exit_code=0, stdout=b"done\n")
    client: Any = _mock_client(container)
    client.api.attach_socket.side_effect = docker.errors.APIError("attach failed")

    with patch("docker.from_env", return_value=client):
        result = await DockerSandbox().execute(
            command=["cat"],
            working_directory=tmp_path,
            timeout_seconds=_GENEROUS_TIMEOUT,
            max_output_bytes=_GENEROUS_OUTPUT_CAP,
            stdin=b"hello",
        )

    assert result.exit_code == 0
    _, kwargs = client.containers.create.call_args
    assert kwargs["stdin_open"] is True
