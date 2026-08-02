"""The Git Integration Service (``P03-S01-M24-T01``,
``git_integration.md``) — commit, branch, and push generated work under
real policy, with every mutating operation genuinely audited.

**Every real Git operation reuses existing, already-proven Kernel
infrastructure — nothing here is a parallel mechanism.**

- **Execution**: real ``git`` subprocesses run through the existing
  :class:`~ai_os_kernel.sandbox.executor.SandboxExecutor` Protocol
  (ADR-0016), not a bespoke ``asyncio.create_subprocess_exec`` call.
  This is exactly what that abstraction is for — a command, a working
  directory, a timeout, an output cap, an explicit environment — and it
  already gives this service two of git_integration.md §5's own rules
  for free: **no shell** (git_integration.md doesn't say this
  explicitly, but security_architecture.md §15 does, and
  ``SandboxExecutor`` already enforces it for every caller), and **real
  secret exclusion** (the child process never inherits ``os.environ`` —
  a credential is only ever present because *this service* explicitly
  passed it via ``env``, never ambiently).
- **Audit**: every mutating operation (commit, branch, push) records a
  real row through the existing, hash-chained
  :class:`~ai_os_kernel.observability.audit.AuditLogWriter`
  (``P01-S05-M04-T05``) — the same tamper-evident table
  :mod:`ai_os_kernel.secrets_manager.access_broker` already writes to,
  not a second, parallel audit mechanism. git_integration.md §7's
  required fields (operation type, repository identifier, branch/commit
  information, success/failure, actor, trace ID, timestamp) map
  directly onto ``AuditLogWriter.record``'s own existing parameters —
  no new audit schema was needed.
- **Credentials**: an optional push credential is a ``secret://``
  reference, resolved through the existing
  :class:`~ai_os_kernel.secrets_manager.access_broker.AccessBroker`
  (``P01-S02-M19-T04``) — itself already gated on the
  :data:`~ai_os_kernel.security_manager.permissions.SECRET_ACCESS`
  permission (``admin``-only) and already auditing the resolution
  itself, allowed or denied. This service never sees a raw secret value
  it did not itself just resolve, and never returns one to any caller.

**Credential delivery: ``GIT_ASKPASS``, never a URL, never a
sandbox.** git_integration.md §5: "Credentials live in this service and
never enter a sandbox. The service exposes the operation and withholds
the credential." A resolved :class:`~ai_os_kernel.secrets_manager.
value.SecretValue` is written to *neither* the repository's
``.git/config`` (a persistent, on-disk credential) *nor* the remote URL
(visible in ``git remote -v``, and via ``argv`` to any process
inspecting the running ``git`` command). Instead, a small, real,
per-call POSIX askpass script (a temp file, mode ``0o700``, deleted in
a ``finally`` block — never left behind) is pointed to by
``GIT_ASKPASS``; the resolved value itself travels only as one
environment variable on the ``git push`` subprocess's own environment,
consumed once and never logged, audited, or returned. This is the
identical, standard mechanism CI systems (GitHub Actions,
git-credential-manager) use for the same reason — this codebase's own
smallest, real version of it, not a new invention.

**Protected-branch push is structurally absent, not permission-gated —
git_integration.md §5.1's own explicit design.** :meth:`push` refuses a
push whose target branch is in :attr:`~ai_os_kernel.git_integration.
models.GitPushPolicy.protected_branches` *before starting any
subprocess at all* — this does not depend on who is asking (no
:class:`~ai_os_kernel.security_manager.models.SecurityContext` check
would change the outcome), matching the doc's own "not gated, not
configurable-on, not available with elevated permission." **This is how
this service respects R-001/ADR-0007's human-approval gate without ever
calling into it**: every real integration path onto a protected branch
must go through a pull request with human approval
(git_integration.md §5.1's own words) — a mechanism this ticket's own
Goal (commit/branch/push) does not build. Making the direct path
impossible here, rather than gated, is what keeps that guarantee real
even before a PR-creation mechanism exists to route through.

**Scoped deliberately smaller than the full framework document
(product-owner decision, options presented before building — the
identical discipline every step this session has used for a genuine
structural fork).** No clone/fetch/status/diff/pull (the ticket's own
Goal names only "commit, branch and push"); no Configuration-Manager-
sourced repository URLs or protected-branch policy (that layer has no
real field for either yet — both are explicit, required, caller-
supplied parameters instead, the same "no hardcoded values, explicit
and caller-supplied" shape ``RetryPolicy``/``GitPushPolicy``'s own
siblings already use); no PR-creation/merge mechanism (a real, separate,
later Task); no manifest-declared ``git:write`` permission check via the
monotonic-narrowing chain (that check belongs at Tool/Agent resolution
time, the same place ``catalog.agents``/``catalog.tools`` are already
checked — this service has no Tool wrapper yet, since the Software
Engineering Pack's own Git-writing Tools are separate, later work).
"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from ai_os_kernel.git_integration.errors import (
    GitOperationFailedError,
    ProtectedBranchPushRefusedError,
)
from ai_os_kernel.git_integration.models import (
    BranchResult,
    CommitResult,
    GitPushPolicy,
    PushResult,
)
from ai_os_kernel.observability.audit import AuditLogWriter, AuditOutcome
from ai_os_kernel.sandbox.executor import SandboxExecutor
from ai_os_kernel.secrets_manager.access_broker import AccessBroker
from ai_os_kernel.security_manager.models import SecurityContext

_ASKPASS_ENV_VAR = "AIOS_GIT_ASKPASS_SECRET"
_ASKPASS_SCRIPT = f"#!/bin/sh\nprintf '%s' \"${_ASKPASS_ENV_VAR}\"\n"

_DEFAULT_TIMEOUT_SECONDS = 30.0
_DEFAULT_MAX_OUTPUT_BYTES = 1_000_000


class GitIntegrationService:
    """Real, audited Git operations against an existing local
    ``workspace`` — see this module's own docstring for the full
    design and disclosed scope."""

    def __init__(
        self,
        *,
        sandbox: SandboxExecutor,
        audit_log: AuditLogWriter,
        push_policy: GitPushPolicy,
        author_name: str,
        author_email: str,
        secret_broker: AccessBroker | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        if not author_name.strip() or not author_email.strip():
            raise ValueError("author_name and author_email must both be real, non-empty values")
        self._sandbox = sandbox
        self._audit_log = audit_log
        self._push_policy = push_policy
        self._author_name = author_name
        self._author_email = author_email
        self._secret_broker = secret_broker
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes

    async def _run_git(
        self,
        *,
        workspace: Path,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> str:
        result = await self._sandbox.execute(
            command=["git", *args],
            working_directory=workspace,
            timeout_seconds=self._timeout_seconds,
            max_output_bytes=self._max_output_bytes,
            env=env,
        )
        if result.timed_out or result.exit_code != 0:
            raise GitOperationFailedError(
                f"git {' '.join(args)!r} failed in {workspace!r} "
                f"(exit_code={result.exit_code}, timed_out={result.timed_out}): "
                f"{result.stderr.strip()}"
            )
        return result.stdout.strip()

    async def _ensure_repo(self, workspace: Path) -> None:
        probe = await self._sandbox.execute(
            command=["git", "rev-parse", "--is-inside-work-tree"],
            working_directory=workspace,
            timeout_seconds=self._timeout_seconds,
            max_output_bytes=self._max_output_bytes,
        )
        if probe.exit_code == 0 and probe.stdout.strip() == "true":
            return
        await self._run_git(workspace=workspace, args=["init"])

    async def commit(
        self,
        *,
        workspace: Path,
        message: str,
        actor_id: str,
        actor_type: str,
        trace_id: str | None = None,
    ) -> CommitResult:
        """Stages every change in ``workspace`` and commits it under
        this service's own configured author identity — passed via
        per-call ``-c user.name=``/``-c user.email=`` flags, never
        written to the repository's own ``.git/config``, so this
        service never mutates shared, persistent repo state to do its
        job."""
        try:
            await self._ensure_repo(workspace)
            await self._run_git(workspace=workspace, args=["add", "-A"])
            await self._run_git(
                workspace=workspace,
                args=[
                    "-c",
                    f"user.name={self._author_name}",
                    "-c",
                    f"user.email={self._author_email}",
                    "commit",
                    "-m",
                    message,
                ],
            )
            branch = await self._run_git(
                workspace=workspace, args=["rev-parse", "--abbrev-ref", "HEAD"]
            )
            commit_sha = await self._run_git(workspace=workspace, args=["rev-parse", "HEAD"])
        except GitOperationFailedError as exc:
            await self._audit_log.record(
                event_type="git.commit.failed",
                principal_id=actor_id,
                principal_type=actor_type,
                outcome=AuditOutcome.FAILURE,
                detail={"workspace": str(workspace), "error": str(exc)},
                resource_type="git_repository",
                resource_id=str(workspace),
                trace_id=trace_id,
            )
            raise

        await self._audit_log.record(
            event_type="git.commit.succeeded",
            principal_id=actor_id,
            principal_type=actor_type,
            outcome=AuditOutcome.SUCCESS,
            detail={
                "workspace": str(workspace),
                "branch": branch,
                "commit_sha": commit_sha,
                "message": message,
            },
            resource_type="git_repository",
            resource_id=str(workspace),
            trace_id=trace_id,
        )
        return CommitResult(commit_sha=commit_sha, branch=branch)

    async def create_branch(
        self,
        *,
        workspace: Path,
        branch_name: str,
        actor_id: str,
        actor_type: str,
        trace_id: str | None = None,
    ) -> BranchResult:
        try:
            await self._ensure_repo(workspace)
            await self._run_git(workspace=workspace, args=["checkout", "-b", branch_name])
        except GitOperationFailedError as exc:
            await self._audit_log.record(
                event_type="git.branch.create.failed",
                principal_id=actor_id,
                principal_type=actor_type,
                outcome=AuditOutcome.FAILURE,
                detail={"workspace": str(workspace), "branch": branch_name, "error": str(exc)},
                resource_type="git_repository",
                resource_id=str(workspace),
                trace_id=trace_id,
            )
            raise

        await self._audit_log.record(
            event_type="git.branch.create.succeeded",
            principal_id=actor_id,
            principal_type=actor_type,
            outcome=AuditOutcome.SUCCESS,
            detail={"workspace": str(workspace), "branch": branch_name},
            resource_type="git_repository",
            resource_id=str(workspace),
            trace_id=trace_id,
        )
        return BranchResult(branch=branch_name, created=True)

    async def push(
        self,
        *,
        workspace: Path,
        branch: str,
        remote_url: str,
        remote_name: str = "origin",
        credential_reference: str | None = None,
        security_context: SecurityContext | None = None,
        actor_id: str,
        actor_type: str,
        trace_id: str | None = None,
    ) -> PushResult:
        """Pushes ``branch`` to ``remote_url`` — refusing outright,
        before any subprocess or credential resolution, if ``branch``
        is a protected branch (see this module's own docstring)."""
        if branch in self._push_policy.protected_branches:
            await self._audit_log.record(
                event_type="git.push.denied",
                principal_id=actor_id,
                principal_type=actor_type,
                outcome=AuditOutcome.DENIED,
                detail={
                    "workspace": str(workspace),
                    "branch": branch,
                    "remote": remote_name,
                    "reason": "protected_branch",
                },
                resource_type="git_repository",
                resource_id=str(workspace),
                trace_id=trace_id,
            )
            raise ProtectedBranchPushRefusedError(
                f"branch {branch!r} is protected — direct push is absent from this "
                "service's own tool surface (git_integration.md §5.1)"
            )
        secret_broker = self._secret_broker
        if credential_reference is not None and (secret_broker is None or security_context is None):
            raise ValueError(
                "a credential_reference was given but no secret_broker/security_context "
                "is configured to resolve it"
            )

        askpass_path: Path | None = None
        try:
            await self._ensure_repo(workspace)
            await self._configure_remote(
                workspace=workspace, remote_name=remote_name, remote_url=remote_url
            )

            push_env: dict[str, str] = {}
            if (
                credential_reference is not None
                and secret_broker is not None
                and security_context is not None
            ):
                secret = await secret_broker.resolve(credential_reference, context=security_context)
                askpass_path = _write_askpass_script()
                push_env = {
                    "GIT_ASKPASS": str(askpass_path),
                    "GIT_TERMINAL_PROMPT": "0",
                    _ASKPASS_ENV_VAR: secret.reveal(),
                }

            await self._run_git(
                workspace=workspace,
                args=["push", remote_name, branch],
                env=push_env or None,
            )
        except GitOperationFailedError as exc:
            await self._audit_log.record(
                event_type="git.push.failed",
                principal_id=actor_id,
                principal_type=actor_type,
                outcome=AuditOutcome.FAILURE,
                detail={
                    "workspace": str(workspace),
                    "branch": branch,
                    "remote": remote_name,
                    "remote_url": remote_url,
                    "error": str(exc),
                },
                resource_type="git_repository",
                resource_id=str(workspace),
                trace_id=trace_id,
            )
            raise
        finally:
            if askpass_path is not None:
                askpass_path.unlink(missing_ok=True)

        await self._audit_log.record(
            event_type="git.push.succeeded",
            principal_id=actor_id,
            principal_type=actor_type,
            outcome=AuditOutcome.SUCCESS,
            detail={
                "workspace": str(workspace),
                "branch": branch,
                "remote": remote_name,
                "remote_url": remote_url,
            },
            resource_type="git_repository",
            resource_id=str(workspace),
            trace_id=trace_id,
        )
        return PushResult(remote=remote_name, branch=branch)

    async def _configure_remote(
        self, *, workspace: Path, remote_name: str, remote_url: str
    ) -> None:
        existing = await self._sandbox.execute(
            command=["git", "remote", "get-url", remote_name],
            working_directory=workspace,
            timeout_seconds=self._timeout_seconds,
            max_output_bytes=self._max_output_bytes,
        )
        if existing.exit_code == 0 and existing.stdout.strip() == remote_url:
            return
        if existing.exit_code == 0:
            await self._run_git(
                workspace=workspace, args=["remote", "set-url", remote_name, remote_url]
            )
        else:
            await self._run_git(
                workspace=workspace, args=["remote", "add", remote_name, remote_url]
            )


def _write_askpass_script() -> Path:
    """A real, per-call temp file — mode ``0o700`` (owner-only,
    executable) — deleted by the caller in a ``finally`` block. Content
    is fixed and contains no secret; the secret travels only via
    :data:`_ASKPASS_ENV_VAR` on the subprocess's own environment (see
    this module's own docstring)."""
    fd, raw_path = tempfile.mkstemp(prefix="aios-git-askpass-", suffix=".sh")
    path = Path(raw_path)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(_ASKPASS_SCRIPT)
        path.chmod(stat.S_IRWXU)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path
