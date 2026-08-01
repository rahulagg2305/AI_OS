"""Prompt-assembly secret leak scan (``P01-S02-M19-T06``, closing the
module's own long-named gap). docs/09_security/secrets_management.md
§3/§6: "Never send secrets to LLMs unless absolutely unavoidable and
explicitly approved" / "A secret is never sent to a model. Prompt
assembly rejects content matching a resolved secret value, as defence
in depth."

**"Content matching a resolved secret value"** — an exact, literal
match against secrets actually resolved for *this* render, not a
regex-shaped heuristic guess at what a credential looks like. The
caller supplies the :class:`~ai_os_kernel.secrets_manager.value.
SecretValue`\\ s it resolved while building the prompt's variables;
this scan checks whether any of their real values ended up verbatim in
the rendered text before that text is allowed to reach an LLM Gateway
call — the defence-in-depth backstop for a template that should never
have interpolated a secret into prompt content in the first place, but
might have by mistake.

**Input is the real ``PromptRenderResponse``**
(:mod:`ai_os_kernel.prompt_engine.models`, ``P02-S03-M07-T01``) — the
actual "assembled prompt" type this ticket depends on that module for,
not a bare string invented here. ``prompt_id`` + ``version`` become the
audit row's ``resource_id``, exactly how a caller already identifies
which rendered prompt this was.

**Audits only the blocked case.** Unlike
:class:`~ai_os_kernel.secrets_manager.access_broker.AccessBroker`
(which audits every access attempt, allowed or denied, because access
*is* the security decision), a clean scan is the expected outcome of
essentially every LLM call in the system — auditing every one would
flood ``governance.audit_log`` with routine traffic rather than
security-relevant events. A detected leak is exactly the kind of rare,
security-relevant event that belongs there, matching this ticket's own
Output: "Blocked send plus an audit record" describes the one event
that produces both.

**Never logs or reveals a value, including the leaked one.** The audit
row's ``detail`` never contains prompt content or a secret value —
only which prompt was blocked and for whom, the same secrets_management.md
§8 "never record the secret value itself" discipline
:class:`AccessBroker` already applies.
"""

from __future__ import annotations

from collections.abc import Iterable

from ai_os_kernel.observability.audit import AuditLogWriter, AuditOutcome
from ai_os_kernel.prompt_engine.models import PromptRenderResponse
from ai_os_kernel.secrets_manager.errors import SecretLeakDetectedError
from ai_os_kernel.secrets_manager.value import SecretValue
from ai_os_kernel.security_manager.models import SecurityContext


async def scan_rendered_prompt_for_secret_leak(
    prompt: PromptRenderResponse,
    *,
    resolved_secrets: Iterable[SecretValue],
    audit_log: AuditLogWriter,
    context: SecurityContext,
) -> PromptRenderResponse:
    """Returns ``prompt`` unchanged if none of ``resolved_secrets``
    appear verbatim in ``prompt.content``.

    Raises :class:`~ai_os_kernel.secrets_manager.errors.SecretLeakDetectedError`
    if any do — after writing a ``secret.leak.blocked`` row to
    ``governance.audit_log`` naming the prompt (never the leaked
    value), so a blocked send is never a silent no-op.
    """
    leaked = any(secret.reveal() in prompt.content for secret in resolved_secrets)
    if not leaked:
        return prompt

    resource_id = f"{prompt.prompt_id}#{prompt.version}"
    await audit_log.record(
        event_type="secret.leak.blocked",
        principal_id=context.principal.principal_id,
        principal_type=context.principal.principal_type,
        outcome=AuditOutcome.DENIED,
        detail={},
        resource_type="prompt",
        resource_id=resource_id,
    )
    raise SecretLeakDetectedError(
        f"prompt {resource_id!r} contains a resolved secret value verbatim "
        "-- refusing to send it to a model"
    )
