"""The real, unmocked proof of the `dependency.graph` Tool — a genuine
`DockerSandbox` genuinely reading real files and genuinely running
`ast.parse()` inside a real, ephemeral container (ADR-0016 Tier 1),
against a real, hand-built Python package with real relative and
absolute imports.

Docker availability is checked the same "opt-in, clearly skipped, not
silently ignored" way every other live-Docker suite in this project
already does.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import docker
import docker.errors
import pytest

from ai_os_kernel.sandbox.docker_executor import DockerSandbox
from ai_os_pack_project_intelligence.tools.dependency_graph import (
    DependencyGraphToolEntrypoint,
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
def real_python_package(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "sub").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "sub" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "util.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "pkg" / "sub" / "helper.py").write_text("def f(): pass\n", encoding="utf-8")
    (tmp_path / "pkg" / "main.py").write_text(
        "import os\nimport pkg.sub.helper\nfrom . import util\nfrom .sub import helper\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.asyncio
async def test_a_real_python_packages_imports_are_genuinely_resolved(
    docker_available: None, real_python_package: Path
) -> None:
    tool = DependencyGraphToolEntrypoint()
    tool.sandbox = DockerSandbox()

    outputs = await tool.execute(
        {
            "workingDirectory": str(real_python_package),
            "pythonFiles": [
                "pkg/__init__.py",
                "pkg/sub/__init__.py",
                "pkg/util.py",
                "pkg/sub/helper.py",
                "pkg/main.py",
            ],
            "timeoutSeconds": _GENEROUS_TIMEOUT,
            "maxOutputBytes": _GENEROUS_OUTPUT_CAP,
        }
    )

    assert outputs["parseErrors"] == []
    edges = {(edge["from"], edge["to"]) for edge in outputs["edges"]}
    assert ("pkg/main.py", "pkg/sub/helper.py") in edges
    assert ("pkg/main.py", "pkg/util.py") in edges
    # os is a real stdlib import -- genuinely unresolved, never fabricated.
    unresolved_names = {entry["importedName"] for entry in outputs["unresolvedImports"]}
    assert "os" in unresolved_names


@pytest.mark.asyncio
async def test_a_real_syntax_error_is_reported_not_fatal(
    docker_available: None, tmp_path: Path
) -> None:
    (tmp_path / "broken.py").write_text("def f(:\n", encoding="utf-8")
    (tmp_path / "fine.py").write_text("x = 1\n", encoding="utf-8")
    tool = DependencyGraphToolEntrypoint()
    tool.sandbox = DockerSandbox()

    outputs = await tool.execute(
        {
            "workingDirectory": str(tmp_path),
            "pythonFiles": ["broken.py", "fine.py"],
            "timeoutSeconds": _GENEROUS_TIMEOUT,
            "maxOutputBytes": _GENEROUS_OUTPUT_CAP,
        }
    )

    assert len(outputs["parseErrors"]) == 1
    assert outputs["parseErrors"][0]["path"] == "broken.py"
    assert "SyntaxError" in outputs["parseErrors"][0]["error"]
    # The one bad file did not prevent the rest of the graph.
    assert {node["path"] for node in outputs["nodes"]} == {"broken.py", "fine.py"}
