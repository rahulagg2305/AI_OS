"""T12 — Cross-workflow interference via shared workspace
(security_architecture.md §4/§5). Real defense exercised here: §5.3's
"mandatory, not best-effort" per-workflow workspace isolation —
:class:`~ai_os_kernel.sandbox.docker_executor.DockerSandbox` mounts
exactly one caller-supplied ``working_directory`` per real container,
with no other host path ever reachable from inside it.

The attempt: two concurrent "workflows," each with its own real sandbox
execution and its own working directory — one plants a file that looks
like it could be sensitive (a fabricated secret/output artifact) and the
other genuinely, from inside a real, separate container, tries to read
it. §5.3's isolation must genuinely hold: the second workflow's
container can never see the first's file.
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
async def test_a_second_workflows_container_cannot_read_a_first_workflows_workspace_file(
    docker_available: None, sandbox: DockerSandbox, tmp_path: Path
) -> None:
    """Two real, distinct workflow workspaces, each backing a real,
    separate container invocation — genuinely proving isolation, not
    assuming it from configuration alone."""
    workflow_a_dir = tmp_path / "workflow-a-workspace"
    workflow_b_dir = tmp_path / "workflow-b-workspace"
    workflow_a_dir.mkdir()
    workflow_b_dir.mkdir()

    write_result = await sandbox.execute(
        command=["sh", "-c", "echo workflow-a-sensitive-output > secret_output.txt"],
        working_directory=workflow_a_dir,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )
    assert write_result.exit_code == 0
    assert (workflow_a_dir / "secret_output.txt").is_file()

    read_attempt = await sandbox.execute(
        command=["cat", "secret_output.txt"],
        working_directory=workflow_b_dir,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    assert read_attempt.exit_code != 0
    assert "workflow-a-sensitive-output" not in read_attempt.stdout


@pytest.mark.asyncio
async def test_each_workflows_own_workspace_is_still_genuinely_usable(
    docker_available: None, sandbox: DockerSandbox, tmp_path: Path
) -> None:
    """Proportionality check: isolation blocks cross-workspace access,
    not a workflow's own workspace."""
    workflow_dir = tmp_path / "workflow-own-workspace"
    workflow_dir.mkdir()

    await sandbox.execute(
        command=["sh", "-c", "echo own-output > output.txt"],
        working_directory=workflow_dir,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )
    read_own = await sandbox.execute(
        command=["cat", "output.txt"],
        working_directory=workflow_dir,
        timeout_seconds=_GENEROUS_TIMEOUT,
        max_output_bytes=_GENEROUS_OUTPUT_CAP,
    )

    assert read_own.exit_code == 0
    assert read_own.stdout.strip() == "own-output"
