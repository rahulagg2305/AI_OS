"""Minimal write path for ``evaluation.llm_calls``.

Records one row per completed :class:`~ai_os_kernel.llm_gateway.gateway.
LLMGateway.complete` call — the Observability subsystem named in
llm_gateway.md §3 and §13 ("Every call emits a span and writes one
``evaluation.llm_calls`` row"), reduced to exactly that one write. No
span, no metrics, no other observability work — "no full observability
platform work beyond this writer" is this step's own fence.

**Deliberately not an ``LLMGateway``-conforming decorator.** A wrapper
that both calls an inner gateway and records the result would need
per-call correlation context (workflow, step, agent, prompt) that
:class:`~ai_os_kernel.llm_gateway.models.LLMRequest` does not carry —
that field (``metadata: TraceContext`` in the full §4 contract) was
deliberately excluded when the request contract was reduced, and
reintroducing it now would be Context Manager/tracing-integration scope
this step's own fence excludes. Composed explicitly by the caller
instead: call :meth:`~ai_os_kernel.llm_gateway.gateway.LLMGateway.complete`
first, then :meth:`LLMCallRecorder.record` with the workflow/step
context the caller already has — exactly "after a successful
``EchoLLMGateway.complete()`` call, write one ``evaluation.llm_calls``
row," the approved step's own shape, not a hidden extra abstraction.

**Column mapping** — every value comes directly from the already-produced
``LLMRequest``/``LLMResponse``/``UsageRecord`` (no field is invented):
``model_alias`` ← ``request.model_alias``; ``provider``/``model_id`` ←
``response.provider``/``response.model_id``; ``stop_reason`` ←
``response.stop_reason.value``; every ``UsageRecord`` field maps to its
identically-named column. ``degradations`` has no source in the reduced
``LLMResponse`` (capability negotiation was deferred at the contract
level too) — stored as an empty JSONB array, the same "no field maps to
this yet" honesty already used for ``catalog.workflow_definitions.
declared_permissions``.

**``agent_id``/``prompt_id``/``prompt_version`` are optional on the call
path** — the approved shape's own words — **but the schema makes them
NOT NULL with real foreign keys** (data_model.md §6,
:mod:`ai_os_kernel.persistence.evaluation_schema`), so there is no way
to store a partial or absent combination today. All three are required
together: passing fewer than three raises :class:`~ai_os_kernel.
llm_gateway.errors.LLMCallRecordingError` before any database access,
clearly, rather than surfacing a ``NOT NULL`` violation from Postgres.
When all three are provided, they must reference real
``catalog.agents``/``catalog.prompts`` rows — enforced by the
already-existing foreign keys on ``evaluation.llm_calls`` itself (built
when that table was created), not re-implemented here; a violation is
still wrapped in the same clean error, never a bare stack trace.
``workflow_id``/``step_id`` are always required, matching the schema
exactly.
"""

from __future__ import annotations

from typing import Protocol

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.llm_gateway.errors import LLMCallRecordingError
from ai_os_kernel.llm_gateway.ids import new_call_id
from ai_os_kernel.llm_gateway.models import LLMRequest, LLMResponse
from ai_os_kernel.persistence.evaluation_schema import llm_calls


class LLMCallRecorder(Protocol):
    """Persistence boundary for recording one completed LLM Gateway call
    — the seam a fake implementation substitutes in unit tests (ADR-0004:
    interface-driven, configuration over code)."""

    async def record(
        self,
        *,
        request: LLMRequest,
        response: LLMResponse,
        workflow_id: str,
        step_id: str,
        agent_id: str | None = None,
        prompt_id: str | None = None,
        prompt_version: str | None = None,
    ) -> None: ...


class SqlLLMCallRecorder:
    """The only implementation of :class:`LLMCallRecorder` at this
    stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def record(
        self,
        *,
        request: LLMRequest,
        response: LLMResponse,
        workflow_id: str,
        step_id: str,
        agent_id: str | None = None,
        prompt_id: str | None = None,
        prompt_version: str | None = None,
    ) -> None:
        if not workflow_id or not workflow_id.strip():
            raise LLMCallRecordingError("workflow_id must not be blank")
        if not step_id or not step_id.strip():
            raise LLMCallRecordingError("step_id must not be blank")
        if agent_id is None or prompt_id is None or prompt_version is None:
            raise LLMCallRecordingError(
                "agent_id, prompt_id, and prompt_version must all be provided together: "
                "evaluation.llm_calls.agent_id/prompt_id are NOT NULL with real foreign "
                "keys to catalog.agents/catalog.prompts (data_model.md §6), so a partial "
                "or absent combination cannot be recorded"
            )

        usage = response.usage
        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    sa.insert(llm_calls).values(
                        call_id=new_call_id(),
                        workflow_id=workflow_id,
                        step_id=step_id,
                        agent_id=agent_id,
                        prompt_id=prompt_id,
                        prompt_version=prompt_version,
                        model_alias=request.model_alias,
                        provider=response.provider,
                        model_id=response.model_id,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        cache_read_tokens=usage.cache_read_tokens,
                        cache_write_tokens=usage.cache_write_tokens,
                        cost_usd=usage.cost_usd,
                        latency_ms=usage.latency_ms,
                        stop_reason=response.stop_reason.value,
                        retries=usage.retries,
                        fallback_used=usage.fallback_used,
                        degradations=[],
                    )
                )
        except sa.exc.SQLAlchemyError as exc:
            raise LLMCallRecordingError(
                f"failed to record LLM call for workflow '{workflow_id}' step '{step_id}': {exc}"
            ) from exc
