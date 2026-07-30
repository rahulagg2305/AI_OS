"""Composition root for the AI_OS Platform Kernel.

Builds the Kernel's object graph in one explicit, deterministic place.
There is **no DI container** (ADR-0010) — every dependency is
constructed here, in order, and handed to whatever needs it. Reading
this file top to bottom is meant to tell the whole startup story:

1. Load configuration (Configuration Manager).
2. Configure structured logging and OpenTelemetry tracing and metrics.
3. Build the Manifest Loader.
4. Build the Health Service from component checks.
5. Build the FastAPI app and attach everything to ``app.state``.
6. On real startup (not import time — see ``_lifespan`` below): build
   the persistence engine, the Stage B ``AgentRegistry``, the minimum
   real Workflow Engine execution path, a minimal Security Manager
   bearer-token verifier, and the Capability Manager's pack lifecycle
   writer, attaching all of them to ``app.state``.
7. Register the Workflow Engine's HTTP routes — ``POST
   /api/v1/workflows``, the cursor-paginated ``GET /api/v1/workflows``,
   and the read-only ``GET /api/v1/workflows/{id}``, ``.../steps``,
   ``.../events`` — all authenticated and authorized by that Security
   Manager slice.
8. Register the Capability Manager's pack lifecycle HTTP routes —
   ``POST /api/v1/packs`` (register/install), ``.../activate``,
   ``.../deactivate``, and ``GET /api/v1/packs/{id}`` — gated on the
   new ``pack:manage``/``pack:read`` permissions, reusing the same
   ``app.state.pack_lifecycle_repository`` unchanged.
9. Build a real ``SqlAgentRegistry`` for the Software Engineering
   pack's own ``se.delivery_pipeline`` workflow
   (``_build_se_delivery_pipeline_registry``) and register ``POST
   /api/v1/workflows/se.delivery_pipeline``
   (:mod:`ai_os_kernel.routes.delivery_pipeline`) — the first
   pack-specific, HTTP-triggerable workflow in this codebase, gated by
   the same ``workflow:start`` permission the platform demo route
   already uses. The real composition this reuses
   (:mod:`ai_os_kernel.workflow_engine.delivery_pipeline`) was promoted
   here from ``tests/integration/_delivery_pipeline.py`` this same
   step — see that module's own docstring for why.

As further Stage B/C components land (pack discovery, ...), their
construction and startup order is added here, not scattered across
entrypoints.

**The LLM Gateway now has a second real, network-calling provider.**
``_build_prompted_agent_registry`` constructs a
:class:`~ai_os_kernel.llm_gateway.router.StaticRouter` from
``config/llm.yaml``'s alias mapping — each alias carrying its own
explicit :class:`~ai_os_kernel.llm_gateway.router.RoutingDecision`
(provider + model id), reading ``config/llm.yaml``'s new, optional
``providers:`` section for any alias that names a provider other than
Anthropic. When ``config/llm.yaml`` also declares a ``local_provider``
(a ``base_url``), this function builds a real
:class:`~ai_os_kernel.llm_gateway.adapters.local_adapter.LocalAdapter`
and passes it to
:func:`~ai_os_kernel.prompted_completion.build_anthropic_prompted_completion_service`
as ``additional_gateways`` — that function still always builds the
real Anthropic adapter itself and now merges both into one
:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`. No
``local_provider`` is configured by default, so this changes no
observable behaviour for every alias that already existed before this
step — it establishes a second, real extension point, exercised only
when an operator configures one.

**Each alias's route is now a real chain, not always a single
candidate.** ``_build_prompted_agent_registry`` builds each alias's
:class:`~ai_os_kernel.llm_gateway.router.RoutingDecision` via
:func:`~ai_os_kernel.llm_gateway.router.build_routing_chain`, from the
primary ``(provider, model_id)`` pair plus ``config/llm.yaml``'s new,
optional ``fallbacks:`` entries for that alias, in order.
:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway` walks
that chain on an ``LLMProviderError``. An alias with no ``fallbacks:``
entry gets exactly the single-candidate decision it always got, so
this changes no observable behaviour for every alias that configures
no chain.

**A real Circuit Breaker now backs every alias, chained or not.**
``_build_prompted_agent_registry`` constructs one
:class:`~ai_os_kernel.llm_gateway.circuit_breaker.InMemoryCircuitBreaker`
(``_CIRCUIT_BREAKER_FAILURE_THRESHOLD``/
``_CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS``, named, documented constants
— llm_gateway.md §10 specifies the mechanism, not the numbers) and
passes it to
:func:`~ai_os_kernel.prompted_completion.build_anthropic_prompted_completion_service`,
which threads it into the same
:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`.
Shared across every provider (keyed internally by provider name), so
Anthropic and the local provider each get their own independent
failure memory from one instance. Changes no observable behaviour
until a provider's circuit actually opens — every existing test and
prior behaviour is a healthy circuit's behaviour, unchanged.

**A real backoff policy now retries a failing candidate before the
chain moves past it.** ``_build_prompted_agent_registry`` also
constructs one :class:`~ai_os_kernel.llm_gateway.backoff.BackoffPolicy`
(``_BACKOFF_MAX_ATTEMPTS``/``_BACKOFF_BASE_DELAY_SECONDS``/
``_BACKOFF_MAX_DELAY_SECONDS``/``_BACKOFF_MAX_TOTAL_SECONDS``, the
identical named-constant carve-out) and passes it through the same
factory into the same ``DispatchingLLMGateway`` — full-jitter
exponential backoff, cooperating directly with the Circuit Breaker
already wired in (a retry is skipped, not attempted, if the prior
failure already opened that candidate's circuit). Changes no
observable behaviour for a candidate that succeeds on its first
attempt, exactly as the Circuit Breaker changes none for a provider
that never fails. All three of llm_gateway.md §3's named Retry &
Fallback Manager pieces — chain traversal, circuit breaking, backoff —
are now real, and all three are Error Taxonomy-aware (a `retriable`
failure is retried, a `transient`/`infrastructure` one counts toward
the breaker, a real `retry_after` hint is honoured — see
``ai_os_kernel.llm_gateway.error_taxonomy``'s own docstring).

**A real Policy & Budget Enforcer now backs every alias too.**
``_build_prompted_agent_registry`` also constructs one
:class:`~ai_os_kernel.llm_gateway.budget_enforcer.PerScopeBudgetEnforcer`
(``_ALIAS_BUDGET_CEILING_USD``, the identical named-constant carve-out)
and passes it through the same factory into the same
``DispatchingLLMGateway`` — a per-``model_alias`` cumulative-cost
ceiling reusing the ``usage.cost_usd`` both real adapters already
compute honestly, checked before every attempt, ahead of the Circuit
Breaker. Classified ``ErrorCategory.BUDGET`` and, uniquely among every
category, never triggers a fallback attempt — a budget ceiling applies
to the alias itself, not to whichever provider would serve it, so
trying a different candidate can never be the fix. Changes no
observable behaviour until an alias's cumulative spend actually
crosses the ceiling — every existing test and prior behaviour is a
within-budget alias's behaviour, unchanged.

**A second, independent ceiling now also exists — per-workflow, using
the first real slice of the documented ``TraceContext``.**
``_build_prompted_agent_registry`` constructs a second
``PerScopeBudgetEnforcer`` instance (``_WORKFLOW_BUDGET_CEILING_USD``)
and passes it as ``workflow_budget_enforcer``. It is keyed by
``request.metadata.workflow_id`` — populated by
:meth:`~ai_os_kernel.prompted_completion.PromptedCompletionService.complete_from_prompt`
from the ``workflow_id`` it already receives as a parameter (previously
used only for ``evaluation.llm_calls`` recording) via a new
:class:`~ai_os_kernel.llm_gateway.models.TraceContext` object — a
deliberately minimal, two-field (``workflow_id``/``step_id``) slice of
platform_sdk.md §4.1's seven-field canonical ``TraceContext`` ("Field
names are normative"). No change to any Workflow Engine code, and no
change to ``PromptedAgent`` or ``AgentStepExecutor`` — ``workflow_id``
already flowed this far before this step; only the last hop, into
``LLMRequest.metadata``, is new. A caller that never supplies
``workflow_id`` (every caller before this step) gets ``metadata=None``
and is completely unaffected — this step's own "preserve existing
behaviour for callers that do not use the new metadata" requirement.

Still deliberately minimal: one deterministic Router implementation,
no provider health beyond the breaker's own binary signal, no
experiment pinning, no agent/principal metadata, no capability
negotiation, no caching, no streaming, no rate limiting, no
`retry_after` HTTP-date parsing, no platform-wide `AiOsError`
hierarchy, and no `trace_id`/`span_id` on `TraceContext` yet (real
values already exist via this Kernel's own OpenTelemetry span context,
ADR-0017 — wiring that in is a distinct, later step, not attempted
here) — see each module's own docstring for exactly what is and is not
built.

**The Context Manager's first real slice now sits between the
Workflow Engine and the one real Agent, exactly where
agent_architecture.md's Invocation Lifecycle places it.**
``_lifespan`` constructs a
:class:`~ai_os_kernel.context_manager.manager.DefaultContextManager`
with one real resolver
(:class:`~ai_os_kernel.context_manager.resolvers.WorkflowStateResolver`),
attaches it to ``app.state.context_manager`` (the same "reachable
independently of any one closure" reasoning
``app.state.workflow_instance_repository`` already established), and
passes it to ``_build_workflow_trigger``, which threads it into
``AgentStepExecutor``. That executor now also receives the current
``workflow_id`` from
:meth:`~ai_os_kernel.workflow_engine.service.WorkflowInstanceService.advance`
(a small, additive ``StepExecutor.execute(step, workflow_id=...)``
signature extension — every implementation defaults it to ``None`` and
every implementation except ``AgentStepExecutor`` ignores it, so this
changes no observable behaviour for tool/no-op steps). The demo
workflow's one agent step now genuinely receives a real
:class:`~ai_os_kernel.context_manager.models.AssembledContext` —
containing the workflow instance's own declared ``inputs``, the only
real source this step builds — which
:class:`~ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent`
(agent_architecture.md's first real "Context Consumer") flattens into
one ``context`` prompt template variable. No change to
``WorkflowDefinition``/``WorkflowStep``/the Workflow Engine's state
machine, persistence, or leasing — see
:mod:`ai_os_kernel.context_manager`'s own docstring for the full
account of what is and is not built, and
:mod:`ai_os_kernel.workflow_engine.step_executor`'s own docstring for
why the signature extension is additive wiring, not a redesign.

**The Context Manager now also enforces a real token budget —
implementation_roadmap.md's own Stage B deliverable line for this
component ("deterministic assembly, budget enforcement, and trust
tagging").** ``app.state.context_manager`` is now constructed with
``default_token_budget=_CONTEXT_TOKEN_BUDGET`` — the identical named,
documented, placeholder-safety-limit carve-out every other Kernel
policy constant in this file already uses. No Workflow Engine or
``AgentStepExecutor`` file changed for this — the budget lives entirely
inside :class:`~ai_os_kernel.context_manager.manager.
DefaultContextManager`'s own construction and ``assemble()`` body; see
that module's own docstring for the admission algorithm (rank by
``relevance_score``, a stable sort so ties preserve resolver order,
then greedily admit what fits, reporting ``items_excluded_count``
honestly) and why it is enforcement, not the still-unbuilt Context
Filter/Ranker.

**The LLM Gateway's Capability Negotiator now has a real matrix
lookup — llm_gateway.md §3/§6, the next explicitly-named Stage B
deliverable ("capability matrix") once the Context Manager's own
deliverable line was fully met.** ``_build_prompted_agent_registry``
constructs a :class:`~ai_os_kernel.llm_gateway.capability_negotiator.
StaticCapabilityNegotiator` from the same ``router`` already built for
routing and a new ``capabilities:`` section in ``config/llm.yaml``
(keyed by real model id, the identical shape ``pricing:`` already
uses), and passes it to ``build_anthropic_prompted_completion_service``
as ``capability_negotiator``. This adds a real, callable
``DispatchingLLMGateway.capabilities(alias) -> ProviderCapabilities``
method — platform_sdk.md §5.1's own documented, synchronous signature
— but nothing in the request-handling path calls it: no tool-calling,
structured-output emulation, streaming, or context-window-fit check
exists yet to consume a capability answer, so this is a real, reachable
fact-lookup with no consumer yet, not a redesign of `complete()`'s own
behaviour. See :mod:`~ai_os_kernel.llm_gateway.capability_negotiator`'s
own docstring for the full design, including a documented discrepancy
between llm_gateway.md §6's thirteen-field matrix and platform_sdk.md
§5.1's own ten-field summary of it (this step implements the fuller,
Gateway-governing shape).

**Why a real HTTP route can exist now, and why it is still narrow.**
docs/07_api/api_architecture.md requires authentication and
authorization on every mutating endpoint ("Unauthenticated access is
denied for every endpoint except health/live, health/ready,
openapi.json"); the previous step's own alignment checkpoint found no
Security Manager existed yet to provide that, and deliberately stopped
at a callable-but-unrouted ``app.state.trigger_prompted_agent_workflow``
rather than violate the contract. This step adds exactly enough of a
Security Manager (:mod:`ai_os_kernel.security_manager`) to satisfy
that contract for a small handful of routes: bearer-token
authentication (a minimal, pre-shared-secret JWT verifier — not full
OIDC, see that module's own docstring for the documented upgrade path)
and two permission checks (``workflow:start``, ``workflow:read``, both
already modelled). :mod:`ai_os_kernel.routes.workflows` now has both
the write route from the previous step and three read-only routes
(instance detail, steps, events) reusing the same
``SqlWorkflowInstanceRepository`` read accessors the Workflow Engine
already had; every other documented endpoint in api_architecture.md §6
still does not exist.

Paths to configuration files, the manifest schema, and pack directories
are resolved relative to the current working directory — every
documented way of running the Kernel (``uv run uvicorn ...``, the
Docker image, Kubernetes) starts the process from the repository root.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.capability_manager.repository import SqlPackLifecycleRepository
from ai_os_kernel.configuration_manager import BootstrapEnv, ConfigurationManager, PlatformConfig
from ai_os_kernel.context_manager.manager import ContextManager, DefaultContextManager
from ai_os_kernel.context_manager.resolvers import WorkflowStateResolver
from ai_os_kernel.health import ComponentStatus, HealthService
from ai_os_kernel.llm_gateway.adapters.anthropic_adapter import (
    PROVIDER_NAME,
    build_anthropic_adapter,
)
from ai_os_kernel.llm_gateway.adapters.local_adapter import (
    PROVIDER_NAME as LOCAL_PROVIDER_NAME,
)
from ai_os_kernel.llm_gateway.adapters.local_adapter import build_local_adapter
from ai_os_kernel.llm_gateway.adapters.model_config import load_provider_config
from ai_os_kernel.llm_gateway.backoff import BackoffPolicy
from ai_os_kernel.llm_gateway.budget_enforcer import PerScopeBudgetEnforcer
from ai_os_kernel.llm_gateway.capability_negotiator import StaticCapabilityNegotiator
from ai_os_kernel.llm_gateway.circuit_breaker import InMemoryCircuitBreaker
from ai_os_kernel.llm_gateway.gateway import DispatchingLLMGateway, LLMGateway
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter, build_routing_chain
from ai_os_kernel.manifest_loader import ManifestLoader
from ai_os_kernel.observability import (
    TraceIdMiddleware,
    configure_logging,
    configure_metrics,
    configure_tracing,
    get_logger,
)
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.settings import DatabaseSettings
from ai_os_kernel.prompt_engine.catalog import SqlPromptCatalog
from ai_os_kernel.prompted_completion import build_anthropic_prompted_completion_service
from ai_os_kernel.routes.delivery_pipeline import router as delivery_pipeline_router
from ai_os_kernel.routes.health import router as health_router
from ai_os_kernel.routes.packs import router as packs_router
from ai_os_kernel.routes.workflows import router as workflows_router
from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.security_manager.token_verifier import (
    JWTBearerTokenVerifier,
    build_jwt_bearer_token_verifier,
)
from ai_os_kernel.workflow_engine.advance_runner import WorkflowAdvanceRunner, WorkflowRunResult
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.delivery_pipeline import build_pipeline_trigger
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository, WorkflowLeaseService
from ai_os_kernel.workflow_engine.models import StepType, WorkflowDefinition, WorkflowStep
from ai_os_kernel.workflow_engine.prompted_agent import PromptedAgent
from ai_os_kernel.workflow_engine.registry import (
    AgentRegistry,
    InMemoryAgentRegistry,
    InMemoryToolRegistry,
    SqlAgentRegistry,
)
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import (
    AgentStepExecutor,
    DispatchingStepExecutor,
    NoOpStepExecutor,
    ToolStepExecutor,
)

logger = get_logger("ai_os_kernel.bootstrap")

# The one agent this composition root registers so far — a fully-qualified
# "pack_id/agent_slug" shape (data_model.md §5) even though no real
# Capability Pack owns it yet; there is no Capability Manager to assign
# one (Stage C), and inventing a fake pack registration would be further
# from the truth than naming it honestly as a platform-level agent.
_PROMPTED_AGENT_ID = "platform/prompted-agent"

# ADR-0024's own local-development example reference, already the
# convention EnvSecretProvider's docstring and every prior step's tests
# use — not invented here.
_ANTHROPIC_API_KEY_SECRET_REFERENCE = "secret://env/llm/anthropic-api-key"  # noqa: S105 — a reference URI, not a credential

# The minimal Security Manager's own pre-shared JWT signing secret — the
# same "secret://env/..." local-development reference shape as
# _ANTHROPIC_API_KEY_SECRET_REFERENCE above, resolved through the
# identical EnvSecretProvider seam. See
# ai_os_kernel.security_manager.token_verifier for why this is a
# pre-shared secret and not a real OIDC provider yet.
_JWT_SIGNING_KEY_SECRET_REFERENCE = "secret://env/security/jwt-signing-key"  # noqa: S105 — a reference URI, not a credential

# Not part of workflow_architecture.md's Step Contract (only promptId/
# promptVersion/modelAlias are), so there is no declared field to read
# this from — PromptedAgent's own docstring already establishes that its
# composition root supplies this once per instance. A named, documented
# constant is the Constitution's own explicitly-permitted carve-out
# ("Hardcoding is prohibited unless technically unavoidable and
# explicitly documented") until a real per-agent configuration mechanism
# exists (Capability Manager territory, out of scope here).
_PROMPTED_AGENT_MAX_OUTPUT_TOKENS = 1024

# The Context Manager's Size & Token Budget Enforcer (context_manager.md
# §4/§6) needs a ceiling; that document names the mechanism, not the
# number, so this is the identical named-constant carve-out
# _PROMPTED_AGENT_MAX_OUTPUT_TOKENS above already uses, until a real
# per-request or per-agent configuration mechanism exists. A placeholder
# safety limit, not a tuned production value — generous enough that the
# one real resolver's own output (a workflow's own declared `inputs`)
# would need to be unusually large before this ceiling ever excludes it.
_CONTEXT_TOKEN_BUDGET = 8000

# The Retry & Fallback Manager's Circuit Breaker (llm_gateway.md §10)
# needs a consecutive-failure threshold and a half-open reset timer;
# §10 names neither number, so these are the identical "named,
# documented constant" carve-out _PROMPTED_AGENT_MAX_OUTPUT_TOKENS
# above already uses, until a real configuration mechanism for
# Gateway-wide resilience parameters exists (Policy & Budget Enforcer
# territory, out of scope here).
_CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
_CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS = 30.0

# The Retry & Fallback Manager's backoff policy (llm_gateway.md §10:
# "exponential backoff with jitter, bounded attempts and total time")
# — the identical named-constant carve-out as the Circuit Breaker
# constants immediately above, until a real configuration mechanism
# for Gateway-wide resilience parameters exists. Three same-candidate
# attempts total (the first plus two retries), starting at half a
# second and doubling up to an eight-second cap, bounded by a
# fifteen-second ceiling on the cumulative delay for one candidate.
_BACKOFF_MAX_ATTEMPTS = 3
_BACKOFF_BASE_DELAY_SECONDS = 0.5
_BACKOFF_MAX_DELAY_SECONDS = 8.0
_BACKOFF_MAX_TOTAL_SECONDS = 15.0

# The Policy & Budget Enforcer's two real, independent ceilings — one
# per model_alias (llm_gateway.md §9's own table has no exact row for
# this; it is a real, useful control in its own right, see
# ai_os_kernel.llm_gateway.budget_enforcer's own docstring for why) and
# one per workflow_id (§9: "Workflow cost ceiling | BudgetExceededError",
# now expressible via the new TraceContext slice, see that module and
# ai_os_kernel.llm_gateway.models for why). The identical named-constant
# carve-out as the Circuit Breaker/backoff constants above, until a real
# configuration mechanism for Gateway-wide policy parameters exists.
# Both are placeholder safety ceilings, not tuned production values.
_ALIAS_BUDGET_CEILING_USD = Decimal("10.00")
_WORKFLOW_BUDGET_CEILING_USD = Decimal("25.00")

# The smallest possible real workflow: one agent step naming
# _PROMPTED_AGENT_ID. Identifiers below follow the identical "no real
# Capability Pack owns this yet, name it honestly as platform-level"
# reasoning _PROMPTED_AGENT_ID's own comment already gives — not loaded
# from a workflow definition *file* via WorkflowDefinitionLoader,
# because there is no real pack directory for such a file to live in
# yet; every existing test in this codebase already constructs
# WorkflowDefinition objects directly in Python for the identical
# reason (no real Capability Pack context to load one from).
_DEMO_WORKFLOW_DEFINITION_ID = "platform.prompted_agent_smoke_test"
_DEMO_WORKFLOW_DEFINITION_VERSION = "1.0.0"
_DEMO_WORKFLOW_PACK_ID = "platform"
_DEMO_WORKFLOW_STEP_ID = "ask_prompted_agent"
_DEMO_WORKFLOW_PROMPT_ID = "platform.prompted_agent_smoke_test/greeting"
_DEMO_WORKFLOW_PROMPT_VERSION = "1.0.0"
_DEMO_WORKFLOW_MODEL_ALIAS = "fast-cheap"

# Bounds for driving the demo instance to completion — a one-step
# workflow completes in a single WorkflowAdvanceRunner.run_once() call,
# so this ceiling is deliberately generous, not tuned; there is no
# scheduler or retry policy to configure here (explicitly out of scope
# — "no full worker scheduler").
_DEMO_WORKFLOW_MAX_ITERATIONS = 5
_DEMO_WORKFLOW_LEASE_DURATION_SECONDS = 30
_DEMO_WORKFLOW_WORKER_ID = "bootstrap-trigger"


def _build_demo_workflow_definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        id=_DEMO_WORKFLOW_DEFINITION_ID,
        name="Prompted Agent Smoke Test",
        description=(
            "The smallest real workflow: one agent step invoking "
            f"{_PROMPTED_AGENT_ID}, proving a workflow instance can actually reach it."
        ),
        version=_DEMO_WORKFLOW_DEFINITION_VERSION,
        inputs={"type": "object"},
        outputs={"type": "object"},
        steps=[
            WorkflowStep(
                id=_DEMO_WORKFLOW_STEP_ID,
                type=StepType.AGENT,
                agent_id=_PROMPTED_AGENT_ID,
                prompt_id=_DEMO_WORKFLOW_PROMPT_ID,
                prompt_version=_DEMO_WORKFLOW_PROMPT_VERSION,
                model_alias=_DEMO_WORKFLOW_MODEL_ALIAS,
            )
        ],
        failure_handling={"on_error": "escalate"},
    )


def _load_configuration() -> PlatformConfig:
    repo_root = Path.cwd()
    bootstrap_env = BootstrapEnv()
    manager = ConfigurationManager(
        environment=bootstrap_env.env,
        platform_config_path=repo_root / "config" / "platform.yaml",
        environments_dir=repo_root / "infra" / "environments",
    )
    return manager.load(role=bootstrap_env.role)


def _build_manifest_loader(config: PlatformConfig) -> ManifestLoader:
    repo_root = Path.cwd()
    return ManifestLoader(
        pack_dirs=config.capability_pack_dirs,
        schema_path=repo_root / config.manifest_schema_path,
    )


def _build_health_service(config: PlatformConfig, manifest_loader: ManifestLoader) -> HealthService:
    def configuration_manager_check() -> ComponentStatus:
        # Reaching this closure at all means configuration already loaded
        # successfully at startup — see build_app().
        return ComponentStatus(
            name="configuration_manager", status="ok", detail=f"env={config.env}"
        )

    def manifest_loader_check() -> ComponentStatus:
        # Re-scans the filesystem on every call. Acceptable at Stage A
        # scale; revisit (cache with a short TTL) if this probe is hit
        # frequently against a large capability_packs/ tree.
        try:
            report = manifest_loader.scan()
        except Exception as exc:  # the schema/validator itself is broken
            return ComponentStatus(name="manifest_loader", status="error", detail=str(exc))
        detail = f"{len(report.discovered)} pack(s) discovered, {len(report.failed)} invalid"
        status = "ok" if not report.failed else "degraded"
        return ComponentStatus(name="manifest_loader", status=status, detail=detail)

    return HealthService([configuration_manager_check, manifest_loader_check])


async def _build_prompted_agent_registry(engine: AsyncEngine) -> AgentRegistry:
    """Real Secrets Resolution + ``AnthropicAdapter`` (+ a real
    ``LocalAdapter`` when ``config/llm.yaml`` configures one) +
    prompted-completion composition (:func:`~ai_os_kernel.prompted_completion.
    build_anthropic_prompted_completion_service`, extended this step to
    accept ``additional_gateways`` rather than reimplemented), registered
    under :data:`_PROMPTED_AGENT_ID` — the "register it so Workflow
    Engine agent steps can resolve it without test-only setup"
    deliverable of an earlier step.

    Takes an already-built ``engine`` (see ``_lifespan``, the only
    caller) rather than building its own, so the same connection pool
    backs both this and the Workflow Engine components this step adds —
    one engine per process, the established pattern.

    A missing/misconfigured ``config/llm.yaml`` or Anthropic secret
    degrades to an **empty** ``InMemoryAgentRegistry`` with a logged
    warning, rather than preventing the Kernel from starting at all:
    Stage A functionality (health checks, manifest discovery) must not
    depend on a Stage B integration being configured, the identical
    reasoning ``manifest_loader_check`` above already applies to a
    broken manifest schema. A missing *database*, unlike a missing LLM
    secret, is handled one level up in ``_lifespan`` — without a real
    engine there is nothing for this function, or the Workflow Engine
    components ``_build_workflow_trigger`` builds, to run against.

    **A real Capability Negotiator now backs the Gateway too** — a
    :class:`~ai_os_kernel.llm_gateway.capability_negotiator.
    StaticCapabilityNegotiator` built from the identical ``router`` this
    function already constructs and ``config/llm.yaml``'s new
    ``capabilities:`` section (``provider_config.capabilities``, the
    same ``model id -> real fact`` shape ``pricing`` already uses). This
    only makes ``DispatchingLLMGateway.capabilities(alias)`` answerable
    for real — nothing in the completion path calls it, so this changes
    no observable request-handling behaviour for any existing caller.
    """
    try:
        provider_config = load_provider_config(Path.cwd() / "config" / "llm.yaml")
        router = StaticRouter(
            routes={
                alias: build_routing_chain(
                    [(provider_config.providers.get(alias, PROVIDER_NAME), model_id)]
                    + [
                        (candidate.provider, candidate.model_id)
                        for candidate in provider_config.fallbacks.get(alias, [])
                    ]
                )
                for alias, model_id in provider_config.model_ids.items()
            }
        )

        additional_gateways: dict[str, LLMGateway] = {}
        if provider_config.local_base_url is not None:
            additional_gateways[LOCAL_PROVIDER_NAME] = build_local_adapter(
                base_url=provider_config.local_base_url,
                router=router,
                pricing=provider_config.pricing,
            )

        service = await build_anthropic_prompted_completion_service(
            engine=engine,
            secret_provider=EnvSecretProvider(),
            api_key_secret_reference=_ANTHROPIC_API_KEY_SECRET_REFERENCE,
            router=router,
            pricing=provider_config.pricing,
            additional_gateways=additional_gateways,
            circuit_breaker=InMemoryCircuitBreaker(
                failure_threshold=_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                reset_timeout_seconds=_CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS,
            ),
            backoff_policy=BackoffPolicy(
                max_attempts=_BACKOFF_MAX_ATTEMPTS,
                base_delay_seconds=_BACKOFF_BASE_DELAY_SECONDS,
                max_delay_seconds=_BACKOFF_MAX_DELAY_SECONDS,
                max_total_seconds=_BACKOFF_MAX_TOTAL_SECONDS,
            ),
            budget_enforcer=PerScopeBudgetEnforcer(ceiling_usd=_ALIAS_BUDGET_CEILING_USD),
            workflow_budget_enforcer=PerScopeBudgetEnforcer(
                ceiling_usd=_WORKFLOW_BUDGET_CEILING_USD
            ),
            capability_negotiator=StaticCapabilityNegotiator(
                router=router, capabilities_by_model_id=provider_config.capabilities
            ),
        )
    except Exception as exc:
        logger.warning("kernel.bootstrap.prompted_agent_unavailable", error=str(exc))
        return InMemoryAgentRegistry({})

    agent = PromptedAgent(service=service, max_output_tokens=_PROMPTED_AGENT_MAX_OUTPUT_TOKENS)
    logger.info("kernel.bootstrap.prompted_agent_registered", agent_id=_PROMPTED_AGENT_ID)
    return InMemoryAgentRegistry({_PROMPTED_AGENT_ID: agent})


def _build_workflow_trigger(
    engine: AsyncEngine, agent_registry: AgentRegistry, context_manager: ContextManager
) -> Callable[[dict[str, Any], str], Awaitable[WorkflowRunResult]]:
    """The minimum real Workflow Engine execution path this step
    approves: real, ``engine``-backed persistence
    (:class:`SqlWorkflowInstanceRepository`, :class:`SqlWorkflowDefinitionCatalog`,
    :class:`SqlWorkflowLeaseRepository`) driving the one demo
    :class:`WorkflowDefinition` (:func:`_build_demo_workflow_definition`)
    through create → start → run-to-completion — "create/start/advance
    one workflow instance path is enough," no worker scheduler, no
    multi-instance queue.

    ``agent_registry`` is whatever :func:`_build_prompted_agent_registry`
    returned (real or degraded-empty) — this function does not care
    which; :class:`AgentStepExecutor` already raises a clear
    ``AgentNotRegisteredError`` if the one agent the demo step declares
    is not present, exactly the same behaviour every other caller of
    that registry already gets.

    Returns a plain async function rather than a new class: it is
    "call three already-built async methods in sequence," which needs
    no seam of its own (ADR-0004) — the same reasoning
    :class:`~ai_os_kernel.prompted_completion.PromptedCompletionService`
    itself was built on. No tool step exists in the demo definition, so
    the tool registry it is handed is deliberately empty.

    **A real Context Manager now backs ``AgentStepExecutor``.**
    ``context_manager`` is whatever ``_lifespan`` built (see its own
    docstring) — constructed one level up, alongside ``engine`` and
    ``agent_registry``, rather than inside this function, so the same
    real instance is also reachable at ``app.state.context_manager`` for
    a caller (a test today) that wants to inspect it independently of
    this closure. This is genuinely new behaviour for the demo workflow
    (its one agent step now receives a real, if minimal,
    ``AssembledContext`` — see :mod:`ai_os_kernel.context_manager`'s own
    docstring for exactly what it contains), not a no-op wiring: unlike
    every optional Gateway parameter added in prior steps, there is no
    "configured or ``None``" branch here — the one real resolver this
    step builds has no external configuration to be missing, so a real
    ``ContextManager`` is always required and always passed.
    """
    instance_service = WorkflowInstanceService(
        repository=SqlWorkflowInstanceRepository(engine),
        step_executor=DispatchingStepExecutor(
            agent_executor=AgentStepExecutor(agent_registry, context_manager=context_manager),
            tool_executor=ToolStepExecutor(InMemoryToolRegistry({})),
            default_executor=NoOpStepExecutor(),
        ),
        definition_catalog=SqlWorkflowDefinitionCatalog(engine),
    )
    advance_runner = WorkflowAdvanceRunner(
        instance_service=instance_service,
        lease_service=WorkflowLeaseService(SqlWorkflowLeaseRepository(engine)),
    )
    definition = _build_demo_workflow_definition()

    async def trigger(inputs: dict[str, Any], principal_id: str) -> WorkflowRunResult:
        instance = await instance_service.create_instance(
            definition=definition,
            inputs=inputs,
            principal_id=principal_id,
            pack_id=_DEMO_WORKFLOW_PACK_ID,
        )
        await instance_service.start(
            workflow_id=instance.workflow_id,
            reason="platform.prompted_agent_smoke_test trigger",
        )
        return await advance_runner.run_to_completion(
            workflow_id=instance.workflow_id,
            definition=definition,
            worker_id=_DEMO_WORKFLOW_WORKER_ID,
            lease_duration_seconds=_DEMO_WORKFLOW_LEASE_DURATION_SECONDS,
            max_iterations=_DEMO_WORKFLOW_MAX_ITERATIONS,
        )

    return trigger


async def _build_se_delivery_pipeline_registry(engine: AsyncEngine) -> AgentRegistry:
    """Real ``SqlAgentRegistry`` composition for ``se.delivery_pipeline``'s
    own five pack-qualified agents (``software-engineering/*``) — the
    first real caller of :class:`~ai_os_kernel.workflow_engine.registry.SqlAgentRegistry`
    in this composition root (that class's own docstring: "bootstrap.py
    does not construct this class at all yet" — this is the step that
    makes that no longer true).

    **A deliberately simpler LLM Gateway composition than
    ``_build_prompted_agent_registry``'s own** — no circuit breaker,
    backoff policy, budget enforcer, or capability negotiator. This
    pipeline's own three LLM-calling agents need a real, working
    completion path to genuinely run; the platform demo's full
    resilience stack is real, useful infrastructure this pipeline does
    not yet have a documented need for. Adding it is a distinct, later
    step once real usage justifies it, not speculative infrastructure
    built ahead of that need (coding_standards.md: "no
    placeholder/speculative architecture").

    **Always returns a real, usable registry — never ``None``, even
    when no real Anthropic secret is configured.** A first version of
    this function degraded to ``None`` on any Gateway-construction
    failure, making the *entire* route reply a blanket ``503`` — a real,
    discovered inconsistency with ``_build_prompted_agent_registry``'s
    own established shape, which degrades to an agent-less registry
    instead, so the route still reaches the real Workflow Engine and
    gets an honest, structured ``failed`` outcome (a real per-agent
    permission/resolution error) rather than an opaque
    whole-composition unavailability. Fixed here to match: only the
    Gateway construction is guarded; ``llm_gateway`` degrades to
    ``None`` on failure (:class:`~ai_os_kernel.workflow_engine.registry.SqlAgentRegistry`'s
    own docstring: a resolved entrypoint's own permissions trigger a
    clear error from ``build_pack_context`` if a needed one is missing,
    rather than this composition silently proceeding or refusing to
    exist at all). ``SqlPromptCatalog`` needs no network/secret call to
    construct, so it is never guarded.

    Takes the already-built ``engine`` rather than constructing its
    own, the same one-engine-per-process reasoning every other
    engine-dependent composition in this file already follows.
    """
    llm_gateway: LLMGateway | None = None
    try:
        provider_config = load_provider_config(Path.cwd() / "config" / "llm.yaml")
        router = StaticRouter(
            routes={
                alias: RoutingDecision(
                    provider=provider_config.providers.get(alias, PROVIDER_NAME),
                    model_id=model_id,
                )
                for alias, model_id in provider_config.model_ids.items()
            }
        )
        anthropic_gateway = await build_anthropic_adapter(
            secret_provider=EnvSecretProvider(),
            api_key_secret_reference=_ANTHROPIC_API_KEY_SECRET_REFERENCE,
            router=router,
            pricing=provider_config.pricing,
        )
        llm_gateway = DispatchingLLMGateway(
            router=router, gateways={PROVIDER_NAME: anthropic_gateway}
        )
    except Exception as exc:
        logger.warning(
            "kernel.bootstrap.se_delivery_pipeline_llm_gateway_unavailable", error=str(exc)
        )

    return SqlAgentRegistry(engine, llm_gateway=llm_gateway, prompt_engine=SqlPromptCatalog(engine))


async def _build_token_verifier() -> JWTBearerTokenVerifier | None:
    """The minimal Security Manager's bearer-token authenticator (see
    ``ai_os_kernel.security_manager.token_verifier`` for what this
    deliberately is and is not).

    A missing/unresolvable signing secret degrades to ``None`` with a
    logged warning, the identical "catch, report, don't crash the
    process" shape ``_build_prompted_agent_registry`` already uses —
    but unlike an empty ``AgentRegistry`` (which safely resolves nothing
    for anyone), ``None`` here must make every permission-checking
    dependency **fail closed** (503, "security manager is not
    configured"), never default-allow. This has no dependency on the
    database engine — authentication is independent of persistence — so
    it is built unconditionally in ``_lifespan``, not only when a real
    engine exists.
    """
    try:
        return await build_jwt_bearer_token_verifier(
            secret_provider=EnvSecretProvider(),
            signing_key_secret_reference=_JWT_SIGNING_KEY_SECRET_REFERENCE,
        )
    except Exception as exc:
        logger.warning("kernel.bootstrap.token_verifier_unavailable", error=str(exc))
        return None


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Runs once when the API process actually starts serving requests
    (unlike ``build_app``, which runs synchronously at import time) —
    the only point in this file's startup story that can ``await``
    anything. A bare ``TestClient(app)`` never triggers this (verified,
    not assumed); only ``with TestClient(app) as client:`` does, which
    is exactly why every existing health-check test — none of which use
    the ``with`` form — is unaffected by this step.

    A missing/misconfigured database degrades to an empty
    ``AgentRegistry`` and **no** ``trigger_prompted_agent_workflow``,
    ``workflow_instance_repository``, ``context_manager``, or
    ``pack_lifecycle_repository`` at all — there is nothing real for any
    of them to run against without one, unlike a missing LLM secret
    alone (handled inside ``_build_prompted_agent_registry``), which
    still leaves a real database for the Workflow Engine components to
    use. The token verifier degrades independently of all five (see
    ``_build_token_verifier``), since authentication needs neither a
    database nor an LLM secret.
    """
    app.state.token_verifier = await _build_token_verifier()

    engine: AsyncEngine | None = None
    try:
        engine = build_engine(DatabaseSettings().database_url)
    except Exception as exc:
        logger.warning("kernel.bootstrap.database_unavailable", error=str(exc))

    if engine is None:
        app.state.agent_registry = InMemoryAgentRegistry({})
    else:
        app.state.agent_registry = await _build_prompted_agent_registry(engine)
        # The Context Manager's first real slice (ai_os_kernel.context_manager)
        # — one real resolver, reading through the same read accessor
        # workflow_instance_repository below already wraps, plus a real
        # Size & Token Budget Enforcer ceiling (_CONTEXT_TOKEN_BUDGET).
        # Constructed here, not inside _build_workflow_trigger, so the
        # identical real instance is also reachable at
        # app.state.context_manager for a caller (a test today) that
        # wants to inspect it directly — the same "plain, stateless
        # wrapper over the engine, safe to construct separately"
        # reasoning workflow_instance_repository below already
        # establishes.
        app.state.context_manager = DefaultContextManager(
            resolvers=[WorkflowStateResolver(SqlWorkflowInstanceRepository(engine))],
            default_token_budget=_CONTEXT_TOKEN_BUDGET,
        )
        app.state.trigger_prompted_agent_workflow = _build_workflow_trigger(
            engine, app.state.agent_registry, app.state.context_manager
        )
        # The same read accessors GET /workflows/{id}(/steps|/events)
        # use (ai_os_kernel.routes.workflows) — a plain, stateless
        # wrapper over the engine, safe to construct separately from the
        # WorkflowInstanceService instance _build_workflow_trigger builds
        # internally for writes.
        app.state.workflow_instance_repository = SqlWorkflowInstanceRepository(engine)
        # The Capability Manager's pack lifecycle writer (register/
        # install, activate, deactivate — see ai_os_kernel.capability_manager),
        # constructed the identical "plain, stateless wrapper over the
        # engine" way as workflow_instance_repository just above. No
        # route reads this yet ("No HTTP routes for packs yet" — this
        # step's own scope fence); it exists so a real caller (a test
        # today, a future route or CLI command later) can reach it
        # through the real composition root instead of only through a
        # hand-built engine.
        app.state.pack_lifecycle_repository = SqlPackLifecycleRepository(engine)
        # se.delivery_pipeline's own real trigger (ai_os_kernel.routes.delivery_pipeline)
        # — a second, independent trigger closure alongside
        # trigger_prompted_agent_workflow above. Always attached once a
        # real engine exists — a missing/invalid Anthropic secret
        # degrades the registry's own llm_gateway internally (see
        # _build_se_delivery_pipeline_registry's own docstring), so the
        # route still reaches the real Workflow Engine and returns an
        # honest, structured `failed` outcome instead of a blanket 503.
        app.state.trigger_se_delivery_pipeline = build_pipeline_trigger(
            engine, await _build_se_delivery_pipeline_registry(engine)
        )

    try:
        yield
    finally:
        if engine is not None:
            await engine.dispose()


def build_app(config: PlatformConfig | None = None) -> FastAPI:
    """Build and return the Kernel's FastAPI application.

    This is what the ``api`` process role starts from
    (see :mod:`ai_os_kernel.entrypoints.api`).
    """
    config = config or _load_configuration()
    configure_logging(config.log_level)
    configure_tracing()
    configure_metrics()
    logger.info("kernel.bootstrap.start", env=config.env, role=config.role)

    manifest_loader = _build_manifest_loader(config)
    health_service = _build_health_service(config, manifest_loader)

    app = FastAPI(
        title="AI_OS Kernel API",
        description=(
            "Transport layer for the AI_OS Platform Kernel. "
            "No business logic lives here — see docs/07_api/api_architecture.md."
        ),
        lifespan=_lifespan,
        version="0.1.0",
    )
    app.state.config = config
    app.state.manifest_loader = manifest_loader
    app.state.health_service = health_service
    app.add_middleware(TraceIdMiddleware)
    app.include_router(health_router)
    app.include_router(workflows_router)
    app.include_router(delivery_pipeline_router)
    app.include_router(packs_router)

    logger.info("kernel.bootstrap.complete")
    return app
