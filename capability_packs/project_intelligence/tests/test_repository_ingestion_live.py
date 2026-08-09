"""The real, unmocked proof of the `repository.ingest` Tool — a genuine
`DockerSandbox` genuinely walking a real directory tree inside a real,
ephemeral container (ADR-0016 Tier 1), not a fake standing in for
either the sandbox or the walk itself.

Docker availability is checked the same "opt-in, clearly skipped, not
silently ignored" way every other live-Docker suite in this project
already does (see `tests/integration/sandbox/test_docker_sandbox_live.py`).
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import docker
import docker.errors
import pytest

from ai_os_kernel.sandbox.docker_executor import DockerSandbox
from ai_os_pack_project_intelligence.tools.repository_ingestion import (
    RepositoryIngestionToolEntrypoint,
)

_GENEROUS_TIMEOUT = 30.0
_GENEROUS_OUTPUT_CAP = 1_000_000


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
def real_repository(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "src" / "helper.py").write_text("def f(): pass\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Real Repo\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"\x00\x01")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_a_real_repository_is_genuinely_ingested_inside_a_real_container(
    docker_available: None, real_repository: Path
) -> None:
    tool = RepositoryIngestionToolEntrypoint()
    tool.sandbox = DockerSandbox()

    outputs = await tool.execute(
        {
            "workingDirectory": str(real_repository),
            "timeoutSeconds": _GENEROUS_TIMEOUT,
            "maxOutputBytes": _GENEROUS_OUTPUT_CAP,
        }
    )

    # __pycache__/.git are genuinely excluded, not merely documented as such.
    assert outputs["fileCount"] == 3
    assert outputs["languageCounts"] == {"python": 2, "markdown": 1}
    paths = {entry["path"] for entry in outputs["files"]}
    assert paths == {"src/main.py", "src/helper.py", "README.md"}
    modules = {entry["name"]: entry["fileCount"] for entry in outputs["modules"]}
    assert modules == {"src": 2, ".": 1}


@pytest.mark.asyncio
async def test_an_empty_directory_is_genuinely_ingested_as_zero_files(
    docker_available: None, tmp_path: Path
) -> None:
    tool = RepositoryIngestionToolEntrypoint()
    tool.sandbox = DockerSandbox()

    outputs = await tool.execute(
        {
            "workingDirectory": str(tmp_path),
            "timeoutSeconds": _GENEROUS_TIMEOUT,
            "maxOutputBytes": _GENEROUS_OUTPUT_CAP,
        }
    )

    assert outputs == {"fileCount": 0, "languageCounts": {}, "modules": [], "files": []}
