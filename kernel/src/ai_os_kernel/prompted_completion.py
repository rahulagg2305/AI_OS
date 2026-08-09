"""Minimal, explicit composition of the Prompt Engine and the LLM
Gateway — proving system_architecture.md's "LLM Abstraction Path" end
to end:

    Agent (in a Capability Pack)
       +-> Prompt Engine        renders a versioned prompt, returns it to the caller
       +-> LLM Gateway          receives the rendered prompt + tools + schema

"The Prompt Engine returns a rendered prompt to the caller; it is not a
proxy in the call path. The caller then invokes the LLM Gateway." Both
:mod:`ai_os_kernel.prompt_engine` and :mod:`ai_os_kernel.llm_gateway`
were built to deliberately not call each other for exactly this reason.
:class:`PromptedCompletionService` is that caller — connective tissue
only, not a new architectural subsystem, not a Protocol (a composition
of two already-injected Protocols needs no seam of its own — ADR-0004:
an interface is justified only when a second implementation is real or
clearly imminent), and not a real ``Agent`` — "full Agent runtime
redesign" is explicitly out of scope this step, so this does not
implement or extend :class:`ai_os_kernel.workflow_engine.agent.Agent`.

**Rendered content becomes the sole user message.** ``PromptEngine``
renders one block of text with no documented split between "system
instructions" and "user turn" at this reduced-contract stage (that
split needs the deferred Context Manager); mapping it to
:attr:`~ai_os_kernel.llm_gateway.models.LLMRequest.system` instead would
invent a distinction the render contract does not make. ``model_alias``
and ``max_output_tokens`` are supplied by the caller directly — they are
call parameters of the LLM Gateway, not something a rendered prompt
would ever produce.

**Recording via the existing ``evaluation.llm_calls`` writer is
optional, per call, and adds no new logic.** A ``call_recorder`` may be
supplied at construction; a given call is recorded only when the caller
also supplies ``workflow_id``/``step_id`` for that call — exactly the
correlation context :class:`~ai_os_kernel.llm_gateway.call_recorder.
LLMCallRecorder` already requires and already validates (its own
"``agent_id``/``prompt_id``/``prompt_version`` must all be provided
together" rule still applies unchanged: recording without an
``agent_id`` fails there, not here). Omitting either leaves that one
call unrecorded rather than raising — the same "optional on the call
path" shape the recorder itself already established.

**The same ``workflow_id``/``step_id`` this method already received
now also reaches the LLM Gateway itself, not only the call recorder.**
:meth:`PromptedCompletionService.complete_from_prompt` builds a
:class:`~ai_os_kernel.llm_gateway.models.TraceContext` (the LLM
Gateway's first real slice of platform_sdk.md §4.1's canonical
``TraceContext`` — "Field names are normative") from them and sets it
as the constructed :class:`~ai_os_kernel.llm_gateway.models.LLMRequest`'s
``metadata`` — the exact, documented mechanism llm_gateway.md §4 names
for this (``metadata: TraceContext``), enabling
:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`'s
per-workflow budget ceiling (llm_gateway.md §9). No new parameter here
— ``workflow_id``/``step_id`` were already accepted; only what happens
with them changed. When both are ``None`` (every caller before this
change), ``metadata`` stays ``None`` too, identical to before.

**"One real end-to-end path" step**: :func:`build_anthropic_prompted_completion_service`
is the "connect the existing composition path" deliverable of that
step — a small factory assembling the one concrete, real composition
the approved framing named explicitly (``PromptEngine -> LLMGateway
(AnthropicAdapter) -> optional llm_calls recording``): a real
``catalog.prompts``-backed :class:`~ai_os_kernel.prompt_engine.catalog.SqlPromptCatalog`,
a real :class:`~ai_os_kernel.llm_gateway.adapters.anthropic_adapter.AnthropicAdapter`
(its API key resolved through the existing
:class:`~ai_os_kernel.secrets_manager.provider.SecretProvider`, never
read from ``ANTHROPIC_API_KEY`` directly), and a real
:class:`~ai_os_kernel.llm_gateway.call_recorder.SqlLLMCallRecorder` —
all three already-existing, already-tested implementations, composed
here rather than reimplemented. Wired into ``kernel/bootstrap.py``
(``_build_prompted_agent_registry``), the real composition root.

**``additional_gateways`` (added when the second real provider adapter
arrived) still does not make this a generic "build me any provider"
factory** (that remains Router/composition-root territory — this
function only ever builds the Anthropic adapter itself; it merely also
*registers whatever the caller already built* into the same
``DispatchingLLMGateway``). ``kernel/bootstrap.py`` is the only caller
that passes a non-empty ``additional_gateways`` today, when
``config/llm.yaml`` declares a ``local_provider``; every other existing
caller keeps getting the identical single-provider gateway this
function always built.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.llm_gateway.adapters.anthropic_adapter import (
    PROVIDER_NAME,
    build_anthropic_adapter,
)
from ai_os_kernel.llm_gateway.adapters.model_config import ModelPricing
from ai_os_kernel.llm_gateway.backoff import BackoffPolicy
from ai_os_kernel.llm_gateway.budget_enforcer import BudgetEnforcer, CountBudgetEnforcer
from ai_os_kernel.llm_gateway.call_recorder import LLMCallRecorder, SqlLLMCallRecorder
from ai_os_kernel.llm_gateway.capability_negotiator import CapabilityNegotiator
from ai_os_kernel.llm_gateway.circuit_breaker import CircuitBreaker
from ai_os_kernel.llm_gateway.gateway import DispatchingLLMGateway, LLMGateway
from ai_os_kernel.llm_gateway.models import (
    LLMRequest,
    LLMResponse,
    Message,
    MessageRole,
    TraceContext,
)
from ai_os_kernel.llm_gateway.router import Router
from ai_os_kernel.prompt_engine.catalog import SqlPromptCatalog
from ai_os_kernel.prompt_engine.models import PromptRenderRequest, PromptRenderResponse
from ai_os_kernel.prompt_engine.renderer import PromptEngine
from ai_os_kernel.secrets_manager.provider import SecretProvider


class PromptedCompletionResult(BaseModel):
    """The two artifacts a caller needs from one prompted completion:
    which rendered prompt was used, and what the model returned."""

    model_config = ConfigDict(frozen=True)

    render: PromptRenderResponse
    response: LLMResponse


class PromptedCompletionService:
    """Composes :class:`PromptEngine` and :class:`LLMGateway` — see this
    module's docstring for why this exists and what it deliberately does
    not do."""

    def __init__(
        self,
        prompt_engine: PromptEngine,
        llm_gateway: LLMGateway,
        call_recorder: LLMCallRecorder | None = None,
    ) -> None:
        self._prompt_engine = prompt_engine
        self._llm_gateway = llm_gateway
        self._call_recorder = call_recorder

    async def complete_from_prompt(
        self,
        *,
        prompt_id: str,
        prompt_version: str,
        variables: dict[str, Any] | None = None,
        model_alias: str,
        max_output_tokens: int,
        workflow_id: str | None = None,
        step_id: str | None = None,
        agent_id: str | None = None,
    ) -> PromptedCompletionResult:
        render_response = await self._prompt_engine.render(
            PromptRenderRequest(
                prompt_id=prompt_id,
                version=prompt_version,
                variables=variables or {},
            )
        )

        metadata = (
            TraceContext(workflow_id=workflow_id, step_id=step_id)
            if workflow_id is not None or step_id is not None
            else None
        )
        llm_request = LLMRequest(
            model_alias=model_alias,
            messages=[Message(role=MessageRole.USER, content=render_response.content)],
            max_output_tokens=max_output_tokens,
            metadata=metadata,
        )
        llm_response = await self._llm_gateway.complete(llm_request)

        if self._call_recorder is not None and workflow_id is not None and step_id is not None:
            await self._call_recorder.record(
                request=llm_request,
                response=llm_response,
                workflow_id=workflow_id,
                step_id=step_id,
                agent_id=agent_id,
                prompt_id=render_response.prompt_id,
                prompt_version=render_response.version,
            )

        return PromptedCompletionResult(render=render_response, response=llm_response)


async def build_anthropic_prompted_completion_service(
    *,
    engine: AsyncEngine,
    secret_provider: SecretProvider,
    api_key_secret_reference: str,
    router: Router,
    pricing: Mapping[str, ModelPricing],
    additional_gateways: Mapping[str, LLMGateway] | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    backoff_policy: BackoffPolicy | None = None,
    budget_enforcer: BudgetEnforcer | None = None,
    workflow_budget_enforcer: BudgetEnforcer | None = None,
    step_token_budget_enforcer: CountBudgetEnforcer | None = None,
    step_wall_time_budget_enforcer: CountBudgetEnforcer | None = None,
    capability_negotiator: CapabilityNegotiator | None = None,
) -> PromptedCompletionService:
    """Assembles the one real composition this step approves: a real
    ``catalog.prompts``-backed :class:`SqlPromptCatalog`, a real
    :class:`AnthropicAdapter` (API key resolved via ``secret_provider`` —
    never ``ANTHROPIC_API_KEY`` directly) behind a real
    :class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`,
    and a real :class:`SqlLLMCallRecorder`, composed into one
    :class:`PromptedCompletionService`.

    ``router``/``pricing`` are accepted, not loaded or constructed from
    a hardcoded path here, so a caller decides where its routing
    configuration comes from (production: a
    :class:`~ai_os_kernel.llm_gateway.router.StaticRouter` built from
    ``config/llm.yaml`` via
    :func:`~ai_os_kernel.llm_gateway.adapters.model_config.load_provider_config`;
    tests: whatever small router the test needs) — the identical
    "accept, don't assume a path" shape
    :func:`~ai_os_kernel.llm_gateway.adapters.anthropic_adapter.build_anthropic_adapter`
    itself already uses for the same two parameters.

    ``additional_gateways`` merges in whatever other real
    :class:`~ai_os_kernel.llm_gateway.gateway.LLMGateway` implementations
    the caller has already constructed (today: a
    :class:`~ai_os_kernel.llm_gateway.adapters.local_adapter.LocalAdapter`,
    keyed by its own ``PROVIDER_NAME``, when ``kernel/bootstrap.py`` has
    a ``local_provider`` configured) — this function still always builds
    and registers the real Anthropic adapter itself, unconditionally, so
    every existing caller that never passes this new, defaulted-``None``
    parameter gets the identical single-provider
    ``DispatchingLLMGateway`` as before. Registering a second provider
    is purely additive: it establishes the real extension point a
    second real provider adapter would register into, without this
    function's required parameters or any existing caller changing.

    ``circuit_breaker``/``backoff_policy``/``budget_enforcer``/
    ``workflow_budget_enforcer``/``step_token_budget_enforcer``/
    ``step_wall_time_budget_enforcer``/``capability_negotiator`` are all
    passed straight through to :class:`DispatchingLLMGateway` unchanged
    — all seven defaulted to ``None`` ("disabled"/"not triggered," in
    that class's own terms) for the identical "existing callers see no
    behaviour change" reason ``additional_gateways`` already
    established.
    """

    anthropic_gateway = await build_anthropic_adapter(
        secret_provider=secret_provider,
        api_key_secret_reference=api_key_secret_reference,
        router=router,
        pricing=pricing,
    )
    gateways: dict[str, LLMGateway] = {PROVIDER_NAME: anthropic_gateway}
    gateways.update(additional_gateways or {})
    llm_gateway = DispatchingLLMGateway(
        router=router,
        gateways=gateways,
        circuit_breaker=circuit_breaker,
        backoff_policy=backoff_policy,
        budget_enforcer=budget_enforcer,
        workflow_budget_enforcer=workflow_budget_enforcer,
        step_token_budget_enforcer=step_token_budget_enforcer,
        step_wall_time_budget_enforcer=step_wall_time_budget_enforcer,
        capability_negotiator=capability_negotiator,
    )
    return PromptedCompletionService(
        prompt_engine=SqlPromptCatalog(engine),
        llm_gateway=llm_gateway,
        call_recorder=SqlLLMCallRecorder(engine),
    )
