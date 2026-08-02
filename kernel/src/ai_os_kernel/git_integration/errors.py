"""Errors raised by the Git Integration Service
(``git_integration.md``'s own design)."""

from __future__ import annotations


class GitIntegrationError(Exception):
    """Base class for every Git Integration Service error."""


class GitOperationFailedError(GitIntegrationError):
    """A real ``git`` subprocess exited non-zero, or timed out. Carries
    the operation's own real stderr/exit code in its message — never a
    credential (see :mod:`ai_os_kernel.git_integration.service`'s own
    docstring for why one can never reach this far in the first
    place)."""


class ProtectedBranchPushRefusedError(GitIntegrationError):
    """A push targeted a branch named in :attr:`~ai_os_kernel.
    git_integration.models.GitPushPolicy.protected_branches`.

    Raised **before any subprocess is started** — git_integration.md
    §5.1: direct push to a protected branch is "absent from the tool
    surface — not gated, not configurable-on, not available with
    elevated permission." This is not a permission check a caller could
    pass with a different role; it is a structural refusal that does
    not depend on who is asking.
    """
