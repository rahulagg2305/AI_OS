"""The per-run reader (``P04-S01-M12-T14``) behind
``GET /api/v1/experiments/{id}/runs`` — the raw ``evaluation.experiment_runs``
rows one experiment produced.

**Distinct from the Comparison Computer, deliberately.**
:class:`~ai_os_kernel.evaluation_engine.comparison_computer.SqlComparisonComputer`
*aggregates* runs into per-(variant, metric) mean/variance; nothing in
this codebase listed the individual run rows themselves until now. This
reader is that missing read — a plain ``SELECT`` over the rows
:class:`~ai_os_kernel.sdk_adapters.experiment_run_recorder_adapter.
SqlExperimentRunRecorder` writes, with no aggregation, no exclusion, and
no join. It lives in ``evaluation_engine`` (not alongside the recorder in
``sdk_adapters``) because, unlike the writer, it implements no
pack-declared Protocol — the identical Kernel-owned placement
:class:`~ai_os_kernel.evaluation_engine.experiment_repository.
SqlExperimentRepository` already uses for the ``experiments`` table's own
reads.
"""

from __future__ import annotations

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.evaluation_schema import experiment_runs


class ExperimentRunRecord(BaseModel):
    """One real, persisted ``evaluation.experiment_runs`` row — the read
    model ``GET /experiments/{id}/runs`` returns, column-for-column."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    experiment_id: str
    workflow_id: str
    variant_key: str
    model_alias: str
    resolved_model_id: str
    replicate_index: int
    served_from_cache: bool
    status: str


class SqlExperimentRunReader:
    """The only implementation at this stage: SQLAlchemy 2.0 Core against
    Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def list_for_experiment(self, experiment_id: str) -> list[ExperimentRunRecord]:
        """Every real run row for ``experiment_id``, ordered by
        ``variant_key`` then ``replicate_index`` — a stable, human-readable
        order grouping each variant's own replicates together. Deliberately
        unpaginated: one experiment's run set is bounded by its own
        (variants x runs_per_variant), a genuinely small, human-sized
        collection, the same reasoning ``GET /experiments`` itself uses."""
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(experiment_runs)
                        .where(experiment_runs.c.experiment_id == experiment_id)
                        .order_by(
                            experiment_runs.c.variant_key,
                            experiment_runs.c.replicate_index,
                        )
                    )
                )
                .mappings()
                .all()
            )
        return [ExperimentRunRecord.model_validate(dict(row)) for row in rows]
