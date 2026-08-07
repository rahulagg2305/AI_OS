"""Experiment definition and validation (`P04-S03-M34-T01`, FR-070) —
this pack's own first real code.

Given a caller-supplied `ExperimentSpec` (this ticket's own "experiment
spec" Input), `validate_experiment_spec` checks it against
`docs/06_capability_packs/benchmarking/overview.md` §7's own real,
already-decided Key Design Rules and returns a real
`ExperimentDefinition` (this ticket's own "validated definition"
Output) — never invents a rule not already written there.

**Real checks performed, each traceable to a specific §7 rule:**
- `runs_per_variant >= 3` — "replicate count (default >= 3)" (§5 step 3).
- At least 2 variants — an experiment that does not vary anything is
  not a comparison, the whole stated purpose of this pack (§1/§2).
- No duplicate `variant_key`s — each real run must be attributable to
  exactly one declared variant.
- No sampling parameter (`temperature`/`top_p`/`top_k`) declared as a
  variable — "Sampling parameters are not experiment variables.
  Current models reject them, so they are absent from the Gateway
  contract and cannot be varied."
- The pinned `(definition_id, definition_version)` genuinely exists —
  via an injected `WorkflowDefinitionExistenceCheck`, never a direct
  database call from this pack's own source (forbidden — no pack may
  import `ai_os_kernel`, `platform_sdk.md` §9 item 7). The real,
  Postgres-backed implementation lives in
  `ai_os_kernel.sdk_adapters.workflow_definition_existence_adapter`,
  wrapping the already-real `SqlWorkflowDefinitionCatalog` — the
  identical "Kernel implements a Protocol this pack only declares"
  shape `ai_os_kernel.sdk_adapters`'s own package docstring already
  establishes for the SDK's own Protocols, applied here to a
  pack-defined one instead.

**Not validated here, and not this ticket's own scope:** "Prompts are
held byte-identical across models by default" (§7) — confirming two
prompt renders are byte-identical requires actually rendering them,
which requires the Prompt Engine this pack has no access to yet; a
required per-model adaptation would need to be *recorded* as its own
declared variable, a real, separate design this ticket's own narrow
`ExperimentVariant` shape does not yet carry a field for. Response
caching (disabled for experiment runs) is a real-time Gateway
enforcement, not a spec-time validation. Both are real, disclosed,
deferred scope, not silently skipped.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol

from pydantic import BaseModel, Field

_MIN_RUNS_PER_VARIANT = 3
_MIN_VARIANTS = 2

# Sampling parameters current models reject, per the overview's own
# §7 rule — the Gateway's own real LLMRequest contract has no field
# for any of these, so a spec declaring one as a variable can never be
# honoured.
_FORBIDDEN_VARIABLE_NAMES = frozenset({"temperature", "top_p", "top_k"})


class ExperimentValidationError(ValueError):
    """A caller-supplied `ExperimentSpec` failed one or more of
    `overview.md` §7's own real, decided rules — carries every failure
    found, not just the first, so a caller can fix all of them at once
    rather than iterating one error at a time."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


class ExperimentVariant(BaseModel):
    """One declared point of variation — most commonly a different
    model (`overview.md` §4's own "Experiment" definition: "deliberate
    variation... most commonly different LLMs")."""

    variant_key: str
    model_alias: str


class ExperimentSpec(BaseModel):
    """The raw, caller-supplied experiment spec — this ticket's own
    "Input." Not yet validated; `validate_experiment_spec` is the real
    validation boundary."""

    name: str
    description: str
    definition_id: str
    definition_version: str
    variants: list[ExperimentVariant]
    runs_per_variant: int
    variables: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    # Optional (`P04-S03-M34-T03`, FR-076) — `None` means "no ceiling
    # declared," the identical "absent means unenforced" shape every
    # other optional policy gate in this codebase already establishes
    # (e.g. `PerScopeBudgetEnforcer`'s own per-workflow ceiling, never
    # constructed for a caller that supplies no `workflow_id`).
    cost_ceiling_usd: Decimal | None = None


class ExperimentDefinition(BaseModel):
    """The real, validated definition — this ticket's own "Output."
    Column-for-column compatible with `evaluation.experiments`'s own
    real schema (`kernel/src/ai_os_kernel/persistence/evaluation_schema.py`),
    since persisting one is the natural next real step (a later
    ticket's own scope, not this one's)."""

    name: str
    description: str
    definition_id: str
    definition_version: str
    variants: list[ExperimentVariant]
    runs_per_variant: int
    variables: dict[str, Any]
    created_by: str
    cost_ceiling_usd: Decimal | None = None


class WorkflowDefinitionExistenceCheck(Protocol):
    """Whether a real `(definition_id, version)` pair genuinely exists
    — the seam a fake implementation substitutes in unit tests
    (ADR-0004: interface-driven, configuration over code). This pack's
    own source may not import `ai_os_kernel` at all (`platform_sdk.md`
    §9 item 7), so the real, Postgres-backed implementation lives in
    the Kernel instead — see this module's own docstring."""

    async def exists(self, *, definition_id: str, version: str) -> bool: ...


async def validate_experiment_spec(
    spec: ExperimentSpec, *, existence_check: WorkflowDefinitionExistenceCheck
) -> ExperimentDefinition:
    """Validates `spec` against every real rule this module's own
    docstring names, collecting every failure before raising — see
    `ExperimentValidationError`'s own docstring for why."""
    errors: list[str] = []

    if spec.runs_per_variant < _MIN_RUNS_PER_VARIANT:
        errors.append(
            f"runs_per_variant must be >= {_MIN_RUNS_PER_VARIANT} (replicate count, "
            f"overview.md §5 step 3) — got {spec.runs_per_variant}"
        )

    if len(spec.variants) < _MIN_VARIANTS:
        errors.append(
            f"an experiment must declare at least {_MIN_VARIANTS} variants to compare — "
            f"got {len(spec.variants)}"
        )

    seen_variant_keys: set[str] = set()
    duplicate_variant_keys: set[str] = set()
    for variant in spec.variants:
        if variant.variant_key in seen_variant_keys:
            duplicate_variant_keys.add(variant.variant_key)
        seen_variant_keys.add(variant.variant_key)
    if duplicate_variant_keys:
        errors.append(f"duplicate variant_key(s): {sorted(duplicate_variant_keys)}")

    forbidden_variables_declared = _FORBIDDEN_VARIABLE_NAMES & spec.variables.keys()
    if forbidden_variables_declared:
        errors.append(
            "sampling parameters are not experiment variables (overview.md §7) — "
            f"declared: {sorted(forbidden_variables_declared)}"
        )

    if not await existence_check.exists(
        definition_id=spec.definition_id, version=spec.definition_version
    ):
        errors.append(
            f"no workflow definition exists for definition_id={spec.definition_id!r}, "
            f"version={spec.definition_version!r} — an experiment cannot pin a workflow "
            "that does not exist"
        )

    if spec.cost_ceiling_usd is not None and spec.cost_ceiling_usd <= 0:
        errors.append(
            f"cost_ceiling_usd must be positive when declared — got {spec.cost_ceiling_usd}"
        )

    if errors:
        raise ExperimentValidationError(errors)

    return ExperimentDefinition(
        name=spec.name,
        description=spec.description,
        definition_id=spec.definition_id,
        definition_version=spec.definition_version,
        variants=spec.variants,
        cost_ceiling_usd=spec.cost_ceiling_usd,
        runs_per_variant=spec.runs_per_variant,
        variables=spec.variables,
        created_by=spec.created_by,
    )
