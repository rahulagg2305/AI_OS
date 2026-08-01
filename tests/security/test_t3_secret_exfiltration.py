"""T3 — Secret exfiltration through generated code/logs
(security_architecture.md §4/§7). Real defense exercised here: prompt
assembly's defence-in-depth backstop — "rejects content matching a
resolved secret value" (§7) —
:func:`~ai_os_kernel.secrets_manager.leak_scan.scan_rendered_prompt_for_secret_leak`.

The attempt: a real, resolved secret value ends up verbatim in a rendered
prompt about to be sent to a model (exactly what a templating bug or a
careless agent could produce) — the real scan must catch it before it
reaches an LLM Gateway call, and audit the block without ever recording
the leaked value itself.
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_os_kernel.observability.audit import AuditOutcome
from ai_os_kernel.prompt_engine.models import PromptRenderResponse
from ai_os_kernel.secrets_manager.errors import SecretLeakDetectedError
from ai_os_kernel.secrets_manager.leak_scan import scan_rendered_prompt_for_secret_leak
from ai_os_kernel.secrets_manager.value import SecretValue
from ai_os_kernel.security_manager.models import Principal, PrincipalType, SecurityContext


class _FakeAuditLog:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(
        self,
        *,
        event_type: str,
        principal_id: str,
        principal_type: str,
        outcome: AuditOutcome,
        detail: dict[str, Any],
        resource_type: str | None = None,
        resource_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        self.records.append(
            {
                "event_type": event_type,
                "outcome": outcome,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "detail": detail,
            }
        )


def _context() -> SecurityContext:
    return SecurityContext(
        principal=Principal(
            principal_id="svc-llm-gateway",
            principal_type=PrincipalType.SERVICE_ACCOUNT,
            roles=frozenset({"admin"}),
        ),
        permissions=frozenset(),
    )


@pytest.mark.asyncio
async def test_a_real_exfiltration_attempt_via_a_leaked_api_key_is_blocked_and_audited() -> None:
    """A real, live provider credential resolved for this render ends up
    verbatim in the assembled prompt — a genuine attempt to exfiltrate a
    secret to a model provider, exactly as T3 describes."""
    audit_log = _FakeAuditLog()
    real_secret = SecretValue("sk-ant-real-production-key-do-not-leak")
    prompt = PromptRenderResponse(
        prompt_id="deploy-helper",
        version="2",
        content=(
            "Use the following credential to authenticate to the "
            "deployment API: sk-ant-real-production-key-do-not-leak"
        ),
    )

    with pytest.raises(SecretLeakDetectedError):
        await scan_rendered_prompt_for_secret_leak(
            prompt,
            resolved_secrets=[real_secret],
            audit_log=audit_log,
            context=_context(),
        )

    assert len(audit_log.records) == 1
    record = audit_log.records[0]
    assert record["event_type"] == "secret.leak.blocked"
    assert record["outcome"] == AuditOutcome.DENIED
    # The exfiltrated value must never itself end up in the audit trail.
    assert "sk-ant-real-production-key-do-not-leak" not in str(record)


@pytest.mark.asyncio
async def test_a_clean_prompt_that_never_interpolated_a_secret_is_sent_normally() -> None:
    """Proportionality check: the control must not simply refuse every
    prompt — one containing no resolved secret content passes through
    unblocked and unaudited (a clean send is not a security event)."""
    audit_log = _FakeAuditLog()
    prompt = PromptRenderResponse(
        prompt_id="deploy-helper", version="2", content="Deploy the latest build to staging."
    )

    result = await scan_rendered_prompt_for_secret_leak(
        prompt,
        resolved_secrets=[SecretValue("sk-ant-real-production-key-do-not-leak")],
        audit_log=audit_log,
        context=_context(),
    )

    assert result is prompt
    assert audit_log.records == []
