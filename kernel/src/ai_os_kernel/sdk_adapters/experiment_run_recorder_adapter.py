"""The Kernel's own real implementation of the Benchmarking Pack's
`ExperimentRunRecorder` Protocol
(`ai_os_pack_benchmarking.replicate_management`, `P04-S03-M34-T02`).

**The identical "Kernel implements a Protocol this pack only declares"
shape this package's own docstring already establishes for the SDK's
own Protocols, applied here to a second pack-defined Protocol** — the
first being `WorkflowDefinitionExistenceCheck`
(`workflow_definition_existence_adapter.py`, `P04-S03-M34-T01`). The
Benchmarking Pack's own source may not import `ai_os_kernel` at all
(`platform_sdk.md` §9 item 7), so writing a real `evaluation.experiment_runs`
row — which requires a real, already-existing `workflow_id` (a `NOT
NULL` foreign key to `workflow_instances`) — cannot happen there.

**No real production caller yet** — `P04-S03-M34-T02`'s own scope is
proving `record()` genuinely writes a correct row, end to end against
a real Postgres, given a real, already-existing `workflow_id` supplied
by its caller (the identical "caller supplies real paths" convention
`SqlGateResultRecorder`/`SqlRunManifestRecorder` already establish).
Wiring this into a real experiment-submission path — which must first
genuinely create that `workflow_instances` row by actually triggering
a run through the Workflow Engine (`overview.md` §5 step 4: "the pack
submits runs... it does not orchestrate them itself") — is later,
separate work, the identical "build real, wire later" precedent
already established for the Gate Registry and the Metrics Collector.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine
from ulid import ULID

from ai_os_kernel.persistence.evaluation_schema import experiment_runs


def new_experiment_run_id() -> str:
    """Prefixed ULID, the identical `data_model.md` §2 scheme every
    other workflow-state/evaluation id in this codebase already uses
    (`wf_`/`stp_`/`gr_`/`rm_`/`met_`) — not added to
    `ai_os_kernel.workflow_engine.ids` since this recorder has no real
    caller in that package yet (see this module's own docstring)."""
    return f"xr_{ULID()}"


class ExperimentRunRecordingError(Exception):
    """An `evaluation.experiment_runs` row could not be recorded —
    wraps a persistence-layer failure (e.g. a constraint violation, a
    missing `workflow_id`/`experiment_id` row for the real foreign
    keys) with a clear message; the underlying exception is chained
    via `from`, the identical shape
    `~ai_os_kernel.workflow_engine.gate_result_recorder.GateResultRecordingError`
    already establishes for its own, analogous writer."""


class SqlExperimentRunRecorder:
    """The only implementation of the Benchmarking Pack's
    `ExperimentRunRecorder` Protocol at this stage: SQLAlchemy 2.0 Core
    against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

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
        run_id = new_experiment_run_id()
        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    sa.insert(experiment_runs).values(
                        run_id=run_id,
                        experiment_id=experiment_id,
                        workflow_id=workflow_id,
                        variant_key=variant_key,
                        model_alias=model_alias,
                        resolved_model_id=resolved_model_id,
                        replicate_index=replicate_index,
                        served_from_cache=served_from_cache,
                        status=status,
                    )
                )
        except sa.exc.SQLAlchemyError as exc:
            raise ExperimentRunRecordingError(
                f"failed to record experiment run for experiment '{experiment_id}' "
                f"workflow '{workflow_id}' variant '{variant_key}' "
                f"replicate {replicate_index}: {exc}"
            ) from exc
        return run_id
