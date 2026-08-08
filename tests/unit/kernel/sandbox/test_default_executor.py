"""Unit tests for :mod:`ai_os_kernel.sandbox.default_executor` — the
config-driven default-backend selection this step introduces. No
Docker/Postgres needed: constructing either backend does zero I/O, so
these tests only need to prove *which class* gets constructed and what
each one's `python_command` resolves to, never that a daemon exists.
"""

from __future__ import annotations

import sys

import pytest

from ai_os_kernel.sandbox.default_executor import (
    ENV_VAR,
    RUNTIME_ENV_VAR,
    UnknownSandboxBackendError,
    build_default_sandbox_executor,
    default_python_command,
)
from ai_os_kernel.sandbox.docker_executor import DockerSandbox
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox


def test_default_backend_is_docker_when_the_env_var_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)

    sandbox = build_default_sandbox_executor()

    assert isinstance(sandbox, DockerSandbox)


def test_backend_is_docker_when_the_env_var_is_explicitly_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_VAR, "docker")

    assert isinstance(build_default_sandbox_executor(), DockerSandbox)


def test_backend_is_local_when_the_env_var_is_explicitly_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_VAR, "local")

    assert isinstance(build_default_sandbox_executor(), LocalSubprocessSandbox)


def test_backend_selection_is_case_and_whitespace_insensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_VAR, "  LOCAL  ")

    assert isinstance(build_default_sandbox_executor(), LocalSubprocessSandbox)


def test_an_unrecognized_backend_name_is_rejected_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, "podman")

    with pytest.raises(UnknownSandboxBackendError, match="podman"):
        build_default_sandbox_executor()


def test_default_python_command_matches_docker_backend_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)

    assert default_python_command() == ("python3",)


def test_default_python_command_matches_local_backend_when_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_VAR, "local")

    assert default_python_command() == (sys.executable,)


def test_docker_sandbox_has_no_runtime_override_when_the_env_var_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.delenv(RUNTIME_ENV_VAR, raising=False)

    sandbox = build_default_sandbox_executor()

    assert isinstance(sandbox, DockerSandbox)
    assert sandbox.runtime is None


def test_docker_sandbox_carries_the_configured_runtime_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.setenv(RUNTIME_ENV_VAR, "runsc")

    sandbox = build_default_sandbox_executor()

    assert isinstance(sandbox, DockerSandbox)
    assert sandbox.runtime == "runsc"


def test_a_blank_runtime_override_is_treated_as_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.setenv(RUNTIME_ENV_VAR, "   ")

    sandbox = build_default_sandbox_executor()

    assert isinstance(sandbox, DockerSandbox)
    assert sandbox.runtime is None


def test_the_runtime_override_is_ignored_entirely_for_the_local_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`AIOS_SANDBOX_RUNTIME` is a Docker-only concept —
    `LocalSubprocessSandbox` has no runtime parameter to carry it, and
    this must not raise just because the variable happens to be set."""
    monkeypatch.setenv(ENV_VAR, "local")
    monkeypatch.setenv(RUNTIME_ENV_VAR, "runsc")

    assert isinstance(build_default_sandbox_executor(), LocalSubprocessSandbox)
