"""Synchronous experiment-run orchestrator (``P04-S01-M12-T13``, FR-070) —
the first real production caller of the already-tested
:class:`~ai_os_kernel.sdk_adapters.experiment_run_recorder_adapter.
SqlExperimentRunRecorder`, backing ``POST /api/v1/experiments/{id}/run``.

**What this closes.** ``evaluation.experiment_runs`` had a real writer
since ``P04-S03-M34-T02`` but *no production caller* — the "proven but
idle" gap risk register R-018 tracks. A run row cannot be a placeholder:
``experiment_runs`` marks ``workflow_id`` (a real FK to
``workflow_instances``), ``resolved_model_id`` and ``served_from_cache``
all ``NOT NULL`` (``evaluation_schema.py``), so a row can only be written
for a workflow that has *genuinely been launched and run*. Materialising
``experiment_runs`` is therefore an orchestrator that actually triggers
Workflow Engine runs, not a bare writer. This is the product-owner-chosen
**synchronous** slice: each variant x replicate is created, started and
run to completion in-request, then recorded — appropriate because
experiments are human-defined and rare (the same reasoning
``GET /experiments`` is unpaginated on). The schema is unchanged, so a
later async submission model (worker-loop-driven + completion hook) is a
drop-in swap.

**Variant -> invocation mapping (this slice's convention).** ``overview.md``
§7 states the model is the only legitimate experiment variable (sampling
parameters cannot vary; prompts are held byte-identical), which is exactly
why ``experiment_runs`` carries a single ``model_alias``/``resolved_model_id``
per row. So this slice runs experiments whose *only* varied dimension is
``model_alias``: each declared model alias becomes one variant, resolved to a
real model id through the Kernel's own :class:`~ai_os_kernel.llm_gateway.
router.Router` (ADR-0002: callers name aliases, the platform resolves
them). A multi-dimensional ``variables`` map (valid at *definition* time
per ``P04-S01-M12-T12``) is rejected *here* with a clear error — genuine
multi-factor experiments are later work, not silently mis-run.

**Model pinning is real (``P04-S01-M12-T15``).** Each variant's runs are
executed against a run-time copy of the workflow definition with *every*
agent step's ``model_alias`` overridden to the variant's model
(:func:`pin_definition_to_model`) — ``overview.md`` §5 step 5, "each run
uses the LLM Gateway with the pinned model." This works because every
real agent reads its model from ``inputs['modelAlias']``, which the step
executor forwards from ``step.model_alias``; overriding that field is
what genuinely makes the run use the variant's model, so the
``resolved_model_id`` recorded is the model the run actually used, not
merely a declared intent. The catalog definition is never mutated.

**One honest limitation, disclosed not hidden.** ``served_from_cache`` is
``False`` by construction: ``overview.md`` §7 requires response caching
disabled for experiment runs, so a real run is never cache-served.
Separately, *completing* a run against a real provider still needs a real
model credential — inherent to calling a real model, not a gap this
orchestrator can close; a keyless environment proves the full loop with a
fake/NoOp executor (as the tests do), never against a live provider.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ai_os_kernel.evaluation_engine.experiment_repository import SqlExperimentRepository
from ai_os_kernel.llm_gateway.router import Router
from ai_os_kernel.sdk_adapters.experiment_run_recorder_adapter import SqlExperimentRunRecorder
from ai_os_kernel.workflow_engine.advance_runner import WorkflowAdvanceRunner
from ai_os_kernel.workflow_engine.definition_catalog import WorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.models import StepType, WorkflowDefinition, WorkflowStep
from ai_os_kernel.workflow_engine.repository import WorkflowInstanceRepository

# overview.md §7: the model is the only legitimate experiment variable, so
# this slice runs experiments varying exactly this one dimension. The key
# is `model_alias` — the convention P04-S01-M12-T12's own create path
# already established, and the exact name of the `experiment_runs` column
# each value lands in.
_MODEL_DIMENSION = "model_alias"

# Lifecycle values written to experiments.status as a run progresses. §6
# gives status no closed value list (no CHECK constraint), so these are
# the orchestrator's own honest vocabulary, mirroring "defined" (the
# create-time value experiment_repository sets).
_STATUS_RUNNING = "running"
_STATUS_COMPLETE = "complete"

# run_to_completion bounds — a run of a human-defined benchmark workflow,
# not the shared multi-instance worker loop, so a generous per-run budget.
_WORKER_ID = "experiment-run-orchestrator"
_LEASE_DURATION_SECONDS = 60
_MAX_ITERATIONS = 100

# §7 again: response caching is disabled for experiment runs, so a real
# run is never cache-served. Recorded as a genuine fact, not a guess.
_SERVED_FROM_CACHE = False


class ExperimentNotFoundError(Exception):
    """``POST /experiments/{id}/run`` named an ``experiment_id`` no real
    ``evaluation.experiments`` row matches — reported before any run."""


class ExperimentNotRunnableError(ValueError):
    """A real experiment definition cannot be run by this slice — its
    ``variables`` do not vary exactly the one ``model`` dimension this
    synchronous slice supports, or its referenced workflow definition
    could not be resolved. Carries a clear, caller-fixable message."""


class ExperimentRunSummary(BaseModel):
    """What ``POST /experiments/{id}/run`` returns — the experiment's new
    status plus the real ``run_id``s written, one per variant x replicate."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    status: str
    run_ids: list[str]
    variant_count: int
    runs_per_variant: int


def _pin_step_to_model(step: WorkflowStep, model_alias: str) -> WorkflowStep:
    """Return a copy of ``step`` pinned to ``model_alias``: an agent step
    gets its ``model_alias`` overridden; a step with nested branches
    (``parallel_steps``) has each branch pinned recursively; anything else
    is returned unchanged. ``WorkflowStep`` validation forbids
    ``model_alias`` on non-agent steps, so only agent steps (top-level or
    nested) are ever touched."""
    if step.type is StepType.AGENT:
        return step.model_copy(update={"model_alias": model_alias})
    if step.parallel_steps is not None:
        return step.model_copy(
            update={
                "parallel_steps": [_pin_step_to_model(b, model_alias) for b in step.parallel_steps]
            }
        )
    return step


def pin_definition_to_model(definition: WorkflowDefinition, model_alias: str) -> WorkflowDefinition:
    """A copy of ``definition`` with every agent step (nested branches
    included) pinned to ``model_alias`` — ``overview.md`` §5 step 5, "each
    run uses the LLM Gateway with the pinned model." Every real agent
    reads its model from ``inputs['modelAlias']``, which the step executor
    forwards from ``step.model_alias`` (``PromptedAgent`` and every SE-pack
    agent's ``_REQUIRED_INVOCATION_FIELDS``), so overriding the step field
    is what genuinely makes the run use the variant's model. The catalog
    row is never mutated: the pin is a run-time condition applied to the
    in-memory definition the run executes (ADR-0022, pinned conditions),
    not a new registered definition."""
    return definition.model_copy(
        update={"steps": [_pin_step_to_model(step, model_alias) for step in definition.steps]}
    )


def expand_model_variants(variables: dict[str, list[str]]) -> list[tuple[str, str]]:
    """The ``(variant_key, model_alias)`` pairs a model-varying experiment
    yields — one per declared alias, in declared order. Raises
    :class:`ExperimentNotRunnableError` if ``variables`` does not vary
    exactly the ``model`` dimension (see this module's docstring for why
    multi-dimensional maps are out of this slice's scope)."""
    if set(variables) != {_MODEL_DIMENSION}:
        raise ExperimentNotRunnableError(
            f"this experiment-run slice varies exactly the {_MODEL_DIMENSION!r} dimension; "
            f"got varied dimensions {sorted(variables)} — multi-factor runs are later work"
        )
    aliases = variables[_MODEL_DIMENSION]
    return [(f"{_MODEL_DIMENSION}={alias}", alias) for alias in aliases]


class ExperimentRunOrchestrator:
    """Runs a defined experiment synchronously: for each variant x
    replicate, create + start + run a real workflow to completion, then
    record the ``evaluation.experiment_runs`` row. Collaborators are the
    same real classes the worker loop and gateway already use — injected
    so a test can supply a NoOp step executor and a static router against
    real Postgres."""

    def __init__(
        self,
        *,
        experiment_repository: SqlExperimentRepository,
        definition_catalog: WorkflowDefinitionCatalog,
        instance_repository: WorkflowInstanceRepository,
        advance_runner: WorkflowAdvanceRunner,
        router: Router,
        run_recorder: SqlExperimentRunRecorder,
    ) -> None:
        self._experiment_repository = experiment_repository
        self._definition_catalog = definition_catalog
        self._instance_repository = instance_repository
        self._advance_runner = advance_runner
        self._router = router
        self._run_recorder = run_recorder

    async def run(self, experiment_id: str, *, principal_id: str) -> ExperimentRunSummary:
        experiment = await self._experiment_repository.get(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(f"no experiment {experiment_id!r} to run")

        variants = expand_model_variants(experiment.variables)
        definition = await self._definition_catalog.get(
            definition_id=experiment.definition_id, version=experiment.definition_version
        )
        if definition is None:
            raise ExperimentNotRunnableError(
                f"experiment {experiment_id!r} references workflow definition "
                f"{experiment.definition_id!r} version {experiment.definition_version!r}, "
                "which no longer resolves"
            )

        # Resolve every alias up front — an unroutable one (LLMProviderError)
        # should fail the whole run before any workflow instance is created,
        # never leave a half-run experiment behind.
        resolved_by_alias = {alias: self._router.resolve(alias).model_id for _, alias in variants}

        await self._experiment_repository.update_status(experiment_id, _STATUS_RUNNING)

        run_ids: list[str] = []
        for variant_key, model_alias in variants:
            # Pin every agent step of this variant's runs to the variant's
            # model (overview.md §5 step 5) — a run-time copy, the catalog
            # definition is never mutated.
            pinned_definition = pin_definition_to_model(definition, model_alias)
            for replicate_index in range(experiment.runs_per_variant):
                instance = await self._instance_repository.create(
                    definition_id=experiment.definition_id,
                    definition_version=experiment.definition_version,
                    inputs=dict(experiment.pinned_conditions),
                    principal_id=principal_id,
                )
                await self._instance_repository.transition_to_running(
                    workflow_id=instance.workflow_id,
                    reason=f"experiment {experiment_id} variant {variant_key} "
                    f"replicate {replicate_index}",
                )
                result = await self._advance_runner.run_to_completion(
                    workflow_id=instance.workflow_id,
                    definition=pinned_definition,
                    worker_id=_WORKER_ID,
                    lease_duration_seconds=_LEASE_DURATION_SECONDS,
                    max_iterations=_MAX_ITERATIONS,
                )
                run_id = await self._run_recorder.record(
                    experiment_id=experiment_id,
                    workflow_id=instance.workflow_id,
                    variant_key=variant_key,
                    model_alias=model_alias,
                    resolved_model_id=resolved_by_alias[model_alias],
                    replicate_index=replicate_index,
                    served_from_cache=_SERVED_FROM_CACHE,
                    status=result.outcome.value,
                )
                run_ids.append(run_id)

        await self._experiment_repository.update_status(experiment_id, _STATUS_COMPLETE)
        return ExperimentRunSummary(
            experiment_id=experiment_id,
            status=_STATUS_COMPLETE,
            run_ids=run_ids,
            variant_count=len(variants),
            runs_per_variant=experiment.runs_per_variant,
        )
