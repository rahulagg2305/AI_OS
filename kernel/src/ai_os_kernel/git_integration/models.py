"""Real shapes for the Git Integration Service — see
:mod:`ai_os_kernel.git_integration.service`'s own module docstring for
the full design."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class GitPushPolicy(BaseModel):
    """Which branch names a push may never target — git_integration.md
    §5.1. **No default** — Configuration Manager has no real field for
    this yet (it is still a 35% minimal slice with no pack-defaults/
    runtime-overrides layer), so a caller must supply this explicitly
    rather than this module silently guessing a name like ``"main"``
    (a real repository may use ``"master"``, ``"trunk"``, or several
    protected release branches at once) — the same "no hardcoded
    values, explicit and caller-supplied" shape already established for
    ``RetryPolicy``/``GitPushPolicy``'s own sibling contracts elsewhere
    in this codebase.
    """

    model_config = ConfigDict(frozen=True)

    protected_branches: frozenset[str]


class CommitResult(BaseModel):
    """The real outcome of :meth:`~ai_os_kernel.git_integration.service.
    GitIntegrationService.commit`."""

    model_config = ConfigDict(frozen=True)

    commit_sha: str
    branch: str


class BranchResult(BaseModel):
    """The real outcome of :meth:`~ai_os_kernel.git_integration.service.
    GitIntegrationService.create_branch`."""

    model_config = ConfigDict(frozen=True)

    branch: str
    created: bool


class PushResult(BaseModel):
    """The real outcome of :meth:`~ai_os_kernel.git_integration.service.
    GitIntegrationService.push`."""

    model_config = ConfigDict(frozen=True)

    remote: str
    branch: str
