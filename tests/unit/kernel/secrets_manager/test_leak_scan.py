"""``scan_rendered_prompt_for_secret_leak`` — proves a clean prompt
(no secret content) renders through unchanged, and a prompt containing
a resolved secret verbatim is detected, rejected, and audited rather
than silently sent. ``P01-S02-M19-T06``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ai_os_kernel.observability.audit import AuditOutcome
from ai_os_kernel.prompt_engine.models import PromptRenderResponse
from ai_os_kernel.secrets_manager.errors import SecretLeakDetectedError
from ai_os_kernel.secrets_manager.leak_scan import scan_rendered_prompt_for_secret_leak
from ai_os_kernel.secrets_manager.value import SecretValue
from ai_os_kernel.security_manager.models import Principal, PrincipalType, SecurityContext


class _FakeAuditLog:
    """A fake ``AuditLogWriter`` — no real database needed to prove
    what gets recorded and what does not (ADR-0004)."""

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
                "principal_id": principal_id,
                "principal_type": principal_type,
                "outcome": outcome,
                "detail": detail,
                "resource_type": resource_type,
                "resource_id": resource_id,
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


def test_a_clean_prompt_with_no_secret_content_renders_normally() -> None:
    async def _run() -> None:
        audit_log = _FakeAuditLog()
        prompt = PromptRenderResponse(
            prompt_id="greeting", version="1", content="Hello, world! No secrets here."
        )
        resolved_secrets = [SecretValue("sk-real-api-key")]

        result = await scan_rendered_prompt_for_secret_leak(
            prompt,
            resolved_secrets=resolved_secrets,
            audit_log=audit_log,
            context=_context(),
        )

        assert result is prompt
        assert audit_log.records == []  # no security-relevant event to record

    asyncio.run(_run())


def test_a_prompt_with_no_resolved_secrets_at_all_renders_normally() -> None:
    async def _run() -> None:
        audit_log = _FakeAuditLog()
        prompt = PromptRenderResponse(prompt_id="greeting", version="1", content="Hello, world!")

        result = await scan_rendered_prompt_for_secret_leak(
            prompt, resolved_secrets=[], audit_log=audit_log, context=_context()
        )

        assert result is prompt
        assert audit_log.records == []

    asyncio.run(_run())


def test_a_leaked_resolved_secret_is_detected_rejected_and_audited() -> None:
    async def _run() -> None:
        audit_log = _FakeAuditLog()
        prompt = PromptRenderResponse(
            prompt_id="summarize",
            version="3",
            content="Use this key to authenticate: sk-real-api-key -- now proceed.",
        )
        resolved_secrets = [SecretValue("sk-real-api-key")]

        with pytest.raises(SecretLeakDetectedError):
            await scan_rendered_prompt_for_secret_leak(
                prompt,
                resolved_secrets=resolved_secrets,
                audit_log=audit_log,
                context=_context(),
            )

        assert len(audit_log.records) == 1
        record = audit_log.records[0]
        assert record["event_type"] == "secret.leak.blocked"
        assert record["principal_id"] == "svc-llm-gateway"
        assert record["outcome"] == AuditOutcome.DENIED
        assert record["resource_type"] == "prompt"
        assert record["resource_id"] == "summarize#3"
        # The one property that matters most: the leaked value never
        # appears anywhere in the audit row.
        assert "sk-real-api-key" not in str(record)

    asyncio.run(_run())


def test_the_exception_message_never_contains_the_leaked_value() -> None:
    async def _run() -> None:
        audit_log = _FakeAuditLog()
        prompt = PromptRenderResponse(
            prompt_id="summarize", version="3", content="key=sk-real-api-key"
        )

        with pytest.raises(SecretLeakDetectedError) as exc_info:
            await scan_rendered_prompt_for_secret_leak(
                prompt,
                resolved_secrets=[SecretValue("sk-real-api-key")],
                audit_log=audit_log,
                context=_context(),
            )

        assert "sk-real-api-key" not in str(exc_info.value)
        assert "summarize#3" in str(exc_info.value)

    asyncio.run(_run())


def test_only_one_of_several_resolved_secrets_leaking_is_still_caught() -> None:
    async def _run() -> None:
        audit_log = _FakeAuditLog()
        prompt = PromptRenderResponse(
            prompt_id="summarize", version="3", content="unrelated content sk-second-secret here"
        )
        resolved_secrets = [SecretValue("sk-first-secret"), SecretValue("sk-second-secret")]

        with pytest.raises(SecretLeakDetectedError):
            await scan_rendered_prompt_for_secret_leak(
                prompt,
                resolved_secrets=resolved_secrets,
                audit_log=audit_log,
                context=_context(),
            )

        assert len(audit_log.records) == 1

    asyncio.run(_run())
