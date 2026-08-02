"""Real proof that ``AIOS_GIT_*`` env vars
(:class:`~ai_os_kernel.git_integration.settings.GitIntegrationSettings`)
— this step's own new, real config source (``P03-S01-M24-T02``) —
genuinely populate a real
:class:`~ai_os_kernel.git_integration.service.GitIntegrationService`
instance through
:func:`~ai_os_kernel.git_integration.default_service.
build_git_integration_service_from_env`, and that the existing
safe-no-op-when-absent guarantee still holds when no
``AIOS_GIT_REMOTE_URL`` is configured — the same guarantee
``ai_os_pack_software_engineering.agents.git_push.GitPushAgentEntrypoint``
relies on for every current, unconfigured caller.

Fake sandbox/audit log — the identical shape
``tests/unit/kernel/git_integration/test_service.py`` already
establishes for the same reason: this file's own subject is env-var
resolution and config validation, not the real ``git`` subprocess
sequence that file already proves against a real backend.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from ai_os_kernel.git_integration.default_service import build_git_integration_service_from_env
from ai_os_kernel.git_integration.errors import (
    GitIntegrationConfigError,
    ProtectedBranchPushRefusedError,
)
from ai_os_kernel.git_integration.service import GitIntegrationService
from ai_os_kernel.sandbox.models import SandboxResult

_WORKSPACE = Path("/fake/workspace")
_ENV_VARS = (
    "AIOS_GIT_REMOTE_URL",
    "AIOS_GIT_AUTHOR_NAME",
    "AIOS_GIT_AUTHOR_EMAIL",
    "AIOS_GIT_PROTECTED_BRANCHES",
)


class _FakeAuditLogWriter:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


class _FakeSandbox:
    """Scripted by (command tuple) -> :class:`SandboxResult` — the
    identical fake ``test_service.py`` already establishes."""

    def __init__(self, scripted: dict[tuple[str, ...], SandboxResult]) -> None:
        self._scripted = scripted
        self.calls: list[dict[str, Any]] = []

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
        self.calls.append({"command": tuple(command), "env": env})
        key = tuple(command)
        if key not in self._scripted:
            raise AssertionError(f"unscripted command: {command!r}")
        return self._scripted[key]


def _ok(stdout: str = "") -> SandboxResult:
    return SandboxResult(
        exit_code=0,
        stdout=stdout,
        stderr="",
        timed_out=False,
        truncated=False,
        duration_seconds=0.01,
    )


@pytest.fixture(autouse=True)
def _clean_git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test in this file starts from a genuinely clean slate —
    the real environment this test process runs in must never leak an
    ambient ``AIOS_GIT_*`` value into what a test believes it is
    configuring from scratch."""
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_no_remote_url_configured_returns_none_the_existing_safe_no_op() -> None:
    """Every real environment today. Must keep resolving to ``None`` —
    the existing safe default ``GitPushAgentEntrypoint``'s own "no
    remote_url configured" no-op already relies on — not a new failure
    mode this step introduces."""
    result = build_git_integration_service_from_env(
        sandbox=_FakeSandbox({}),  # type: ignore[arg-type]
        audit_log=_FakeAuditLogWriter(),
    )

    assert result is None


async def test_a_fully_configured_remote_genuinely_populates_a_real_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real proof this step exists for: env vars flow all the way
    into a real, behaviorally-verifiable ``GitIntegrationService`` —
    author identity shows up in the exact ``git commit`` args a real
    caller would send, and the configured protected branch genuinely
    refuses a push — not merely a constructed object of the right type."""
    monkeypatch.setenv("AIOS_GIT_REMOTE_URL", "https://example.invalid/repo.git")
    monkeypatch.setenv("AIOS_GIT_AUTHOR_NAME", "AI_OS Delivery Pipeline")
    monkeypatch.setenv("AIOS_GIT_AUTHOR_EMAIL", "delivery-pipeline@ai-os.internal")
    monkeypatch.setenv("AIOS_GIT_PROTECTED_BRANCHES", " main , release ")

    sandbox = _FakeSandbox(
        {
            ("git", "rev-parse", "--is-inside-work-tree"): _ok("true"),
            ("git", "add", "-A"): _ok(),
            (
                "git",
                "-c",
                "user.name=AI_OS Delivery Pipeline",
                "-c",
                "user.email=delivery-pipeline@ai-os.internal",
                "commit",
                "-m",
                "real config source proof",
            ): _ok(),
            ("git", "rev-parse", "--abbrev-ref", "HEAD"): _ok("feature/x"),
            ("git", "rev-parse", "HEAD"): _ok("abc123"),
        }
    )
    audit_log = _FakeAuditLogWriter()

    service = build_git_integration_service_from_env(
        sandbox=sandbox,  # type: ignore[arg-type]
        audit_log=audit_log,
    )

    assert isinstance(service, GitIntegrationService)

    # Author identity genuinely came from AIOS_GIT_AUTHOR_NAME/_EMAIL —
    # the exact `-c user.name=`/`-c user.email=` args a real `git
    # commit` receives (test_service.py's own proof shape).
    commit_result = await service.commit(
        workspace=_WORKSPACE,
        message="real config source proof",
        actor_id="test",
        actor_type="test",
    )
    assert commit_result.commit_sha == "abc123"

    # Protected branches genuinely came from AIOS_GIT_PROTECTED_BRANCHES
    # — comma-parsed, whitespace-stripped ("main", not " main ") — and
    # the refusal is real: no push subprocess is even attempted.
    with pytest.raises(ProtectedBranchPushRefusedError):
        await service.push(
            workspace=_WORKSPACE,
            branch="main",
            remote_url="https://example.invalid/repo.git",
            actor_id="test",
            actor_type="test",
        )
    assert not any(call["command"][:2] == ("git", "push") for call in sandbox.calls)


@pytest.mark.parametrize(
    "missing_var",
    ["AIOS_GIT_AUTHOR_NAME", "AIOS_GIT_AUTHOR_EMAIL", "AIOS_GIT_PROTECTED_BRANCHES"],
)
def test_a_configured_remote_with_missing_author_or_branch_config_is_a_clear_error(
    monkeypatch: pytest.MonkeyPatch, missing_var: str
) -> None:
    """A configured remote is a real, disclosed intent to push for
    real — silently proceeding with an empty ``protected_branches`` (or
    a blank author identity written into every commit) would be the
    exact unsafe-default R-001 flagged, not a genuine improvement over
    the prior no-config-source gap."""
    monkeypatch.setenv("AIOS_GIT_REMOTE_URL", "https://example.invalid/repo.git")
    monkeypatch.setenv("AIOS_GIT_AUTHOR_NAME", "AI_OS Delivery Pipeline")
    monkeypatch.setenv("AIOS_GIT_AUTHOR_EMAIL", "delivery-pipeline@ai-os.internal")
    monkeypatch.setenv("AIOS_GIT_PROTECTED_BRANCHES", "main")
    monkeypatch.delenv(missing_var, raising=False)

    with pytest.raises(GitIntegrationConfigError, match=missing_var):
        build_git_integration_service_from_env(
            sandbox=_FakeSandbox({}),  # type: ignore[arg-type]
            audit_log=_FakeAuditLogWriter(),
        )


def test_a_configured_remote_with_blank_protected_branches_is_a_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``AIOS_GIT_PROTECTED_BRANCHES=" , "`` is present (not missing)
    but resolves to zero real branch names — the specific R-001 case: an
    *empty* protected-branches set is never a safe production default,
    even when the env var itself is technically set."""
    monkeypatch.setenv("AIOS_GIT_REMOTE_URL", "https://example.invalid/repo.git")
    monkeypatch.setenv("AIOS_GIT_AUTHOR_NAME", "AI_OS Delivery Pipeline")
    monkeypatch.setenv("AIOS_GIT_AUTHOR_EMAIL", "delivery-pipeline@ai-os.internal")
    monkeypatch.setenv("AIOS_GIT_PROTECTED_BRANCHES", " , ")

    with pytest.raises(GitIntegrationConfigError, match="AIOS_GIT_PROTECTED_BRANCHES"):
        build_git_integration_service_from_env(
            sandbox=_FakeSandbox({}),  # type: ignore[arg-type]
            audit_log=_FakeAuditLogWriter(),
        )
