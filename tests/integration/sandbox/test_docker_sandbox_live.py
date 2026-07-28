"""The real, unmocked proof of `DockerSandbox`'s own ADR-0016 Tier 1
guarantees — network isolation and filesystem containment — against a
genuine Docker daemon. Unlike
`tests/unit/kernel/sandbox/test_docker_executor.py`'s own mocked tests
(which prove this backend's Python code *asks* the Docker Engine for
the right controls), these tests prove the Docker Engine itself
*enforces* them: a real container, genuinely denied network access and
genuinely confined to its one mounted directory.

**Docker Desktop was unavailable in every session of this project's own
history so far** (`docker ps` fails with a `dockerDesktopLinuxEngine`
named-pipe error) — these tests are skipped, with a clear reason, when
the daemon cannot be reached, exactly the same "opt-in, clearly
skipped, not silently ignored" shape this project's own opt-in-live LLM
tests already use for a missing API key (ADR-0015). Running this file
is the single highest-priority re-verification item once Docker Desktop
is available.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import docker
import docker.errors
import pytest

from ai_os_kernel.sandbox.docker_executor import DockerSandbox

_GENEROUS_TIMEOUT = 30.0
_GENEROUS_OUTPUT_CAP = 65536


@pytest.fixture(scope="module")
def docker_available() -> Generator[None, None, None]:
    try:
        client = docker.from_env()
        client.ping()
    except (docker.errors.DockerException, OSError) as exc:
        pytest.skip(f"Docker daemon is not reachable — this live-container suite is opt-in: {exc}")
    else:
        yield


@pytest.fixture
def sandbox() -> DockerSandbox:
    return DockerSandbox()


@pytest.mark.asyncio
async def test_a_real_container_genuinely_has_no_network_access(
    docker_available: None, sandbox: DockerSandbox, tmp_path: Path
) -> None:
    """`network_mode="none"` must genuinely deny network access, not
    merely be requested — a real DNS/TCP attempt from inside the
    container must fail."""
    result = await sandbox.execute(
        command=[
            "python3",
            "-c",
            "import socket; socket.create_connection(('8.8.8.8', 53), timeout=3)",
        ],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    assert result.timed_out is False
    assert result.exit_code != 0
    assert "OSError" in result.stderr or "Network is unreachable" in result.stderr


@pytest.mark.asyncio
async def test_a_real_container_can_write_inside_the_mounted_working_directory(
    docker_available: None, sandbox: DockerSandbox, tmp_path: Path
) -> None:
    """The one writable path — a real round trip: written inside the
    container, genuinely visible on the host afterward."""
    result = await sandbox.execute(
        command=["sh", "-c", "echo hello-from-container > output.txt"],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    assert result.exit_code == 0
    written = tmp_path / "output.txt"
    assert written.is_file()
    assert written.read_text(encoding="utf-8").strip() == "hello-from-container"


@pytest.mark.asyncio
async def test_a_real_container_genuinely_cannot_write_outside_the_working_directory(
    docker_available: None, sandbox: DockerSandbox, tmp_path: Path
) -> None:
    """The read-only root filesystem must genuinely reject a write
    anywhere outside the one mounted, writable path."""
    result = await sandbox.execute(
        command=["sh", "-c", "echo escaped > /etc/should-not-be-writable"],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    assert result.exit_code != 0
    assert "Read-only file system" in result.stderr


@pytest.mark.asyncio
async def test_a_real_container_genuinely_runs_as_a_non_root_user(
    docker_available: None, sandbox: DockerSandbox, tmp_path: Path
) -> None:
    result = await sandbox.execute(
        command=["id", "-u"],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    assert result.exit_code == 0
    assert result.stdout.strip() != "0"


@pytest.mark.asyncio
async def test_a_real_container_is_genuinely_killed_on_timeout(
    docker_available: None, sandbox: DockerSandbox, tmp_path: Path
) -> None:
    result = await sandbox.execute(
        command=["sleep", "60"],
        working_directory=tmp_path,
        timeout_seconds=2.0,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    assert result.timed_out is True
    assert result.exit_code is None


@pytest.mark.asyncio
async def test_a_real_container_is_genuinely_removed_after_execution(
    docker_available: None, sandbox: DockerSandbox, tmp_path: Path
) -> None:
    """Lifetime: ephemeral, never reused — proven by asking the real
    Docker Engine whether any container from this test still exists."""
    client = docker.from_env()
    before = {c.id for c in client.containers.list(all=True)}

    await sandbox.execute(
        command=["echo", "ephemeral"],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    after = {c.id for c in client.containers.list(all=True)}
    assert after - before == set()


@pytest.mark.asyncio
async def test_stdin_delivery_genuinely_reaches_the_container(
    docker_available: None, sandbox: DockerSandbox, tmp_path: Path
) -> None:
    """The one mechanism this module's own docstring flags as the most
    platform/version-sensitive and least able to be proven by a mock —
    a real byte string, genuinely read back by a real container's own
    stdin."""
    result = await sandbox.execute(
        command=["cat"],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
        stdin=b"hello from the host\n",
    )

    assert result.exit_code == 0
    assert result.stdout == "hello from the host\n"
