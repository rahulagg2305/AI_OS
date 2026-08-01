"""T1 — Generated code executes hostile actions (security_architecture.md
§4/§5). Real defense: :class:`DockerSandbox`'s Tier 1 controls, genuinely
enforced by the Docker Engine — ``network_mode="none"``, ``read_only=True``
root filesystem, non-root UID. Opt-in, Docker-gated (mirrors
``tests/integration/sandbox/test_docker_sandbox_live.py``'s established
pattern): skips cleanly with no local Docker daemon, runs for real in CI.

Each test below is a genuine attempt at the hostile action T1 names —
network exfiltration, filesystem escape, privilege escalation to root —
run inside a real container, asserting the real Docker Engine refuses it.
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


@pytest.fixture
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
async def test_a_real_network_exfiltration_attempt_is_genuinely_blocked(
    docker_available: None, sandbox: DockerSandbox, tmp_path: Path
) -> None:
    """The hostile action T1 names most directly: generated code trying to
    phone out with whatever it can reach. `network_mode="none"` must
    genuinely deny it, not merely be requested."""
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

    assert result.exit_code != 0
    assert "OSError" in result.stderr or "Network is unreachable" in result.stderr


@pytest.mark.asyncio
async def test_a_real_filesystem_escape_attempt_outside_the_mounted_workdir_is_blocked(
    docker_available: None, sandbox: DockerSandbox, tmp_path: Path
) -> None:
    """A second hostile action: generated code trying to write outside its
    one sanctioned working directory (e.g. to persist a backdoor or tamper
    with the image). The read-only root filesystem must genuinely refuse
    it."""
    result = await sandbox.execute(
        command=["sh", "-c", "echo escaped > /etc/should-not-be-writable"],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    assert result.exit_code != 0
    assert "Read-only file system" in result.stderr


@pytest.mark.asyncio
async def test_a_real_attempt_to_act_as_root_finds_the_container_already_non_root(
    docker_available: None, sandbox: DockerSandbox, tmp_path: Path
) -> None:
    """A third hostile action: generated code assuming it can act with
    root privileges (e.g. installing a package, changing ownership
    system-wide). The container's own identity is never root, so even an
    unmodified attempt to check `id -u` proves the escalation has nowhere
    to start from."""
    result = await sandbox.execute(
        command=["id", "-u"],
        working_directory=tmp_path,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    assert result.exit_code == 0
    assert result.stdout.strip() != "0"
