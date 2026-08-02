"""Builds the real, production :class:`~ai_os_kernel.git_integration.
service.GitIntegrationService` from ``AIOS_GIT_*`` env vars
(:class:`~ai_os_kernel.git_integration.settings.GitIntegrationSettings`)
— the real config source ``git_integration.md``/``git_push.py`` both
name as deferred, later work. Closes that gap.

**Mirrors :mod:`ai_os_kernel.sandbox.default_executor`'s own "one env
var read once at construction, absent means the existing safe default"
shape** — absent ``AIOS_GIT_REMOTE_URL`` returns ``None`` here too,
which is what lets every current caller keep degrading to the existing,
proven no-op (:class:`~ai_os_pack_software_engineering.agents.git_push.
GitPushAgentEntrypoint` already returns ``{"pushed": False, ...,
"reason": "no remote_url configured"}`` whenever its own ``remote_url``
is ``None``) rather than this module inventing a second one.

**Present but incomplete is a configuration error, not a guess.** A
configured remote with no real author identity, or no real
``protected_branches``, is refused loudly
(:class:`~ai_os_kernel.git_integration.errors.GitIntegrationConfigError`)
— the same "a granted permission this builder cannot actually back is a
configuration error, not a silent no-op" principle
:func:`~ai_os_kernel.sdk_adapters.pack_context.build_pack_context`
already established, applied here to the specific, disclosed R-001
finding that an *empty* ``protected_branches`` set is never a safe
production default.
"""

from __future__ import annotations

from ai_os_kernel.git_integration.errors import GitIntegrationConfigError
from ai_os_kernel.git_integration.models import GitPushPolicy
from ai_os_kernel.git_integration.service import GitIntegrationService
from ai_os_kernel.git_integration.settings import GitIntegrationSettings
from ai_os_kernel.observability.audit import AuditLogWriter
from ai_os_kernel.sandbox.executor import SandboxExecutor
from ai_os_kernel.secrets_manager.access_broker import AccessBroker

_REMOTE_URL_VAR = "AIOS_GIT_REMOTE_URL"
_AUTHOR_NAME_VAR = "AIOS_GIT_AUTHOR_NAME"
_AUTHOR_EMAIL_VAR = "AIOS_GIT_AUTHOR_EMAIL"
_PROTECTED_BRANCHES_VAR = "AIOS_GIT_PROTECTED_BRANCHES"


def build_git_integration_service_from_env(
    *,
    sandbox: SandboxExecutor,
    audit_log: AuditLogWriter,
    secret_broker: AccessBroker | None = None,
) -> GitIntegrationService | None:
    """Returns a real, fully-configured ``GitIntegrationService`` when
    ``AIOS_GIT_REMOTE_URL`` is set, or ``None`` when it is absent — the
    genuine, current default in every environment today, and the signal
    every real caller already uses to keep its own existing no-op
    behaviour (see this module's own docstring).

    Raises :class:`GitIntegrationConfigError` if ``AIOS_GIT_REMOTE_URL``
    is set but ``AIOS_GIT_AUTHOR_NAME``/``AIOS_GIT_AUTHOR_EMAIL``/
    ``AIOS_GIT_PROTECTED_BRANCHES`` are not all real, non-empty values.
    """
    settings = GitIntegrationSettings()
    if settings.remote_url is None:
        return None

    author_name = settings.author_name
    author_email = settings.author_email
    protected_branches_raw = settings.protected_branches

    missing = [
        name
        for name, value in (
            (_AUTHOR_NAME_VAR, author_name),
            (_AUTHOR_EMAIL_VAR, author_email),
            (_PROTECTED_BRANCHES_VAR, protected_branches_raw),
        )
        if not value or not value.strip()
    ]
    if missing or author_name is None or author_email is None or protected_branches_raw is None:
        # The `or _ is None` disjuncts are unreachable in practice (an
        # empty/whitespace-only string is already `missing`) — they
        # exist so mypy --strict can narrow all three from `str | None`
        # to `str` below, without a bare `assert` (coding_standards.md:
        # asserts are stripped under `-O` and ruff S101 flags them
        # outside tests).
        raise GitIntegrationConfigError(
            f"{_REMOTE_URL_VAR} is configured but {missing} is/are not — a real remote "
            "requires a real author identity and an explicit, non-empty protected-branches "
            "list, never a silently-guessed default (R-001)"
        )

    protected_branches = frozenset(
        branch.strip() for branch in protected_branches_raw.split(",") if branch.strip()
    )
    if not protected_branches:
        raise GitIntegrationConfigError(
            f"{_PROTECTED_BRANCHES_VAR} resolved to no real branch names — an empty "
            "protected-branches set is never a safe production default (R-001)"
        )

    return GitIntegrationService(
        sandbox=sandbox,
        audit_log=audit_log,
        push_policy=GitPushPolicy(protected_branches=protected_branches),
        author_name=author_name,
        author_email=author_email,
        secret_broker=secret_broker,
    )


__all__ = ["build_git_integration_service_from_env"]
