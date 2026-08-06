"""Errors raised by the Workflow Engine's definition loading, input
validation, and instance creation."""

from __future__ import annotations

from typing import Any


class WorkflowDefinitionError(Exception):
    """A workflow definition file could not be loaded or is invalid.

    Raised with a clear, specific message — never a bare stack trace —
    so an invalid definition fails loudly and diagnosably.
    """


class WorkflowInputValidationError(Exception):
    """The inputs supplied to start a workflow do not satisfy the
    definition's declared ``inputs`` JSON Schema, or a required starting
    value (e.g. the principal) is missing."""


class WorkflowInstanceCreationError(Exception):
    """A workflow instance could not be created.

    Wraps a persistence-layer failure (e.g. a constraint violation) with
    a clear message; the underlying exception is chained via ``from``.
    """


class WorkflowDefinitionRegistrationError(Exception):
    """A workflow definition could not be registered into
    ``catalog.workflow_definitions``.

    Wraps a persistence-layer failure with a clear message; the
    underlying exception is chained via ``from``.
    """


class WorkflowInvalidTransitionError(Exception):
    """A requested state transition is not allowed.

    Raised when the target instance does not exist, or exists but is
    not in the status the requested transition requires — never a bare
    constraint-violation stack trace.
    """


class AgentOutputValidationError(Exception):
    """An agent's returned outputs do not satisfy its declared
    ``output_schema`` (agent_architecture.md: "Output Validator —
    validates against output_model before returning")."""


class PromptedAgentInputError(Exception):
    """:class:`~ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent`
    was invoked without one of its three required invocation fields —
    ``promptId``, ``promptVersion``, ``modelAlias`` (agent_architecture.md:
    "those are the values the agent uses at step 4 ... constructed into
    its ``AgentRequest``"). Unlike a step's own declaration of these
    fields (validated at workflow-definition load time by
    :class:`~ai_os_kernel.workflow_engine.models.WorkflowStep`), this
    fires at invocation time against whatever ``inputs`` dict this
    agent actually received — the two checks are independent, since a
    step declaring all three does not, by itself, guarantee the
    registry resolves ``agentId`` to *this* agent."""


class ToolOutputValidationError(Exception):
    """A tool's returned outputs do not satisfy its declared
    ``output_schema`` (manifest.schema.json ``tools[].outputSchema``)."""


class DecisionConditionError(Exception):
    """A ``decision`` step's declared ``condition`` could not be
    genuinely evaluated — its ``sourceStepId`` has not executed yet (no
    matching :class:`~ai_os_kernel.workflow_engine.step_record.
    WorkflowStepRecord` exists), or that step's own recorded ``outputs``
    does not contain the declared ``field``. A structural/configuration
    problem (P02-S01-M05-T09): the identical call against the identical,
    still-missing state reproduces exactly, never retriable."""


class ParallelStepFailedError(Exception):
    """A ``parallel`` step's real join policy was not satisfied
    (``P02-S01-M05-T10``): every branch genuinely ran concurrently
    (:class:`~ai_os_kernel.workflow_engine.step_executor.
    ParallelStepExecutor`), but the outcome does not satisfy
    ``joinPolicy`` — ``all`` and at least one branch failed, or ``any``
    and every branch failed. (``collect`` never raises this; it reports
    every branch's own real outcome, failures included, as a successful
    result.) ``results`` carries each branch's own real, structured
    outcome (``branchId``/``status``/``outputs``/``error``) for whoever
    catches this — never re-parsed out of the message string."""

    def __init__(self, message: str, *, results: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.results = results


class SubWorkflowFailedError(Exception):
    """A ``sub_workflow`` step (:class:`~ai_os_kernel.workflow_engine.
    step_executor.SubWorkflowStepExecutor`) could not genuinely be
    satisfied — either its declared ``subWorkflowId`` has no matching
    entry in the executor's own composition-level ``definitions``
    mapping (a configuration problem, the identical shape
    :class:`DecisionConditionError` already covers for an unresolvable
    reference), or the real child ``WorkflowInstance`` it created and
    ran to completion did not reach
    :attr:`~ai_os_kernel.workflow_engine.advance_runner.
    WorkflowRunOutcome.COMPLETED` (a genuine runtime failure of the
    invoked child). No type split for the same reason
    ``AgentRegistryError``/``ToolRegistryError`` already document: two
    distinct real causes, one class, a clear message per site."""


class HumanApprovalPendingError(Exception):
    """A ``human_approval`` step
    (:class:`~ai_os_kernel.workflow_engine.human_approval.
    HumanApprovalStepExecutor`) has a real, persisted ``approvals`` row
    that is still ``pending`` — genuinely not yet decided, not a
    failure. Caught specially by
    :meth:`~ai_os_kernel.workflow_engine.service.WorkflowInstanceService.advance`
    (before its own generic exception handler) to transition the
    instance to ``waiting_for_human`` instead of recording a failed
    attempt — see that method's own docstring addendum. **Never raised
    on a timeout**: nothing in this codebase ever converts an elapsed
    ``timeout``/``expires_at`` into an implicit approval — R-001
    (`risk_register.md`) is a permanent, non-negotiable rule, not a
    default this exception's own absence of a case for it left open by
    oversight."""


class HumanApprovalRejectedError(Exception):
    """A ``human_approval`` step's real, persisted decision was
    ``rejected`` — a genuine step failure (human_approval_points.md
    §5: "Reject → Workflow follows the rejection path (may terminate
    or compensate)"; compensation is not built, so this halts the
    pipeline through the same, existing failure boundary
    :class:`AgentOutputValidationError` already uses — "terminate," not
    a new mechanism)."""


class ApprovalNotPendingError(Exception):
    """A real decision was attempted against an ``approvals`` row that
    is not (or no longer) ``pending`` — already decided, or genuinely
    absent. Guards :meth:`~ai_os_kernel.workflow_engine.human_approval.
    SqlApprovalRepository.decide` against a double decision (two real,
    concurrent decide attempts) the identical way every other guarded
    ``UPDATE ... WHERE`` in this codebase already guards against a
    stale caller — never a silent overwrite of an already-recorded,
    attributable decision."""


class ToolSandboxRequiredError(Exception):
    """A tool declares ``trust_tier = tier1_sandboxed`` but is not
    genuinely backed by a real :class:`~ai_os_kernel.sandbox.executor.
    SandboxExecutor` (:class:`~ai_os_kernel.workflow_engine.tool.
    SandboxBackedTool`, ADR-0016) — it cannot be safely dispatched. A
    ``tier2_trusted`` tool, or a ``tier1_sandboxed`` tool that genuinely
    exposes a working sandbox, both run through this executor; only a
    ``tier1_sandboxed`` tool making an unsubstantiated claim is
    refused."""


class AgentNotRegisteredError(Exception):
    """A step declared an ``agentId`` that no
    :class:`~ai_os_kernel.workflow_engine.registry.AgentRegistry`
    implementation has a registered :class:`~ai_os_kernel.workflow_engine.
    agent.Agent` instance for."""


class ToolNotRegisteredError(Exception):
    """A step declared a ``toolId`` that no
    :class:`~ai_os_kernel.workflow_engine.registry.ToolRegistry`
    implementation has a registered :class:`~ai_os_kernel.workflow_engine.
    tool.Tool` instance for."""


class AgentRegistryError(Exception):
    """An :class:`~ai_os_kernel.workflow_engine.registry.AgentRegistry`
    lookup failed for a reason other than "no such id" — a
    persistence-layer failure (e.g. a connection error), a loaded
    entrypoint that does not satisfy the
    :class:`~ai_os_kernel.workflow_engine.agent.Agent` Protocol, or one
    that declares a ``required_permissions`` capability this registry
    was not itself given a real backing object for. A missing id is
    :class:`AgentNotRegisteredError`, not this; a malformed or
    unimportable entrypoint string is :class:`EntrypointLoadError`, not
    this.

    ``retriable`` (added 2026-07-31, resolving the split deliberately
    left undecided two steps ago) follows the identical per-instance
    self-declaration convention :class:`~ai_os_kernel.llm_gateway.
    errors.LLMProviderError` already established — a constructor
    parameter each real raise site sets explicitly, not a fixed value,
    since this one exception type genuinely covers causes with
    different natures. **The investigation found a real, structural way
    to tell them apart after all** (the "no structural way to
    distinguish" framing from two steps ago undersold it): each raise
    site in :mod:`~ai_os_kernel.workflow_engine.registry` already knows
    exactly which real cause it represents — no ambiguity ever reaches
    a caller, because each ``raise`` statement is written at the one
    place that already has the answer. Splitting into separate
    exception *classes* was considered and rejected: nothing in this
    codebase catches ``AgentRegistryError``/``ToolRegistryError`` by
    anything narrower than their own type today (only the generic
    ``except Exception`` boundary in
    :meth:`~ai_os_kernel.workflow_engine.service.WorkflowInstanceService.advance`,
    which reads the generic ``retriable`` attribute, never a type), so
    a type split would add real code with no real consumer to justify
    it — the identical reasoning `error_handling_retry.md` already
    applies against inventing a severity taxonomy nothing documents a
    need for. Defaults ``False`` (the *opposite* default from
    ``LLMProviderError``, deliberately — three of this exception's four
    real causes are structural/permanent, only one is genuinely
    transient) — see each raise site's own comment for which case
    overrides it to ``True``."""

    def __init__(self, message: str, *, retriable: bool = False) -> None:
        super().__init__(message)
        self.retriable = retriable


class ToolRegistryError(Exception):
    """A :class:`~ai_os_kernel.workflow_engine.registry.ToolRegistry`
    lookup failed for a reason other than "no such id" — a
    persistence-layer failure (e.g. a connection error), a loaded
    entrypoint that does not satisfy the
    :class:`~ai_os_kernel.workflow_engine.tool.Tool` Protocol, one whose
    own declared ``trust_tier`` disagrees with what ``catalog.tools``
    records for it, or one that declares a ``required_permissions``
    capability this registry was not itself given a real backing object
    for. A missing id is :class:`ToolNotRegisteredError`, not this; a
    malformed or unimportable entrypoint string is
    :class:`EntrypointLoadError`, not this.

    ``retriable`` (added 2026-07-31) is the identical per-instance
    self-declaration :class:`AgentRegistryError` now carries — see that
    class's own docstring for the full reasoning (a real, structural way
    to tell this exception's own distinct real causes apart, found by
    investigation, not left undecided; no type split, since nothing
    catches this type any narrower than itself today). Defaults
    ``False``; the one genuinely transient raise site (a persistence-
    layer failure) overrides it to ``True``."""

    def __init__(self, message: str, *, retriable: bool = False) -> None:
        super().__init__(message)
        self.retriable = retriable


class EntrypointLoadError(Exception):
    """An ``entrypoint`` string
    (:class:`~ai_os_kernel.workflow_engine.entrypoint_loader.
    EntrypointLoader`) could not be resolved to a constructed object —
    a malformed string, an unimportable module, a missing attribute, a
    name that is not a class, or a constructor that raised. The
    underlying exception (when there is one) is chained via ``from``.
    """


class PackNotActivatedError(Exception):
    """A resolved agent/tool's declared ``pack_id`` has no corresponding
    ``catalog.packs`` row, or that row's ``state``
    (:class:`~ai_os_kernel.workflow_engine.pack_state.PackState`) is not
    ``activated`` (capability_manager.md §4: "components available to
    the Workflow Engine" only once ``activated``). Raised before an
    entrypoint is ever loaded — an agent/tool whose id and entrypoint
    are both otherwise perfectly valid is still refused while its pack
    is not active."""


class QualityGateFailedError(Exception):
    """A blocking ``quality_gate`` step (:class:`~ai_os_kernel.
    workflow_engine.quality_gate.QualityGateStepExecutor`) genuinely
    failed — its configured source step either has no persisted output
    yet or reported a non-passing result. Raised, never silently
    swallowed, so it propagates out of :meth:`WorkflowInstanceService.advance`
    exactly the way :class:`AgentOutputValidationError`/
    :class:`ToolOutputValidationError` already do, reaching
    :meth:`WorkflowAdvanceRunner.run_to_completion` at the same existing
    failure boundary — not new orchestration logic.

    ``gate_step_id`` (added 2026-07-30, the bounded-retry step) is the
    failing gate's own declared step id — structured, not parsed back
    out of the message string. ``WorkflowInstanceService.advance``
    (added 2026-07-30, the general-step-retry step) additionally
    attaches the identical value to *every* exception it catches, as a
    generic ``step_id`` attribute — so this class's own ``gate_step_id``
    is now redundant with that (kept only so nothing that already reads
    it breaks), and ``run_to_completion`` reads the generic ``step_id``
    for every exception type uniformly, gate or not.

    ``retriable = True`` (added 2026-07-30, the general-step-retry step)
    is this class's own self-declaration, following the identical
    ``LLMProviderError.retriable`` convention
    (:mod:`ai_os_kernel.llm_gateway.errors`) that already exists for
    exactly this purpose: ``run_to_completion`` retries an exception
    only when it declares itself ``retriable`` — see that class's own
    docstring, and :mod:`ai_os_kernel.workflow_engine.advance_runner`'s
    module docstring, for the full retriable-vs-not category reasoning.
    A quality-gate failure is always retriable *by this codebase's own
    design*: the retry re-runs the step that *produces* the artifact
    the gate evaluates (e.g. ``build``, never the gate's own source
    step alone), which is genuine, real "corrective work" in the sense
    error_handling_retry.md §3's ``quality`` category requires — not a
    blind re-evaluation of the identical, already-failed artifact.

    When no retry is configured for this gate's own step id (the
    default, every caller except ``se.delivery_pipeline``), this still
    halts the run with ``WorkflowRunOutcome.FAILED`` exactly as before
    — carrying these attributes is additive, not a behavior change on
    its own.

    ``results`` (added ``P02-S06-M15-T08``, concurrent multi-gate
    evaluation) optionally carries each declared gate's own real,
    structured outcome — the identical "structured, not re-parsed from
    the message" shape :class:`ParallelStepFailedError.results` already
    establishes. ``None`` (the default) for every single-gate failure
    from before this step — genuinely unaffected."""

    def __init__(
        self, message: str, *, gate_step_id: str, results: list[dict[str, Any]] | None = None
    ) -> None:
        super().__init__(message)
        self.gate_step_id = gate_step_id
        self.retriable = True
        self.results = results


class WorkflowLeaseUnavailableError(Exception):
    """A workflow instance's lease could not be acquired or released.

    Raised when the instance does not exist, is not ``running``, is
    already leased and not yet expired, is currently being claimed by
    another worker (the ``SELECT ... FOR UPDATE SKIP LOCKED`` row was
    unavailable), on release when the caller does not hold the lease
    it is trying to release, or when a persistence failure occurs
    while reaping expired leases.
    """


class GateResultRecordingError(Exception):
    """An ``evaluation.gate_results`` row could not be recorded.

    Wraps a persistence-layer failure (e.g. a constraint violation, a
    missing ``workflow_id`` row for the real foreign key) with a clear
    message; the underlying exception is chained via ``from`` — the
    identical shape :class:`~ai_os_kernel.llm_gateway.errors.
    LLMCallRecordingError` already established for its own, analogous
    writer.
    """


class RunManifestRecordingError(Exception):
    """An ``evaluation.run_manifests`` row could not be recorded.

    The identical "wrap a persistence-layer failure with a clear
    message, chain via ``from``" shape
    :class:`GateResultRecordingError` already establishes for its own,
    analogous writer.
    """
