"""Replicate management (`P04-S03-M34-T02`, FR-072) — expanding one
validated `ExperimentVariant` (`experiment_definition.py`) into its own
real, numbered set of replicates, and recording each one.

**`runs_per_variant >= 3` is already a real, enforced precondition,
not re-decided here.** `validate_experiment_spec` already rejects any
`ExperimentDefinition` whose own `runs_per_variant` is below 3
(`overview.md` §5 step 3, "replicate count (default >= 3)") before an
`ExperimentDefinition` — the only real, validated source of a
`runs_per_variant` value — can ever exist. `plan_replicates` re-checks
it defensively anyway (`ReplicateValidationError`), since it is a real,
independently callable function with its own contract, not merely an
internal helper only ever reached through that one validated path.

**"Recorded" needs a real, already-existing `workflow_id` — this
module cannot create one.** `evaluation.experiment_runs.workflow_id`
is a `NOT NULL` foreign key to a real `workflow_instances` row
(`overview.md` §5 step 4: "the pack submits runs to the Workflow
Engine — it does not orchestrate them itself"; submission is real,
separate, later work). `ExperimentRunRecorder` below is therefore a
Protocol this pack declares but cannot implement — the same shape
`experiment_definition.py`'s own `WorkflowDefinitionExistenceCheck`
already establishes — with the real, Postgres-backed implementation
living in `ai_os_kernel.sdk_adapters.experiment_run_recorder_adapter`
instead, since this pack's own source may never import `ai_os_kernel`
(`platform_sdk.md` §9 item 7). No real submission path calls it yet —
the identical "build real, wire later" precedent already established
for `experiment_definition.py`'s own existence check, the Gate
Registry, and the Metrics Collector.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from ai_os_pack_benchmarking.experiment_definition import ExperimentVariant

_MIN_RUNS_PER_VARIANT = 3


class ReplicateValidationError(ValueError):
    """`runs_per_variant` was below the real, decided minimum
    (`overview.md` §5 step 3) — the identical defensive re-check this
    module's own docstring explains."""


class ReplicatePlan(BaseModel):
    """One real, numbered replicate of a declared variant — not yet
    tied to any real workflow run (see this module's own docstring for
    why: submission is real, separate, later work)."""

    variant_key: str
    model_alias: str
    replicate_index: int


class ExperimentRunRecorder(Protocol):
    """Persists one real, already-executed (or already-submitted)
    replicate as a real `evaluation.experiment_runs` row — the seam a
    fake implementation substitutes in unit tests (ADR-0004:
    interface-driven, configuration over code). See this module's own
    docstring for why the real implementation cannot live in this
    pack."""

    async def record(
        self,
        *,
        experiment_id: str,
        workflow_id: str,
        variant_key: str,
        model_alias: str,
        replicate_index: int,
        resolved_model_id: str,
        served_from_cache: bool,
        status: str,
    ) -> str:
        """Returns the new row's own real `run_id`. Takes `replicate`'s
        own fields individually, not a `ReplicatePlan` object — this
        Protocol crosses into the Kernel (see this module's own
        docstring), which may never import this pack's own types; a
        plain, primitive-only boundary keeps that true in both
        directions, not just the already-enforced one."""
        ...


def plan_replicates(variant: ExperimentVariant, *, runs_per_variant: int) -> list[ReplicatePlan]:
    """Expands `variant` into `runs_per_variant` real, numbered
    `ReplicatePlan`s (`replicate_index` `0` through `runs_per_variant - 1`)
    — pure, deterministic, no I/O."""
    if runs_per_variant < _MIN_RUNS_PER_VARIANT:
        raise ReplicateValidationError(
            f"runs_per_variant must be >= {_MIN_RUNS_PER_VARIANT} (replicate count, "
            f"overview.md §5 step 3) — got {runs_per_variant}"
        )

    return [
        ReplicatePlan(
            variant_key=variant.variant_key,
            model_alias=variant.model_alias,
            replicate_index=replicate_index,
        )
        for replicate_index in range(runs_per_variant)
    ]
