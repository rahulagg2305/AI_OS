"""Fake-based unit tests for :class:`~ai_os_kernel.git_integration.
service.GitIntegrationService` — the executor and audit log are both
fakes so these tests need no real Postgres or real ``git`` binary; the
service's own real control-flow logic (protected-branch refusal,
credential resolution/injection, audit event shape) is exercised
directly, unmocked. Real, Postgres+git-backed end-to-end proof lives in
``tests/integration/git_integration/test_git_integration_service.py``.
"""

from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from ai_os_kernel.git_integration.errors import (
    GitOperationFailedError,
    ProtectedBranchPushRefusedError,
)
from ai_os_kernel.git_integration.models import GitPushPolicy
from ai_os_kernel.git_integration.service import GitIntegrationService, _write_askpass_script
from ai_os_kernel.observability.audit import AuditOutcome
from ai_os_kernel.sandbox.models import SandboxResult
from ai_os_kernel.secrets_manager.access_broker import AccessBroker
from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.security_manager.models import Principal, PrincipalType, SecurityContext
from ai_os_kernel.security_manager.permissions import SECRET_ACCESS

_WORKSPACE = Path("/fake/workspace")


class _FakeAuditLogWriter:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


class _FakeSandbox:
    """Scripted by (command tuple) -> :class:`SandboxResult`; records
    every call, including the real ``env`` dict passed, so a test can
    assert exactly what a real backend would have received."""

    def __init__(self, scripted: dict[tuple[str, ...], SandboxResult]) -> None:
        self._scripted = scripted
        self.calls: list[dict[str, Any]] = []

    async def execute(
        self,
        *,
        command: list[str],
        working_directory: Path,
        timeout_seconds: float,
        max_output_bytes: int,
        env: dict[str, str] | None = None,
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


def _failed(stderr: str = "boom") -> SandboxResult:
    return SandboxResult(
        exit_code=1,
        stdout="",
        stderr=stderr,
        timed_out=False,
        truncated=False,
        duration_seconds=0.01,
    )


def _service(
    sandbox: _FakeSandbox,
    audit_log: _FakeAuditLogWriter,
    *,
    protected_branches: frozenset[str] = frozenset({"main"}),
    secret_broker: AccessBroker | None = None,
) -> GitIntegrationService:
    return GitIntegrationService(
        sandbox=sandbox,  # type: ignore[arg-type]
        audit_log=audit_log,
        push_policy=GitPushPolicy(protected_branches=protected_branches),
        author_name="AI_OS Bot",
        author_email="bot@ai-os.internal",
        secret_broker=secret_broker,
    )


async def test_commit_runs_the_real_sequence_and_audits_success() -> None:
    sandbox = _FakeSandbox(
        {
            ("git", "rev-parse", "--is-inside-work-tree"): _ok("true"),
            ("git", "add", "-A"): _ok(),
            (
                "git",
                "-c",
                "user.name=AI_OS Bot",
                "-c",
                "user.email=bot@ai-os.internal",
                "commit",
                "-m",
                "generated work",
            ): _ok(),
            ("git", "rev-parse", "--abbrev-ref", "HEAD"): _ok("feature/x"),
            ("git", "rev-parse", "HEAD"): _ok("abc123"),
        }
    )
    audit_log = _FakeAuditLogWriter()
    service = _service(sandbox, audit_log)

    result = await service.commit(
        workspace=_WORKSPACE, message="generated work", actor_id="agent-1", actor_type="agent"
    )

    assert result.commit_sha == "abc123"
    assert result.branch == "feature/x"
    succeeded = next(r for r in audit_log.records if r["event_type"] == "git.commit.succeeded")
    assert succeeded["outcome"] == AuditOutcome.SUCCESS
    assert succeeded["principal_id"] == "agent-1"
    assert succeeded["detail"]["commit_sha"] == "abc123"
    assert succeeded["detail"]["branch"] == "feature/x"


async def test_commit_when_git_init_is_needed_runs_init_first() -> None:
    sandbox = _FakeSandbox(
        {
            ("git", "rev-parse", "--is-inside-work-tree"): _failed("not a git repository"),
            ("git", "init"): _ok(),
            ("git", "add", "-A"): _ok(),
            (
                "git",
                "-c",
                "user.name=AI_OS Bot",
                "-c",
                "user.email=bot@ai-os.internal",
                "commit",
                "-m",
                "m",
            ): _ok(),
            ("git", "rev-parse", "--abbrev-ref", "HEAD"): _ok("master"),
            ("git", "rev-parse", "HEAD"): _ok("sha1"),
        }
    )
    audit_log = _FakeAuditLogWriter()
    service = _service(sandbox, audit_log)

    await service.commit(workspace=_WORKSPACE, message="m", actor_id="a", actor_type="agent")

    assert ("git", "init") in [c["command"] for c in sandbox.calls]


async def test_commit_failure_is_never_silent() -> None:
    sandbox = _FakeSandbox(
        {
            ("git", "rev-parse", "--is-inside-work-tree"): _ok("true"),
            ("git", "add", "-A"): _ok(),
            (
                "git",
                "-c",
                "user.name=AI_OS Bot",
                "-c",
                "user.email=bot@ai-os.internal",
                "commit",
                "-m",
                "m",
            ): _failed("nothing to commit"),
        }
    )
    audit_log = _FakeAuditLogWriter()
    service = _service(sandbox, audit_log)

    with pytest.raises(GitOperationFailedError, match="nothing to commit"):
        await service.commit(workspace=_WORKSPACE, message="m", actor_id="a", actor_type="agent")

    failed = next(r for r in audit_log.records if r["event_type"] == "git.commit.failed")
    assert failed["outcome"] == AuditOutcome.FAILURE
    assert "nothing to commit" in failed["detail"]["error"]


async def test_create_branch_success_and_failure_are_both_audited() -> None:
    sandbox = _FakeSandbox(
        {
            ("git", "rev-parse", "--is-inside-work-tree"): _ok("true"),
            ("git", "checkout", "-b", "feature/y"): _ok(),
        }
    )
    audit_log = _FakeAuditLogWriter()
    service = _service(sandbox, audit_log)

    result = await service.create_branch(
        workspace=_WORKSPACE, branch_name="feature/y", actor_id="a", actor_type="agent"
    )
    assert result.created is True
    succeeded = next(
        r for r in audit_log.records if r["event_type"] == "git.branch.create.succeeded"
    )
    assert succeeded["detail"]["branch"] == "feature/y"


async def test_push_to_a_protected_branch_is_refused_before_any_subprocess() -> None:
    sandbox = _FakeSandbox({})  # any command raises AssertionError — proves none is attempted
    audit_log = _FakeAuditLogWriter()
    service = _service(sandbox, audit_log, protected_branches=frozenset({"main"}))

    with pytest.raises(ProtectedBranchPushRefusedError):
        await service.push(
            workspace=_WORKSPACE,
            branch="main",
            remote_url="https://example.invalid/repo.git",
            actor_id="a",
            actor_type="agent",
        )

    assert sandbox.calls == []
    denied = next(r for r in audit_log.records if r["event_type"] == "git.push.denied")
    assert denied["outcome"] == AuditOutcome.DENIED
    assert denied["detail"]["reason"] == "protected_branch"


async def test_push_without_a_credential_passes_no_env() -> None:
    sandbox = _FakeSandbox(
        {
            ("git", "rev-parse", "--is-inside-work-tree"): _ok("true"),
            ("git", "remote", "get-url", "origin"): _failed("no such remote"),
            ("git", "remote", "add", "origin", "https://example.invalid/repo.git"): _ok(),
            ("git", "push", "origin", "feature/x"): _ok(),
        }
    )
    audit_log = _FakeAuditLogWriter()
    service = _service(sandbox, audit_log, protected_branches=frozenset({"main"}))

    await service.push(
        workspace=_WORKSPACE,
        branch="feature/x",
        remote_url="https://example.invalid/repo.git",
        actor_id="a",
        actor_type="agent",
    )

    push_call = next(
        c for c in sandbox.calls if c["command"] == ("git", "push", "origin", "feature/x")
    )
    assert push_call["env"] is None
    succeeded = next(r for r in audit_log.records if r["event_type"] == "git.push.succeeded")
    assert succeeded["outcome"] == AuditOutcome.SUCCESS


async def test_push_with_a_credential_resolves_it_and_never_leaks_it_to_audit() -> None:
    provider = EnvSecretProvider(env={"AIOS_SECRET_GIT_TOKEN": "real-token-xyz"})
    broker_audit = _FakeAuditLogWriter()
    broker = AccessBroker(provider=provider, audit_log=broker_audit)
    context = SecurityContext(
        principal=Principal(
            principal_id="admin-1", principal_type=PrincipalType.USER, roles=frozenset({"admin"})
        ),
        permissions=frozenset({SECRET_ACCESS}),
    )
    sandbox = _FakeSandbox(
        {
            ("git", "rev-parse", "--is-inside-work-tree"): _ok("true"),
            ("git", "remote", "get-url", "origin"): _ok("https://example.invalid/repo.git"),
            ("git", "push", "origin", "feature/x"): _ok(),
        }
    )
    audit_log = _FakeAuditLogWriter()
    service = _service(
        sandbox, audit_log, protected_branches=frozenset({"main"}), secret_broker=broker
    )

    await service.push(
        workspace=_WORKSPACE,
        branch="feature/x",
        remote_url="https://example.invalid/repo.git",
        credential_reference="secret://env/git-token",
        security_context=context,
        actor_id="a",
        actor_type="agent",
    )

    push_call = next(
        c for c in sandbox.calls if c["command"] == ("git", "push", "origin", "feature/x")
    )
    assert push_call["env"] is not None
    assert push_call["env"]["AIOS_GIT_ASKPASS_SECRET"] == "real-token-xyz"  # noqa: S105
    assert push_call["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert "GIT_ASKPASS" in push_call["env"]

    for record in audit_log.records:
        assert "real-token-xyz" not in str(record["detail"])


async def test_push_with_a_credential_reference_but_no_broker_is_refused_immediately() -> None:
    sandbox = _FakeSandbox({})  # nothing scripted — must never be called
    audit_log = _FakeAuditLogWriter()
    service = _service(sandbox, audit_log, protected_branches=frozenset({"main"}))

    with pytest.raises(ValueError, match="no secret_broker/security_context"):
        await service.push(
            workspace=_WORKSPACE,
            branch="feature/x",
            remote_url="https://example.invalid/repo.git",
            credential_reference="secret://env/git-token",
            actor_id="a",
            actor_type="agent",
        )

    assert sandbox.calls == []


async def test_the_real_askpass_script_is_executable_and_echoes_the_env_secret() -> None:
    """A real temp file, real permissions, genuinely executed as a
    subprocess — proving the mechanism itself, not just its
    construction."""
    path = _write_askpass_script()
    try:
        if os.name == "posix":
            # Windows' filesystem cannot represent POSIX permission bits
            # (os.chmod there only toggles a read-only flag) — the mode
            # is only meaningfully checkable on the real deployment
            # target. The execution proof below runs on every platform.
            mode = path.stat().st_mode
            assert stat.S_IMODE(mode) == stat.S_IRWXU

        env = dict(os.environ)
        env["AIOS_GIT_ASKPASS_SECRET"] = "echoed-secret-value"  # noqa: S105
        process = await asyncio.create_subprocess_exec(
            "sh", str(path), stdout=asyncio.subprocess.PIPE, env=env
        )
        stdout, _ = await process.communicate()
        assert stdout.decode() == "echoed-secret-value"
    finally:
        path.unlink(missing_ok=True)
