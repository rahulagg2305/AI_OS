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
10. Real pack discovery: every schema-valid manifest
    ``manifest_loader.scan()`` finds under the configured pack
    directories is genuinely registered (deriving real catalog rows via
    the manifest -> catalog installer) and activated
    (``_register_and_activate_discovered_packs``) — no manual ``POST
    /api/v1/packs`` call or test-harness seeding required for a real
    Kernel startup to make a real pack's agents genuinely resolvable.
11. The Pack Health Collector: one immediate poll per discovered pack
    at startup, then a real, continuously-running background task
    (``ai_os_kernel.capability_manager.health_poller.run_health_polling_loop``)
    that re-polls every ``POLL_INTERVAL_SECONDS`` for the life of the
    process — genuinely stopped, not merely abandoned, on shutdown.
12. The Lease Reaper: a second real, continuously-running background
    task (``ai_os_kernel.workflow_engine.lease_reaper.run_reap_loop``)
    that proactively reclaims expired ``workflow_leases`` rows every
    ``LEASE_REAP_INTERVAL_SECONDS``, the identical start/cancel pattern
    step 11 established.
13. The scheduled audit-chain verification job
    (``ai_os_kernel.observability.audit_verification_job.run_periodic_audit_chain_verification``)
    — built and unit-tested in an earlier step but never started in a
    real Kernel process until now. All three background loops (11, 12,
    13) are drained on shutdown through one
    ``ai_os_kernel.health.shutdown.GracefulShutdownCoordinator``
    (``P01-S04-M03-T06``), not three duplicated cancel-and-await blocks.

As further Stage B/C components land, their construction and startup
order is added here, not scattered across
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
(:class:`~ai_os_kernel.context_manager.resolvers.WorkflowStateResolver`,
joined as of ``P02-S03-M08-T11`` by
:class:`~ai_os_kernel.context_manager.resolvers.RuntimeConfigResolver`
— see that ticket's own note below for why),
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

**Real pack discovery now genuinely registers and activates every
schema-valid pack it finds — no more manual ``POST /api/v1/packs`` call
or test-harness seeding required.** ``_lifespan`` now calls
``_register_and_activate_discovered_packs`` (once a real database
engine exists — the same "nothing real to run without one" gating
every other engine-dependent piece of this file already follows) with
the already-built ``manifest_loader`` (``app.state.manifest_loader``,
built once at import time in ``build_app``) and the freshly-built
``pack_lifecycle_repository``. For each pack ``manifest_loader.scan()``
reports as discovered, it calls
:meth:`~ai_os_kernel.capability_manager.repository.SqlPackLifecycleRepository.register`
with ``pack_root`` set to that manifest's own directory — the real
manifest -> catalog installer path from the previous step
(:mod:`ai_os_kernel.capability_manager.manifest_catalog_installer`),
genuinely deriving ``catalog.agents``/``catalog.prompts``/``catalog.tools``
rows, not a bare pack row — then calls
:meth:`~ai_os_kernel.capability_manager.repository.SqlPackLifecycleRepository.activate`.
``sdk_version``/``min_kernel_version`` are read from the manifest's own
``dependencies.sdkVersion``/``compatibility.minKernelVersion`` fields
(schema-validated already, since only ``report.discovered`` entries
reach this function), never hardcoded literals — the earlier
test-harness code this step's predecessor step touched used to write
these as separate string literals that merely happened to match.

**Idempotent across restarts, by construction, not by a new special
case.** A restart against the same pack directory re-runs
``register()``, which raises :class:`PackAlreadyRegisteredError` on the
now-duplicate ``pack_id`` primary key — caught and logged at ``info``,
the expected steady state, not an error. ``activate()`` on an
already-``activated`` pack raises
:class:`InvalidPackTransitionError` for the identical reason (its own
``_ACTIVATABLE_FROM_STATES`` excludes ``ACTIVATED``) — also caught and
logged at ``info``. Neither duplicates a row nor crashes startup.
**One real, documented consequence of activating unconditionally
rather than only on first discovery**: a pack an operator manually
``deactivate()``'d through the HTTP route is, by design,
re-activatable (capability_manager.md §4's own state table calls
``deactivated`` "reactivatable" — see ``repository.py``'s own
docstring), so a Kernel restart genuinely re-activates it. There is no
"stay deactivated across restarts" mechanism in this codebase yet; this
is a known, documented limitation, not a bug this step silently
introduced.

**Per-pack resilience, not all-or-nothing.** A manifest that fails
schema validation (``report.failed``) is logged at ``warning`` and
skipped — the identical severity ``manifest_loader_check`` already uses
for the same fact. A genuine registration/activation failure for an
otherwise-valid, discovered manifest (a real database error, for
example) is logged at ``error`` — visible, distinguishable from the
benign idempotent-restart cases above, never silently swallowed — but
does not abort the loop or crash Kernel startup, the same per-item
resilience :meth:`ManifestLoader.scan` already guarantees ("one broken
pack must not prevent discovering every other pack"), now extended one
step further to registration/activation.

Paths to configuration files, the manifest schema, and pack directories
are resolved relative to the current working directory — every
documented way of running the Kernel (``uv run uvicorn ...``, the
Docker image, Kubernetes) starts the process from the repository root.

**``RuntimeConfigResolver`` now reaches a real production composition
too (``P02-S03-M08-T11``) — the first of the four resolvers built
disclosed as "not yet wired into any production composition" to close
that gap.** No roadmap ticket named this wiring before this step (found
by regenerating ``STATUS.md`` fresh and sweeping every ``todo`` ticket
tree-wide for a match); a new, minimal ticket was authored for it with
explicit product-owner sign-off, rather than guessing an existing
ticket's scope. Both real compositions that build a
:class:`~ai_os_kernel.context_manager.manager.DefaultContextManager` —
``_lifespan`` (the ``api`` role) and :func:`build_workflow_worker_loop`
(the ``worker`` role) — now also construct a real
:class:`~ai_os_kernel.configuration_manager.loader.ConfigurationManager`/
:class:`~ai_os_kernel.configuration_manager.runtime_overrides.RuntimeOverrideStore`
pair (:func:`_build_configuration_manager`, factored out of
:func:`load_configuration` unchanged) and add a
:class:`~ai_os_kernel.context_manager.resolvers.RuntimeConfigResolver`
reading ``_RUNTIME_CONTEXT_CONFIG_KEYS`` (``env``/``role``/``log_level``
— real, meaningful-to-an-agent fields, not the test-only
``*_interval_seconds`` override knobs) alongside the pre-existing
``WorkflowStateResolver``. This is also the first production composition
to keep a live ``RuntimeOverrideStore`` running at all — previously a
fully-built, fully-tested Layer 5 with zero real callers. Every
existing test/composition that never touches
``app.state.configuration_manager``/``app.state.runtime_override_store``
sees no behaviour change; the one real agent step now additionally
receives real runtime configuration in its assembled context, alongside
the workflow's own declared ``inputs``.

**``MemoryResolver`` reaches the identical two real compositions too
(``P02-S03-M08-T13``) — the third of the four resolvers to close the
same disclosed gap** (``KnowledgeResolver`` closed it separately, into
``se.delivery_pipeline``'s ``requirements-analyst`` step specifically,
``P02-S03-M08-T12`` — see :mod:`ai_os_kernel.workflow_engine.
delivery_pipeline`` for that one). Simpler than either: a plain
:class:`~ai_os_kernel.persistence.memory_writer.SqlMemoryStore` read,
no router/embedder/environment-validation dependency, so it is
unconditional in both compositions rather than wrapped in a ``try`` —
there is no real failure mode here worth degrading gracefully from.
``_MEMORY_RESOLVER_TYPE`` (``"engineering"``) is a real, considered
default from memory_manager.md's own documented taxonomy — the
cross-run, long-lived category, matching this resolver's own
deliberate "not scoped to one workflow" design, not the short-lived
``"workflow"`` category a single-run composition would otherwise
suggest.
"""

import asyncio
import hashlib
import os
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from fastapi import FastAPI
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.capability_manager.errors import (
    CapabilityManagerError,
    InvalidPackTransitionError,
    PackAlreadyRegisteredError,
)
from ai_os_kernel.capability_manager.health_poller import (
    CONSECUTIVE_FAILURE_THRESHOLD,
    POLL_INTERVAL_SECONDS,
    poll_pack_health,
    run_health_polling_loop,
)
from ai_os_kernel.capability_manager.repository import (
    PackLifecycleRepository,
    SqlPackLifecycleRepository,
)
from ai_os_kernel.configuration_manager import (
    BootstrapEnv,
    ConfigurationError,
    ConfigurationManager,
    PlatformConfig,
    RuntimeOverrideStore,
)
from ai_os_kernel.context_manager.manager import ContextManager, DefaultContextManager
from ai_os_kernel.context_manager.resolvers import (
    ContextSourceResolver,
    KnowledgeResolver,
    MemoryResolver,
    RuntimeConfigResolver,
    WorkflowStateResolver,
)
from ai_os_kernel.git_integration.default_service import build_git_integration_service_from_env
from ai_os_kernel.health import ComponentStatus, GracefulShutdownCoordinator, HealthService
from ai_os_kernel.knowledge_manager.query_engine import QueryEngine
from ai_os_kernel.llm_gateway.adapters.anthropic_adapter import (
    PROVIDER_NAME,
    build_anthropic_adapter,
)
from ai_os_kernel.llm_gateway.adapters.local_adapter import (
    PROVIDER_NAME as LOCAL_PROVIDER_NAME,
)
from ai_os_kernel.llm_gateway.adapters.local_adapter import build_local_adapter
from ai_os_kernel.llm_gateway.adapters.model_config import LLMProviderConfig, load_provider_config
from ai_os_kernel.llm_gateway.backoff import BackoffPolicy
from ai_os_kernel.llm_gateway.budget_enforcer import PerScopeBudgetEnforcer
from ai_os_kernel.llm_gateway.capability_negotiator import StaticCapabilityNegotiator
from ai_os_kernel.llm_gateway.circuit_breaker import InMemoryCircuitBreaker
from ai_os_kernel.llm_gateway.gateway import DispatchingLLMGateway, EchoLLMGateway, LLMGateway
from ai_os_kernel.llm_gateway.router import (
    Router,
    RoutingDecision,
    StaticRouter,
    build_routing_chain,
)
from ai_os_kernel.manifest_loader import ManifestLoader
from ai_os_kernel.observability import (
    AUDIT_CHAIN_VERIFICATION_INTERVAL_SECONDS,
    SqlAuditLogWriter,
    TraceIdMiddleware,
    configure_logging,
    configure_metrics,
    configure_tracing,
    get_logger,
    run_periodic_audit_chain_verification,
)
from ai_os_kernel.observability.settings import ObservabilitySettings
from ai_os_kernel.persistence.catalog_schema import agents as catalog_agents
from ai_os_kernel.persistence.catalog_schema import prompts as catalog_prompts
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_keyword_search import SqlKeywordSearcher
from ai_os_kernel.persistence.memory_writer import MemoryType, SqlMemoryStore
from ai_os_kernel.persistence.settings import DatabaseSettings
from ai_os_kernel.prompt_engine.catalog import SqlPromptCatalog
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.prompted_completion import build_anthropic_prompted_completion_service
from ai_os_kernel.retrieval.retrieval_service import RetrievalService
from ai_os_kernel.retrieval.vector_search import SqlVectorSearcher
from ai_os_kernel.routes.approvals import router as approvals_router
from ai_os_kernel.routes.delivery_pipeline import router as delivery_pipeline_router
from ai_os_kernel.routes.health import router as health_router
from ai_os_kernel.routes.packs import router as packs_router
from ai_os_kernel.routes.role_administration import router as role_administration_router
from ai_os_kernel.routes.workflows import router as workflows_router
from ai_os_kernel.sandbox.default_executor import build_default_sandbox_executor
from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.security_manager.token_verifier import (
    JWTBearerTokenVerifier,
    build_jwt_bearer_token_verifier,
)
from ai_os_kernel.workflow_engine.advance_runner import (
    WorkflowAdvanceRunner,
    WorkflowRunResult,
    WorkflowTrigger,
)
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.delivery_pipeline import DEFINITION_ID, build_pipeline_trigger
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository, WorkflowLeaseService
from ai_os_kernel.workflow_engine.lease_reaper import (
    LEASE_REAP_INTERVAL_SECONDS,
    WorkflowLeaseReaper,
    run_reap_loop,
)
from ai_os_kernel.workflow_engine.models import StepType, WorkflowDefinition, WorkflowStep
from ai_os_kernel.workflow_engine.pack_state import PackState
from ai_os_kernel.workflow_engine.prompted_agent import PromptedAgent
from ai_os_kernel.workflow_engine.registry import (
    AgentRegistry,
    InMemoryAgentRegistry,
    InMemoryToolRegistry,
    SqlAgentRegistry,
)
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.run_manifest_recorder import SqlRunManifestRecorder
from ai_os_kernel.workflow_engine.scheduler import (
    SCHEDULER_INTERVAL_SECONDS,
    WorkflowScheduler,
    run_scheduler_loop,
)
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import (
    AgentStepExecutor,
    DispatchingStepExecutor,
    NoOpStepExecutor,
    ToolStepExecutor,
)
from ai_os_kernel.workflow_engine.worker_loop import (
    WORKER_POLL_INTERVAL_SECONDS,
    WorkflowWorkerLoop,
    run_worker_loop,
)

logger = get_logger("ai_os_kernel.bootstrap")

# The database readiness check's own timeout ceiling (health_lifecycle.md
# §10's now-resolved "hard vs. soft dependency" gap: the database is a
# real hard dependency, checked with a genuine SELECT 1, not just "was a
# URL configured") — short enough that a readiness probe hitting this
# check every few seconds never accumulates meaningful latency even
# against a completely unreachable host, long enough not to false-fail a
# real database under brief, ordinary load. A placeholder safety bound,
# the identical named-constant carve-out every other Kernel policy
# constant in this file already uses.
_DATABASE_CHECK_TIMEOUT_SECONDS = 2.0

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

# RuntimeConfigResolver's own config_keys parameter (P02-S03-M08-T07's
# module docstring: "no guessing a typo'd name" -- validated against
# PlatformConfig.model_fields at construction). These three are real,
# meaningful-to-an-agent-step fields, not test-only override knobs (the
# *_interval_seconds fields exist purely to let a test skip a real
# production wait -- see PlatformConfig's own docstring for each).
_RUNTIME_CONTEXT_CONFIG_KEYS: tuple[str, ...] = ("env", "role", "log_level")

# KnowledgeResolver's own real constructor parameters (P02-S03-M08-T12).
# "embedding-fast" is the one real alias config/llm.yaml already
# declares for embeddings (-> nomic-embed-text, routed to `local` --
# see that file's own comment); never a literal model id, per ADR-0002.
# 10 is a named, documented placeholder ceiling, the identical carve-out
# _PROMPTED_AGENT_MAX_OUTPUT_TOKENS above already uses, until a real
# per-request/per-step configuration mechanism exists.
_KNOWLEDGE_EMBEDDING_MODEL_ALIAS = "embedding-fast"
_KNOWLEDGE_RESOLVER_LIMIT = 10

# MemoryResolver's own real constructor parameters (P02-S03-M08-T13).
# "engineering" (memory_manager.md's own documented taxonomy: workflow/
# engineering/reusable-asset) is the real, cross-run, long-lived
# category -- the one meaningful default for a generic composition
# reused by every agent step, not scoped to one workflow's own
# short-lived run. 10 is the identical named, documented placeholder
# ceiling _KNOWLEDGE_RESOLVER_LIMIT above already uses.
_MEMORY_RESOLVER_TYPE: MemoryType = "engineering"
_MEMORY_RESOLVER_LIMIT = 10

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

# The real content this demo prompt renders — the identical literal
# tests/integration/test_bootstrap_workflow_trigger.py's own
# _GREETING_TEMPLATE already uses for the same prompt id/version, so
# this is not a fresh invention, only a second real place the same
# real value lives.
_DEMO_WORKFLOW_PROMPT_CONTENT = "Hello from the smoke test!"

# catalog.agents/catalog.prompts real, enforced foreign keys that
# evaluation.llm_calls.agent_id/(prompt_id, prompt_version) require
# (persistence/evaluation_schema.py) — _PROMPTED_AGENT_ID and
# _DEMO_WORKFLOW_PROMPT_ID/_VERSION above were never rows in either
# table, so a real call-recorder write for this demo composition would
# fail with a foreign-key violation right after a real LLM call already
# succeeded. _seed_prompted_agent_catalog_rows (below) makes both real,
# idempotently, at the same startup point that already registers this
# agent — closing that gap rather than leaving it to surface as a
# runtime error the first time a real completion tries to record.
_PROMPTED_AGENT_VERSION = "0.1.0"
_PROMPTED_AGENT_ENTRYPOINT = "ai_os_kernel.workflow_engine.prompted_agent:PromptedAgent"

# Bounds for driving the demo instance to completion — a one-step
# workflow completes in a single WorkflowAdvanceRunner.run_once() call,
# so this ceiling is deliberately generous, not tuned; there is no
# scheduler or retry policy to configure here (explicitly out of scope
# — "no full worker scheduler").
_DEMO_WORKFLOW_MAX_ITERATIONS = 5
_DEMO_WORKFLOW_LEASE_DURATION_SECONDS = 30
_DEMO_WORKFLOW_WORKER_ID = "bootstrap-trigger"

# The audit trail actor/reason for every register()/activate() call this
# file makes on a discovered pack's behalf — a real Kernel process, not
# a human/test/route caller, so it gets its own identity rather than
# reusing "test" (every real test's own literal) or inventing a
# per-call reason. Named, documented constants, the identical carve-out
# every other literal in this file already uses.
_PACK_DISCOVERY_ACTOR = "kernel-bootstrap"
_PACK_DISCOVERY_REASON = "automatic discovery at Kernel startup"


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


def _build_configuration_manager(environment: str) -> ConfigurationManager:
    """The identical construction :func:`load_configuration` below uses,
    factored out so a caller needing a *persistent* instance
    (:class:`~ai_os_kernel.context_manager.resolvers.RuntimeConfigResolver`
    calls ``.load()`` again on every real request, per that class's own
    docstring) does not duplicate the three real path arguments."""
    repo_root = Path.cwd()
    return ConfigurationManager(
        environment=environment,
        platform_config_path=repo_root / "config" / "platform.yaml",
        environments_dir=repo_root / "infra" / "environments",
    )


def load_configuration() -> PlatformConfig:
    """Loads real, ``AIOS_``-env-driven configuration — the identical
    construction :func:`build_app` (the ``api`` role) already used
    privately, now also the ``worker`` role's own entrypoint
    (:mod:`ai_os_kernel.entrypoints.worker`) calls directly, since that
    role has no ``app``/``app.state`` of its own to read configuration
    from (``P01-S01-M40-T05``). Public for exactly that reason — every
    other ``_build_*`` helper in this module stays private, since only
    this module's own functions call them."""
    bootstrap_env = BootstrapEnv()
    manager = _build_configuration_manager(bootstrap_env.env)
    return manager.load(role=bootstrap_env.role)


def _build_manifest_loader(config: PlatformConfig) -> ManifestLoader:
    repo_root = Path.cwd()
    return ManifestLoader(
        pack_dirs=config.capability_pack_dirs,
        schema_path=repo_root / config.manifest_schema_path,
    )


def _format_pack_health_summary(pack_id: str, health: dict[str, Any]) -> str:
    """Renders one activated pack's own real ``catalog.packs.health``
    snapshot (written by
    :func:`~ai_os_kernel.capability_manager.health_poller.poll_pack_health`)
    into the same "bracketed annotation appended to a name" style
    ``manifest_loader_check`` already uses for ``not_activated`` — real,
    full detail (status, the consecutive-failure count *and* the real
    threshold it is measured against, when the snapshot was taken, and
    which specific agents are failing, if any), not a placeholder.
    """
    consecutive_failures = health.get("consecutive_failures", 0)
    summary = (
        f"{pack_id} [{health.get('status', 'unknown')}, "
        f"consecutive_failures={consecutive_failures}/{CONSECUTIVE_FAILURE_THRESHOLD}, "
        f"checked_at={health.get('checked_at', 'never')}]"
    )
    failed_agents = health.get("details", {}).get("failed_agents")
    if failed_agents:
        summary += f" failed_agents={sorted(failed_agents)}"
    return summary


def _build_health_service(
    config: PlatformConfig, manifest_loader: ManifestLoader, app: FastAPI
) -> HealthService:
    """``app`` is the same instance ``build_app`` is about to attach this
    very ``HealthService`` to — passed here, not built from, since this
    function runs before ``_lifespan`` ever populates
    ``app.state.pack_lifecycle_repository``/``app.state.database_engine``
    (real pack discovery, and the real database connectivity check
    below, both only happen once a real database engine exists).
    ``manifest_loader_check``/``database_check`` below read those
    attributes lazily, at call time, via the same
    ``getattr(app.state, ..., None)`` idiom
    :mod:`ai_os_kernel.routes.packs` already uses — by the time a real
    request hits ``/health/ready``, ``_lifespan`` may or may not have run
    yet (a bare ``TestClient(app)`` never triggers it at all), and both
    checks must degrade to a real "unreachable"/"absent" report, not
    raise, in either case.
    """

    def configuration_manager_check() -> ComponentStatus:
        # Reaching this closure at all means configuration already loaded
        # successfully at startup — see build_app().
        return ComponentStatus(
            name="configuration_manager", status="ok", detail=f"env={config.env}"
        )

    async def manifest_loader_check() -> ComponentStatus:
        # Re-scans the filesystem on every call. Acceptable at Stage A
        # scale; revisit (cache with a short TTL) if this probe is hit
        # frequently against a large capability_packs/ tree.
        try:
            report = manifest_loader.scan()
        except Exception as exc:  # the schema/validator itself is broken
            return ComponentStatus(name="manifest_loader", status="error", detail=str(exc))

        detail = f"{len(report.discovered)} pack(s) discovered, {len(report.failed)} invalid"
        status = "ok" if not report.failed else "degraded"

        # Real activation status — genuinely distinguishes (a) discovered
        # and activated, (b) discovered, schema-valid, but stuck/failed
        # during registration or activation, from (c) not schema-valid at
        # all (report.failed, already covered above). Only attempted when
        # a real pack_lifecycle_repository exists (a real database is
        # configured and _lifespan has already run) — the identical
        # "must not depend on a Stage B integration being configured"
        # degrade this file's every other Stage B component already
        # follows; with no repository, this check's behaviour is
        # byte-for-byte what it was before this step.
        repository: PackLifecycleRepository | None = getattr(
            app.state, "pack_lifecycle_repository", None
        )
        if repository is not None and report.discovered:
            not_activated: list[str] = []
            health_summaries: list[str] = []
            any_pack_degrading = False
            for discovered_pack in report.discovered:
                pack_id = discovered_pack.metadata.id
                record = await repository.get_pack(pack_id)
                if record is None:
                    not_activated.append(f"{pack_id} [not registered]")
                    continue
                if record.state is not PackState.ACTIVATED:
                    not_activated.append(f"{pack_id} [state={record.state.value}]")
                    continue

                # The Pack Health Collector's own real snapshot
                # (health_poller.poll_pack_health) — surfaced here for
                # every genuinely activated, already-polled pack, not
                # only ones that already crossed the failure threshold.
                # An activated pack with real, non-zero
                # consecutive_failures is a genuine early warning (it
                # has not yet been moved to PackState.FAILED — that is
                # the "not_activated" branch above, a distinct, later
                # consequence) and must be visible here, not silent
                # until the pack actually goes down.
                if record.health is not None:
                    health_summaries.append(_format_pack_health_summary(pack_id, record.health))
                    if record.health.get("consecutive_failures", 0) > 0:
                        any_pack_degrading = True

            activated_count = len(report.discovered) - len(not_activated)
            detail += f"; {activated_count} activated, {len(not_activated)} not activated"
            if not_activated:
                detail += f" ({', '.join(not_activated)})"
                status = "degraded"
            if health_summaries:
                detail += f"; health: {'; '.join(health_summaries)}"
            if any_pack_degrading:
                status = "degraded"

        return ComponentStatus(name="manifest_loader", status=status, detail=detail)

    async def database_check() -> ComponentStatus:
        """A real hard dependency (see :mod:`ai_os_kernel.health.service`'s
        own docstring for the evidence) — ``critical=True`` unconditionally,
        so an unreachable database escalates the overall report to
        ``"not_ready"`` (HTTP 503), not merely ``"degraded"``.

        Reuses ``app.state.database_engine`` (the same real, pooled
        engine ``_lifespan`` already built for everything else, exposed
        there for exactly this reason) rather than building a dedicated
        one per call — the cheapest way to make this genuine, not just
        "was a URL configured": ``create_async_engine`` is lazy, so the
        engine merely *existing* on ``app.state`` proves nothing about
        whether the real host behind it is reachable right now, only
        that construction (URL parsing) succeeded at startup. A real
        ``SELECT 1``, bounded by ``_DATABASE_CHECK_TIMEOUT_SECONDS`` so a
        completely unreachable host fails fast rather than hanging a
        readiness probe on the OS's own default TCP connect timeout, is
        what actually answers the question. Absent entirely when no
        database is configured (or under a bare ``TestClient(app)``,
        which never triggers ``_lifespan``) — reported as unreachable,
        not silently skipped, since a real Kernel with no database
        configured genuinely cannot serve any functional route either.
        """
        engine: AsyncEngine | None = getattr(app.state, "database_engine", None)
        if engine is None:
            return ComponentStatus(
                name="database",
                status="error",
                detail="no database engine configured",
                critical=True,
            )

        async def _ping() -> None:
            async with engine.connect() as connection:
                await connection.execute(sa.text("SELECT 1"))

        try:
            await asyncio.wait_for(_ping(), timeout=_DATABASE_CHECK_TIMEOUT_SECONDS)
        except Exception as exc:
            return ComponentStatus(
                name="database",
                status="error",
                detail=f"database unreachable: {exc}",
                critical=True,
            )
        return ComponentStatus(name="database", status="ok", detail="reachable", critical=True)

    return HealthService([configuration_manager_check, manifest_loader_check, database_check])


def _build_router(provider_config: LLMProviderConfig) -> Router:
    """The real, ``config/llm.yaml``-driven router construction
    :func:`_build_prompted_agent_registry` already performed inline —
    factored out (``P02-S03-M08-T12``) so :func:`_build_knowledge_resolver`
    below can build a second, independent one from a second, fresh
    ``load_provider_config()`` read, the identical "cheap to construct
    a second one" reasoning :func:`_build_configuration_manager` already
    established for ``ConfigurationManager``."""
    return StaticRouter(
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


async def _seed_prompted_agent_catalog_rows(engine: AsyncEngine) -> None:
    """Real, idempotent rows for the two foreign keys ``evaluation.
    llm_calls`` enforces (``agent_id`` -> ``catalog.agents.agent_id``;
    ``(prompt_id, prompt_version)`` -> ``catalog.prompts``' composite
    key) — without these, the moment :data:`_PROMPTED_AGENT_ID`'s own
    ``PromptedAgent`` genuinely completes a real call and its already-
    wired ``SqlLLMCallRecorder`` tries to record it, the insert fails
    with a real ``IntegrityError`` *after* that real (and, against a
    live provider, billed) completion already succeeded — turning a
    silent no-op (today, since :func:`~ai_os_kernel.workflow_engine.
    step_executor.AgentStepExecutor` never supplied ``stepId``/
    ``agentId``/``workflowId`` for the guard to even fire) into a real
    regression the moment that gap closes.

    ``ON CONFLICT ... DO NOTHING`` on both inserts: called on every real
    startup that reaches this composition (mirroring
    :func:`_register_and_activate_discovered_packs`'s own idempotent
    shape), so a second and every subsequent call against the same
    database must be a safe no-op, not a duplicate-key error.

    Every value inserted is a real, already-declared fact about this
    demo composition, not fabricated to satisfy the foreign key:
    ``entrypoint`` names the real :class:`~ai_os_kernel.workflow_engine.
    prompted_agent.PromptedAgent` class; ``output_schema`` is that
    class's own real, already-declared attribute; ``content`` is the
    identical literal :data:`_DEMO_WORKFLOW_PROMPT_CONTENT` names above,
    also the exact template `test_bootstrap_workflow_trigger.py`'s own
    ``_GREETING_TEMPLATE`` already renders in tests; ``content_hash`` is
    a real ``sha256`` of that same content, computed the identical way
    :func:`~ai_os_kernel.capability_manager.manifest_catalog_installer.
    _register_prompt`-equivalent real writers already do. ``input_schema``
    on both rows and ``required_permissions``/``required_tools`` on the
    agent row have no real source — this synthetic, no-manifest
    composition declares none — so they are stored honestly empty
    (``{}``/``[]``), the same "no field maps to this yet" convention
    :mod:`~ai_os_kernel.llm_gateway.call_recorder` already documents for
    ``degradations``.
    """
    async with engine.begin() as connection:
        await connection.execute(
            pg_insert(catalog_agents)
            .values(
                agent_id=_PROMPTED_AGENT_ID,
                pack_id=_DEMO_WORKFLOW_PACK_ID,
                version=_PROMPTED_AGENT_VERSION,
                entrypoint=_PROMPTED_AGENT_ENTRYPOINT,
                input_schema={},
                output_schema=PromptedAgent.output_schema,
                required_permissions=[],
                required_tools=[],
            )
            .on_conflict_do_nothing(index_elements=["agent_id"])
        )
        await connection.execute(
            pg_insert(catalog_prompts)
            .values(
                prompt_id=_DEMO_WORKFLOW_PROMPT_ID,
                version=_DEMO_WORKFLOW_PROMPT_VERSION,
                pack_id=_DEMO_WORKFLOW_PACK_ID,
                content=_DEMO_WORKFLOW_PROMPT_CONTENT,
                input_schema={},
                content_hash=(
                    f"sha256:{hashlib.sha256(_DEMO_WORKFLOW_PROMPT_CONTENT.encode('utf-8')).hexdigest()}"
                ),
            )
            .on_conflict_do_nothing(index_elements=["prompt_id", "version"])
        )


async def _build_prompted_agent_registry(engine: AsyncEngine) -> AgentRegistry:
    """Real Secrets Resolution + ``AnthropicAdapter`` (+ a real
    ``LocalAdapter`` when ``config/llm.yaml`` configures one) +
    prompted-completion composition (:func:`~ai_os_kernel.prompted_completion.
    build_anthropic_prompted_completion_service`, extended this step to
    accept ``additional_gateways`` rather than reimplemented), registered
    under :data:`_PROMPTED_AGENT_ID` — the "register it so Workflow
    Engine agent steps can resolve it without test-only setup"
    deliverable of an earlier step.

    Takes an already-built ``engine`` (``_lifespan`` for the ``api``
    role, :func:`build_workflow_worker_loop` for the ``worker`` role)
    rather than building its own, so the same connection pool backs
    both this and the Workflow Engine components built alongside it —
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

    **Also seeds the two real catalog rows this agent's own real call
    recording needs** — see :func:`_seed_prompted_agent_catalog_rows`.
    """
    try:
        provider_config = load_provider_config(Path.cwd() / "config" / "llm.yaml")
        router = _build_router(provider_config)

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

    try:
        await _seed_prompted_agent_catalog_rows(engine)
    except Exception as exc:
        # A genuinely unreachable database at this exact moment must not
        # revoke the agent registration above (the identical Stage-A-
        # must-not-depend-on-Stage-B-being-configured reasoning this
        # function's own outer except already applies) -- and, in
        # every real test that intentionally never connects its engine
        # (e.g. tests/unit/kernel/test_bootstrap.py's own fake
        # AIOS_DATABASE_URL, documented there as "engine construction
        # is lazy... only complete() does [real I/O]"), this is the
        # only place that invariant would otherwise break.
        logger.warning("kernel.bootstrap.prompted_agent_catalog_seed_failed", error=str(exc))
    agent = PromptedAgent(service=service, max_output_tokens=_PROMPTED_AGENT_MAX_OUTPUT_TOKENS)
    logger.info("kernel.bootstrap.prompted_agent_registered", agent_id=_PROMPTED_AGENT_ID)
    return InMemoryAgentRegistry({_PROMPTED_AGENT_ID: agent})


def _build_knowledge_resolver(engine: AsyncEngine) -> KnowledgeResolver | None:
    """The real, production ``KnowledgeResolver`` for ``se.delivery_pipeline``'s
    ``requirements-analyst`` step (``P02-S03-M08-T12``) — real
    ``QueryEngine``/``RetrievalService`` (module 9/11, unchanged, no
    parallel search mechanism) plus a real ``Embedder``, exactly the
    same real ``LocalAdapter`` :func:`_build_prompted_agent_registry`
    already builds for chat completions, built here a second time from
    a second, fresh ``load_provider_config()`` read — the identical
    "cheap to construct a second one" reasoning :func:`_build_router`
    above already documents.

    **Degrades to ``None``, not a crash, when no local embeddings
    server is configured** — ``config/llm.yaml``'s own comment states
    ``local_provider`` is "absent by default in a fresh checkout," the
    identical real, honest default :func:`_build_prompted_agent_registry`
    already tolerates for ``additional_gateways``. A caller wiring this
    into a composition must itself treat ``None`` as "no knowledge
    resolver available," the same shape :class:`RuntimeConfigResolver`'s
    own degrade-gracefully caller in ``_lifespan`` already establishes.
    """
    provider_config = load_provider_config(Path.cwd() / "config" / "llm.yaml")
    if provider_config.local_base_url is None:
        return None

    router = _build_router(provider_config)
    embedder = build_local_adapter(
        base_url=provider_config.local_base_url, router=router, pricing=provider_config.pricing
    )
    query_engine = QueryEngine(
        engine=engine,
        retrieval_service=RetrievalService(
            keyword_searcher=SqlKeywordSearcher(engine), vector_searcher=SqlVectorSearcher(engine)
        ),
    )
    return KnowledgeResolver(
        query_engine=query_engine,
        embedder=embedder,
        embedding_model_alias=_KNOWLEDGE_EMBEDDING_MODEL_ALIAS,
        limit=_KNOWLEDGE_RESOLVER_LIMIT,
    )


def _generate_worker_id(prefix: str) -> str:
    """A real, distinct identity per process — hostname + PID, never a
    shared literal (``P01-S01-M40-T05``). Before this step, exactly one
    process (the ``api`` role's own background loop, inside
    ``_lifespan``) ever ran a :class:`~ai_os_kernel.workflow_engine.
    worker_loop.WorkflowWorkerLoop`, so a fixed ``worker_id`` was
    harmless. Now that :func:`build_workflow_worker_loop` also backs a
    genuinely separate, real ``worker``-role process — and ADR-0020's
    own documented target is *N* such replicas — reusing one literal
    across all of them would make ``workflow_leases.worker_id`` unable
    to tell any of them apart. Hostname + PID is real, always available
    with no new configuration surface, and reads clearly in that
    column; a container's own hostname is normally its pod/container
    id, which is exactly the identity an operator already looks up."""
    return f"{prefix}-{socket.gethostname()}-{os.getpid()}"


async def build_workflow_worker_loop(engine: AsyncEngine) -> WorkflowWorkerLoop:
    """Builds the real, continuously-running multi-instance worker loop
    (``P02-S01-M05-T14``) — the one real construction shared by the
    ``api`` role's own background task (``_lifespan``) and the
    ``worker`` role's own standalone process
    (:mod:`ai_os_kernel.entrypoints.worker`, ``P01-S01-M40-T05``), so
    neither ever duplicates it.

    **Builds its own ``AgentRegistry``/``ContextManager``, rather than
    reusing ``app.state``'s.** Before this step, ``_lifespan`` passed
    its own already-built ``app.state.agent_registry``/
    ``app.state.context_manager`` (built for the demo trigger path) to
    this construction — reachable only because both lived in the same
    process. The ``worker`` role has no ``app``/``app.state`` at all, so
    this function builds its own pair from ``engine`` directly, the
    identical "cheap to construct a second one" reasoning this module
    already applies to ``WorkflowLeaseService`` (see ``lease_reap_task``
    in ``_lifespan``) — both are stateless wrappers over the same
    engine, so a second instance is behaviourally identical to reusing
    the first, not a second, divergent copy.

    Excludes ``se.delivery_pipeline`` (:data:`DEFINITION_ID`) from
    whatever this loop picks up — see the caller-side comment this
    function's own extraction preserved verbatim for the full reasoning
    (that pipeline's own real composition needs credential/git_service
    threading and real quality_gate/decision/human_approval executors
    this loop was never given; the approvals route's own synchronous
    resume is the sole safe resumption path for it).

    **``RuntimeConfigResolver`` (``P02-S03-M08-T11``) now rides alongside
    ``WorkflowStateResolver`` here too**, the identical "cheap to
    construct a second one" reasoning above already covers a second,
    independent ``ConfigurationManager``/``RuntimeOverrideStore`` pair —
    real, live runtime configuration is now part of every agent step's
    real, assembled context, not only reachable from an isolated test.
    Degrades gracefully, the identical reasoning ``_lifespan``'s own
    construction applies, when ``BootstrapEnv().env`` is not one of
    ConfigurationManager's real, documented environments.

    **``MemoryResolver`` (``P02-S03-M08-T13``) rides alongside too** —
    a real, plain ``SqlMemoryStore(engine)`` read, no embeddings/router
    dependency and no failure mode worth degrading (unlike
    ``RuntimeConfigResolver``'s environment validation), so it is
    unconditional, not wrapped in a ``try``.
    """
    agent_registry = await _build_prompted_agent_registry(engine)
    bootstrap_env = BootstrapEnv()
    context_resolvers: list[ContextSourceResolver] = [
        WorkflowStateResolver(SqlWorkflowInstanceRepository(engine)),
        MemoryResolver(
            memory_store=SqlMemoryStore(engine),
            memory_type=_MEMORY_RESOLVER_TYPE,
            limit=_MEMORY_RESOLVER_LIMIT,
        ),
    ]
    try:
        context_resolvers.append(
            RuntimeConfigResolver(
                configuration_manager=_build_configuration_manager(bootstrap_env.env),
                runtime_override_store=RuntimeOverrideStore(),
                role=bootstrap_env.role,
                config_keys=_RUNTIME_CONTEXT_CONFIG_KEYS,
            )
        )
    except ConfigurationError as exc:
        logger.warning("kernel.bootstrap.runtime_config_resolver_unavailable", error=str(exc))
    context_manager = DefaultContextManager(
        resolvers=context_resolvers,
        default_token_budget=_CONTEXT_TOKEN_BUDGET,
    )
    worker_loop_definition_catalog = SqlWorkflowDefinitionCatalog(engine)
    return WorkflowWorkerLoop(
        repository=SqlWorkflowInstanceRepository(engine),
        advance_runner=WorkflowAdvanceRunner(
            instance_service=WorkflowInstanceService(
                repository=SqlWorkflowInstanceRepository(engine),
                step_executor=DispatchingStepExecutor(
                    agent_executor=AgentStepExecutor(
                        agent_registry, context_manager=context_manager
                    ),
                    tool_executor=ToolStepExecutor(InMemoryToolRegistry({})),
                    default_executor=NoOpStepExecutor(),
                ),
                definition_catalog=worker_loop_definition_catalog,
                run_manifest_recorder=SqlRunManifestRecorder(engine),
            ),
            lease_service=WorkflowLeaseService(SqlWorkflowLeaseRepository(engine)),
        ),
        definition_catalog=worker_loop_definition_catalog,
        worker_id=_generate_worker_id("kernel-worker"),
        exclude_definition_ids=frozenset({DEFINITION_ID}),
    )


def _build_workflow_trigger(
    engine: AsyncEngine, agent_registry: AgentRegistry, context_manager: ContextManager
) -> WorkflowTrigger:
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
        run_manifest_recorder=SqlRunManifestRecorder(engine),
    )
    advance_runner = WorkflowAdvanceRunner(
        instance_service=instance_service,
        lease_service=WorkflowLeaseService(SqlWorkflowLeaseRepository(engine)),
    )
    definition = _build_demo_workflow_definition()

    async def trigger(
        inputs: dict[str, Any],
        principal_id: str,
        *,
        principal_permissions: frozenset[str] | None = None,
    ) -> WorkflowRunResult:
        instance = await instance_service.create_instance(
            definition=definition,
            inputs=inputs,
            principal_id=principal_id,
            pack_id=_DEMO_WORKFLOW_PACK_ID,
            principal_permissions=principal_permissions,
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

    **``git_service`` (P03-S01-M24-T02) is built from real ``AIOS_GIT_*``
    env vars, unguarded** — unlike ``llm_gateway`` above, a *partially*
    configured ``AIOS_GIT_REMOTE_URL`` (missing author identity or
    protected branches) is a genuine operator misconfiguration, not an
    ordinary "no credential in this environment yet" state, so it fails
    startup loudly (:class:`~ai_os_kernel.git_integration.errors.
    GitIntegrationConfigError`) rather than degrading silently — the
    identical "fail clearly at startup rather than silently proceeding"
    principle :class:`~ai_os_kernel.persistence.settings.DatabaseSettings`
    already establishes for a required-when-present value.
    :func:`~ai_os_kernel.git_integration.default_service.
    build_git_integration_service_from_env` itself returns ``None`` — the
    safe, existing no-op every current caller already relies on — when
    ``AIOS_GIT_REMOTE_URL`` is absent entirely, so a Kernel with no Git
    configuration at all still starts exactly as before this step.
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

    sandbox = build_default_sandbox_executor()
    git_service = build_git_integration_service_from_env(
        sandbox=sandbox, audit_log=SqlAuditLogWriter(engine)
    )

    return SqlAgentRegistry(
        engine,
        llm_gateway=llm_gateway,
        prompt_engine=SqlPromptCatalog(engine),
        sandbox=sandbox,
        git_service=git_service,
    )


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


async def _register_and_activate_discovered_packs(
    manifest_loader: ManifestLoader, pack_lifecycle_repository: SqlPackLifecycleRepository
) -> list[str]:
    """Real pack discovery -> registration -> activation, with zero
    manual intervention — see this module's own docstring for the full
    design (idempotency, degrade behaviour, why ``sdk_version``/
    ``min_kernel_version`` are read from the manifest rather than
    hardcoded).

    Only called once a real database engine exists (see ``_lifespan``,
    the only caller) — there is nothing real for ``register()``/
    ``activate()`` to write to without one, the identical "a missing
    database is handled one level up" reasoning
    ``_build_prompted_agent_registry``'s own docstring already states.

    Returns every schema-valid discovered pack's own ``pack_id`` —
    regardless of whether *this* call's own register/activate attempt
    succeeded, was a benign idempotent-restart skip, or hit a genuine,
    logged error — so ``_lifespan``'s own health-poll step (see
    :mod:`ai_os_kernel.capability_manager.health_poller`) can attempt a
    real poll for every discovered pack. A poll against a pack that
    genuinely isn't ``ACTIVATED`` for any reason correctly reports
    unhealthy on its own (agent resolution itself requires an activated
    pack) — not a special case this function needs to filter out first.
    """
    report = manifest_loader.scan()
    for failure in report.failed:
        logger.warning(
            "kernel.bootstrap.pack_manifest_invalid",
            manifest_path=failure.manifest_path,
            error=failure.error,
        )

    for discovered in report.discovered:
        pack_id = discovered.metadata.id
        pack_root = Path(discovered.manifest_path).parent
        try:
            await pack_lifecycle_repository.register(
                pack_id=pack_id,
                version=discovered.metadata.version,
                manifest=discovered.raw,
                sdk_version=discovered.raw["dependencies"]["sdkVersion"],
                min_kernel_version=discovered.raw["compatibility"]["minKernelVersion"],
                actor=_PACK_DISCOVERY_ACTOR,
                reason=_PACK_DISCOVERY_REASON,
                pack_root=pack_root,
            )
            logger.info("kernel.bootstrap.pack_registered", pack_id=pack_id)
        except PackAlreadyRegisteredError:
            logger.info("kernel.bootstrap.pack_already_registered", pack_id=pack_id)
        except CapabilityManagerError as exc:
            logger.error(
                "kernel.bootstrap.pack_registration_failed", pack_id=pack_id, error=str(exc)
            )
            continue

        try:
            await pack_lifecycle_repository.activate(
                pack_id=pack_id, actor=_PACK_DISCOVERY_ACTOR, reason=_PACK_DISCOVERY_REASON
            )
            logger.info("kernel.bootstrap.pack_activated", pack_id=pack_id)
        except InvalidPackTransitionError as exc:
            # Only genuinely benign if the real reason is "already
            # activated" — a real, discovered gap this step's own health
            # check work surfaced: every InvalidPackTransitionError used
            # to be logged at info unconditionally, which would have
            # misclassified a pack genuinely stuck in some other,
            # non-activatable state (e.g. "failed") as a harmless restart
            # instead of a real problem. Checked once, here, rather than
            # trusted blindly.
            current = await pack_lifecycle_repository.get_pack(pack_id)
            if current is not None and current.state is PackState.ACTIVATED:
                logger.info("kernel.bootstrap.pack_already_activated", pack_id=pack_id)
            else:
                logger.error(
                    "kernel.bootstrap.pack_activation_failed", pack_id=pack_id, error=str(exc)
                )
        except CapabilityManagerError as exc:
            logger.error("kernel.bootstrap.pack_activation_failed", pack_id=pack_id, error=str(exc))

    return [discovered.metadata.id for discovered in report.discovered]


async def _poll_discovered_pack_health(
    engine: AsyncEngine,
    pack_lifecycle_repository: SqlPackLifecycleRepository,
    agent_registry: AgentRegistry,
    pack_ids: list[str],
) -> None:
    """The Pack Health Collector's own real caller — one real poll per
    discovered pack, per Kernel startup. See
    :mod:`ai_os_kernel.capability_manager.health_poller`'s own docstring
    for the full design (the three-value policy, why there is no
    background scheduler yet, why this is deliberately the smallest
    real slice). ``agent_registry`` is whatever
    ``_build_se_delivery_pipeline_registry`` already built for the
    pipeline trigger — reused, not rebuilt, the same "one real object,
    not a second copy" reasoning this file already applies elsewhere
    (e.g. ``app.state.database_engine``).

    A genuine polling failure (a real database error, not merely an
    unhealthy pack — that is the *expected*, correctly-reported outcome
    of a real poll) is logged and does not abort polling the remaining
    packs, the identical per-item resilience
    ``_register_and_activate_discovered_packs`` already established.
    """
    for pack_id in pack_ids:
        try:
            report = await poll_pack_health(
                engine=engine,
                pack_lifecycle_repository=pack_lifecycle_repository,
                agent_registry=agent_registry,
                pack_id=pack_id,
                actor=_PACK_DISCOVERY_ACTOR,
            )
            logger.info(
                "kernel.bootstrap.pack_health_polled", pack_id=pack_id, status=report.status
            )
        except Exception as exc:
            logger.error(
                "kernel.bootstrap.pack_health_poll_failed", pack_id=pack_id, error=str(exc)
            )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Runs once when the API process actually starts serving requests
    (unlike ``build_app``, which runs synchronously at import time) —
    the only point in this file's startup story that can ``await``
    anything. A bare ``TestClient(app)`` never triggers this (verified,
    not assumed); only ``with TestClient(app) as client:`` does — a bare
    ``TestClient`` therefore has no ``database_engine`` either, and
    ``database_check`` reports it as genuinely unreachable, exactly as a
    real Kernel with no configured database would be.

    A missing/misconfigured database degrades to an empty
    ``AgentRegistry`` and **no** ``database_engine``,
    ``trigger_prompted_agent_workflow``, ``workflow_instance_repository``,
    ``context_manager``, ``pack_lifecycle_repository``,
    ``pack_health_polling_task``, ``lease_reap_task``, or
    ``workflow_worker_task`` at all — there is nothing real for any of
    them to run against without one, unlike a missing LLM secret alone
    (handled inside ``_build_prompted_agent_registry``), which still
    leaves a real database for the Workflow Engine components to use.
    The token verifier degrades independently of all seven, since
    authentication needs neither a database nor an LLM secret.

    **Five real, continuously-running background tasks are started
    here and drained through a single
    :class:`~ai_os_kernel.health.shutdown.GracefulShutdownCoordinator`
    (``P01-S04-M03-T06``) in this function's own ``finally`` block** —
    the Pack Health Collector's own polling loop
    (``ai_os_kernel.capability_manager.health_poller.run_health_polling_loop``),
    the Lease Reaper's own reap loop
    (``ai_os_kernel.workflow_engine.lease_reaper.run_reap_loop``), the
    audit-chain verification job
    (``ai_os_kernel.observability.audit_verification_job.run_periodic_audit_chain_verification``,
    built and unit-tested in ``P01-S05-M04-T06`` but never started
    anywhere until it was), the multi-instance worker loop
    (``ai_os_kernel.workflow_engine.worker_loop.run_worker_loop``,
    built and unit/integration-tested in ``P02-S01-M05-T12`` but
    deliberately left unstarted until a real, system-wide definition
    discovery mechanism existed for it to use — see
    ``definition_catalog.py``'s own docstring), and, as of this step
    (``P02-S01-M05-T13``), the Scheduler's own loop
    (``ai_os_kernel.workflow_engine.scheduler.run_scheduler_loop``,
    starting a `created` instance once its own real, persisted
    `scheduled_at` is due — workflow_engine.md §5.13's own
    previously-"not built at all" Scheduler component). All five are
    genuinely stopped — cancelled or signalled to stop, then awaited —
    before ``engine.dispose()`` runs, so no query any of them makes can
    ever race a closed connection pool.
    """
    app.state.token_verifier = await _build_token_verifier()
    shutdown_coordinator = GracefulShutdownCoordinator()
    app.state.shutdown_coordinator = shutdown_coordinator

    engine: AsyncEngine | None = None
    try:
        engine = build_engine(DatabaseSettings().database_url)
    except Exception as exc:
        logger.warning("kernel.bootstrap.database_unavailable", error=str(exc))

    if engine is None:
        app.state.agent_registry = InMemoryAgentRegistry({})
    else:
        # Exposed here, raw, for exactly one real reason: the Health
        # Service's own database_check (_build_health_service) needs
        # this real, pooled engine to issue a genuine SELECT 1 against
        # — every other app.state object below wraps it inside a
        # higher-level repository/service that does not expose it.
        app.state.database_engine = engine
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
        # MemoryResolver (P02-S03-M08-T13) -- a real, plain
        # SqlMemoryStore(engine) read, no failure mode worth degrading
        # (unlike RuntimeConfigResolver's environment validation below),
        # so it is unconditional.
        # RuntimeConfigResolver's own real, persistent collaborators
        # (P02-S03-M08-T11) -- kept alive on app.state when available,
        # the identical "reachable independently of any one closure"
        # reasoning app.state.context_manager itself already
        # establishes, since RuntimeConfigResolver.resolve() calls
        # .load() again on every real request (never a value cached
        # once here). Environment comes from a fresh BootstrapEnv()
        # read, the identical real, AIOS_-env-var-driven source
        # load_configuration() itself uses -- not app.state.config.env,
        # which a caller supplying its own PlatformConfig
        # (build_app(config=...), every test in this suite) may have
        # set to a value ConfigurationManager's own closed environment
        # vocabulary does not recognise. Degrades gracefully -- the
        # identical "catch, report, don't crash the process" shape
        # _build_token_verifier above already uses -- rather than
        # crash Kernel startup: deployment_architecture.md §4 names
        # exactly four real deployment environments
        # (local/dev/staging/production), and this repository's own CI
        # workflow sets AIOS_ENV=ci, an identity never meant to satisfy
        # that closed, documented vocabulary.
        context_resolvers: list[ContextSourceResolver] = [
            WorkflowStateResolver(SqlWorkflowInstanceRepository(engine)),
            MemoryResolver(
                memory_store=SqlMemoryStore(engine),
                memory_type=_MEMORY_RESOLVER_TYPE,
                limit=_MEMORY_RESOLVER_LIMIT,
            ),
        ]
        try:
            app.state.configuration_manager = _build_configuration_manager(BootstrapEnv().env)
            app.state.runtime_override_store = RuntimeOverrideStore()
            context_resolvers.append(
                RuntimeConfigResolver(
                    configuration_manager=app.state.configuration_manager,
                    runtime_override_store=app.state.runtime_override_store,
                    role=app.state.config.role,
                    config_keys=_RUNTIME_CONTEXT_CONFIG_KEYS,
                )
            )
        except ConfigurationError as exc:
            logger.warning("kernel.bootstrap.runtime_config_resolver_unavailable", error=str(exc))
        app.state.context_manager = DefaultContextManager(
            resolvers=context_resolvers,
            default_token_budget=_CONTEXT_TOKEN_BUDGET,
        )
        app.state.trigger_prompted_agent_workflow = _build_workflow_trigger(
            engine, app.state.agent_registry, app.state.context_manager
        )
        # The Lease Reaper's own real background loop — the "future
        # worker process framework" ai_os_kernel.workflow_engine.lease_reaper's
        # own docstring used to defer to, applying the identical
        # started-in-_lifespan/cancelled-in-finally pattern
        # health_polling_task above already proves. A dedicated,
        # plain, stateless WorkflowLeaseReaper/WorkflowLeaseService
        # pair over the same shared engine — the identical "cheap to
        # construct a second one" reasoning workflow_instance_repository
        # below already establishes, rather than threading state out
        # of _build_workflow_trigger's own internal one.
        lease_reap_interval = app.state.config.lease_reap_interval_seconds
        if lease_reap_interval is None:
            lease_reap_interval = LEASE_REAP_INTERVAL_SECONDS
        lease_reap_task = asyncio.create_task(
            run_reap_loop(
                reaper=WorkflowLeaseReaper(
                    WorkflowLeaseService(SqlWorkflowLeaseRepository(engine))
                ),
                interval_seconds=lease_reap_interval,
            )
        )
        app.state.lease_reap_task = lease_reap_task
        shutdown_coordinator.register_task("lease_reap", lease_reap_task)
        # The Scheduler's own real background loop (workflow_engine.md
        # §5.13, `P02-S01-M05-T13`) — starts a `created` instance once
        # its own real, persisted `scheduled_at` is due. A dedicated,
        # plain, stateless `WorkflowScheduler` over the same shared
        # engine — the identical "cheap to construct a second one"
        # reasoning `lease_reap_task` above already establishes.
        scheduler_interval = app.state.config.scheduler_interval_seconds
        if scheduler_interval is None:
            scheduler_interval = SCHEDULER_INTERVAL_SECONDS
        scheduler_task = asyncio.create_task(
            run_scheduler_loop(
                scheduler=WorkflowScheduler(SqlWorkflowInstanceRepository(engine)),
                interval_seconds=scheduler_interval,
            )
        )
        app.state.scheduler_task = scheduler_task
        shutdown_coordinator.register_task("scheduler", scheduler_task)
        # The multi-instance worker loop's own real background loop
        # (P02-S01-M05-T14) — the first of the four P02-S01-M05-T09
        # through T12 "proven, unused" capabilities to move to "proven,
        # running." Definition resolution goes through the real
        # SqlWorkflowDefinitionCatalog.get() that step added, not a
        # composition-injected mapping — genuine, system-wide
        # discovery of whichever definition an arbitrary, already-
        # running instance happens to belong to. Construction itself is
        # shared with the ``worker`` role's own standalone process
        # (``P01-S01-M40-T05``) — see build_workflow_worker_loop's own
        # docstring for the full reasoning, including why it builds its
        # own agent_registry/context_manager rather than reusing
        # app.state's.
        worker_loop = await build_workflow_worker_loop(engine)
        worker_poll_interval = app.state.config.worker_poll_interval_seconds
        if worker_poll_interval is None:
            worker_poll_interval = WORKER_POLL_INTERVAL_SECONDS
        workflow_worker_task = asyncio.create_task(
            run_worker_loop(worker=worker_loop, interval_seconds=worker_poll_interval)
        )
        app.state.workflow_worker_task = workflow_worker_task
        shutdown_coordinator.register_task("workflow_worker_loop", workflow_worker_task)
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
        # Real pack discovery -> registration -> activation — see this
        # module's own docstring and _register_and_activate_discovered_packs'
        # for the full design (idempotency, per-pack degrade behaviour).
        # Uses the manifest_loader already built and attached in
        # build_app(), reused rather than rebuilt.
        discovered_pack_ids = await _register_and_activate_discovered_packs(
            app.state.manifest_loader, app.state.pack_lifecycle_repository
        )
        # The Pack Health Collector's own real caller — one real poll
        # per discovered pack, per Kernel startup. See
        # ai_os_kernel.capability_manager.health_poller's own docstring
        # for the full design (poll interval/timeout/consecutive-failure
        # policy, why there is no background scheduler yet).
        #
        # Deliberately backed by a real, always-answering
        # EchoLLMGateway/InMemoryPromptEngine, never
        # se_delivery_pipeline_registry's own real, credential-gated
        # one built below — a genuine, discovered design correction
        # made during this step's own testing, not shipped as a first
        # guess. "Can this pack's agents still resolve/construct" is a
        # code-health question; whether a live Anthropic secret happens
        # to be configured right now is a separate, already-tracked
        # degrade (`se_delivery_pipeline_llm_gateway_unavailable`,
        # logged at warning). Polling with the credential-gated registry
        # would have reported the four llm:invoke agents "unhealthy"
        # for a missing secret alone — three such Kernel restarts with
        # no secret configured (a completely ordinary dev/CI state, not
        # a broken pack) would have genuinely, permanently failed the
        # pack via mark_failed(), with no recovery path
        # (`_ACTIVATABLE_FROM_STATES` excludes `FAILED`). The Echo/
        # InMemory pair used here is real, working infrastructure
        # (:class:`~ai_os_kernel.llm_gateway.gateway.EchoLLMGateway`,
        # the identical "deterministic, no live LLM call required"
        # backing every pack-agent unit/integration test in this
        # codebase already uses) — it genuinely exercises
        # `build_pack_context`'s own permission-gated injection path,
        # just never a real network call.
        health_check_agent_registry = SqlAgentRegistry(
            engine,
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={}),
        )
        await _poll_discovered_pack_health(
            engine,
            app.state.pack_lifecycle_repository,
            health_check_agent_registry,
            discovered_pack_ids,
        )
        # The real background scheduler enforcing POLL_INTERVAL_SECONDS
        # — the one-shot poll just above covers "healthy the instant
        # the Kernel starts"; this covers "still healthy an hour into a
        # long-running process." Reuses the identical health_check_agent_registry
        # and discovered_pack_ids the one-shot poll already used —
        # scheduling, not re-deciding what gets polled or how. Stored on
        # app.state so a caller (a test today) can inspect/await it
        # directly, the same "expose the real object" reasoning
        # database_engine above already establishes. Started here, never
        # awaited to completion — it runs for the lifetime of the
        # process and is cancelled cleanly in this function's own
        # ``finally`` block below.
        health_polling_interval = app.state.config.pack_health_poll_interval_seconds
        if health_polling_interval is None:
            health_polling_interval = POLL_INTERVAL_SECONDS
        health_polling_task = asyncio.create_task(
            run_health_polling_loop(
                engine=engine,
                pack_lifecycle_repository=app.state.pack_lifecycle_repository,
                agent_registry=health_check_agent_registry,
                pack_ids=discovered_pack_ids,
                actor=_PACK_DISCOVERY_ACTOR,
                interval_seconds=health_polling_interval,
            )
        )
        app.state.pack_health_polling_task = health_polling_task
        shutdown_coordinator.register_task("pack_health_poll", health_polling_task)
        # The scheduled audit-chain verification job
        # (P01-S05-M04-T06) — built and unit-tested before this step
        # but never started in a real Kernel process until now
        # (P01-S04-M03-T06). Uses the identical, already-proven
        # SqlAuditLogWriter (P01-S05-M04-T05/T06) as both the writer
        # and the read side (AuditChainReader), since it structurally
        # satisfies that Protocol via its own list_all(). Registered
        # as a stop-event job, not a cancelled one, per
        # GracefulShutdownCoordinator's own docstring: this loop
        # already accepts a cooperative stop signal and drains its
        # current pass before exiting on its own.
        audit_chain_verification_interval = (
            app.state.config.audit_chain_verification_interval_seconds
        )
        if audit_chain_verification_interval is None:
            audit_chain_verification_interval = AUDIT_CHAIN_VERIFICATION_INTERVAL_SECONDS
        audit_chain_verification_stop_event = asyncio.Event()
        audit_chain_verification_task = asyncio.create_task(
            run_periodic_audit_chain_verification(
                SqlAuditLogWriter(engine),
                interval_seconds=audit_chain_verification_interval,
                stop_event=audit_chain_verification_stop_event,
            )
        )
        app.state.audit_chain_verification_task = audit_chain_verification_task
        shutdown_coordinator.register_stop_event_task(
            "audit_chain_verification",
            audit_chain_verification_task,
            audit_chain_verification_stop_event,
        )
        # se.delivery_pipeline's own registry — real and
        # credential-gated, built here (not for the health poll above,
        # which needs an always-answering one instead — see its own
        # comment for why).
        se_delivery_pipeline_registry = await _build_se_delivery_pipeline_registry(engine)
        # se.delivery_pipeline's own real trigger (ai_os_kernel.routes.delivery_pipeline)
        # — a second, independent trigger closure alongside
        # trigger_prompted_agent_workflow above. Always attached once a
        # real engine exists — a missing/invalid Anthropic secret
        # degrades the registry's own llm_gateway internally (see
        # _build_se_delivery_pipeline_registry's own docstring), so the
        # route still reaches the real Workflow Engine and returns an
        # honest, structured `failed` outcome instead of a blanket 503.
        # KnowledgeResolver for requirements-analyst (P02-S03-M08-T12) —
        # degrades gracefully to None, the identical "catch, report,
        # don't crash the process" shape RuntimeConfigResolver's own
        # construction above already uses, since a fresh checkout
        # configures no real local embeddings server (config/llm.yaml's
        # own comment: "absent by default").
        try:
            se_delivery_pipeline_knowledge_resolver = _build_knowledge_resolver(engine)
        except Exception as exc:
            logger.warning("kernel.bootstrap.knowledge_resolver_unavailable", error=str(exc))
            se_delivery_pipeline_knowledge_resolver = None
        app.state.trigger_se_delivery_pipeline = build_pipeline_trigger(
            engine,
            se_delivery_pipeline_registry,
            knowledge_resolver=se_delivery_pipeline_knowledge_resolver,
        )
        # Exposed so ai_os_kernel.routes.approvals can genuinely resume
        # a paused se.delivery_pipeline instance after a real decision
        # (resume_pipeline_after_approval, P03-S03-M30-T06) with the
        # identical real, credential/git_service-threaded registry
        # trigger_se_delivery_pipeline itself already uses — never the
        # platform demo's own app.state.agent_registry, which does not
        # know this pack's agents at all.
        app.state.se_delivery_pipeline_agent_registry = se_delivery_pipeline_registry
        app.state.se_delivery_pipeline_knowledge_resolver = se_delivery_pipeline_knowledge_resolver

    try:
        yield
    finally:
        # Every registered background loop is genuinely drained
        # *before* the engine they query is disposed — each uses that
        # same engine on every iteration, so disposing first would race
        # a live query against a closed pool. A Kernel process with no
        # database registered nothing, so this is a genuine no-op for
        # that case (GracefulShutdownCoordinator.shutdown's own
        # docstring).
        await shutdown_coordinator.shutdown()
        if engine is not None:
            await engine.dispose()


def build_app(config: PlatformConfig | None = None) -> FastAPI:
    """Build and return the Kernel's FastAPI application.

    This is what the ``api`` process role starts from
    (see :mod:`ai_os_kernel.entrypoints.api`).
    """
    config = config or load_configuration()
    configure_logging(config.log_level)
    # OTEL_EXPORTER_OTLP_ENDPOINT is a bootstrap-minimum env var
    # (configuration_management.md §3.3), read directly here — the
    # identical reasoning DatabaseSettings().database_url below already
    # establishes — never a PlatformConfig/YAML value.
    otlp_endpoint = ObservabilitySettings().otlp_endpoint
    configure_tracing(otlp_endpoint=otlp_endpoint)
    configure_metrics(otlp_endpoint=otlp_endpoint)
    logger.info("kernel.bootstrap.start", env=config.env, role=config.role)

    manifest_loader = _build_manifest_loader(config)

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
    # Built after `app` exists (unlike every other Stage A component
    # above) and given a reference to it — see _build_health_service's
    # own docstring for why: its manifest_loader_check now needs to read
    # app.state.pack_lifecycle_repository, which does not exist yet at
    # this point in build_app() and is only ever populated later, inside
    # _lifespan, once a real database engine exists.
    app.state.health_service = _build_health_service(config, manifest_loader, app)
    app.add_middleware(TraceIdMiddleware)
    app.include_router(health_router)
    app.include_router(workflows_router)
    app.include_router(delivery_pipeline_router)
    app.include_router(approvals_router)
    app.include_router(packs_router)
    app.include_router(role_administration_router)

    logger.info("kernel.bootstrap.complete")
    return app
