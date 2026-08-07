"""The Metrics Collector (`P04-S01-M12-T04`, FR-073) — this package's
first real code (`kernel/src/ai_os_kernel/evaluation_engine/` was,
until now, a docstring-only `__init__.py`).

Computes a small, real, honest slice of `evaluation_engine.md` §3's
four metric categories, sourced entirely from data this codebase
already, genuinely persists — no new instrumentation added anywhere:

- **Cost** (§3.1): `aios.workflow.total_tokens` /
  `aios.workflow.total_cost_usd`, read from `workflow_instances`'s own
  already-real, already-maintained aggregate columns (the LLM
  Gateway's own per-workflow budget enforcement, `llm_gateway.md` §9,
  keeps these current as a side effect of every real completion).
- **Performance** (§3.2): `aios.workflow.duration_seconds`, from
  `workflow_instances.completed_at - .created_at`.
- **Quality** (§3.3): `aios.workflow.gate_failures`, a real `COUNT`
  over `evaluation.gate_results` where `status != 'completed'` for
  this workflow.
- **Process** (§3.4): `aios.workflow.step_retries`, a real `COUNT` over
  `workflow_steps` where `attempt > 1` — each real retry genuinely
  inserts its own distinct row (`gate_result_recorder.py`'s own
  docstring already confirms this: "two real, distinct `workflow_steps`
  rows, one `failed`, one `completed`"), so this counts real retries,
  not merely steps.

**A real, disclosed, structural blocker, not silently worked around:
`evaluation.metrics.run_id` is a `NOT NULL` foreign key to
`experiment_runs`, and no `experiment`/`experiment_run` has ever been
created in production** — Module 34, the Benchmarking Pack that owns
experiment *definition* (`evaluation_engine.md` §5.1), is 0% built.
This means no ordinary `se.delivery_pipeline` run can get a real
`evaluation.metrics` row today, unlike `gate_results`/`run_manifests`
(both keyed by `workflow_id` alone, no experiment required). Design
fork resolved with the product owner: build the real writer now,
proven end to end against a real Postgres with a real, schema-valid,
test-seeded `experiments`/`experiment_runs` row — the identical
"build real, wire later" precedent this same module already
established for the Gate Registry, `gate_results`, and
`run_manifests` before any of their own real production callers
existed (`quality_gate_engine.py`'s own repeated "build the real
component before anything wires it in" language).

**Not composed into `WorkflowInstanceService`/`se.delivery_pipeline`
today — there is no real caller yet, not an oversight.**
`WorkflowInstance` carries no real `run_id` of its own to supply (only
a nullable `experiment_id`, an unrelated column with no `experiment_runs`
foreign key at all) — nothing in the current Workflow Engine composition
knows which `experiment_runs.run_id`, if any, a given workflow_id
belongs to. Wiring this in is real, separate, later work that waits on
Module 34 existing, exactly as this module's own `__init__.py` already
names as Stage D.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine
from ulid import ULID

from ai_os_kernel.persistence.evaluation_schema import gate_results, metrics
from ai_os_kernel.persistence.schema import workflow_instances, workflow_steps

_SOURCE_COMPONENT = "evaluation_engine.metrics_collector"

_METRIC_TOTAL_TOKENS = "aios.workflow.total_tokens"
_METRIC_TOTAL_COST_USD = "aios.workflow.total_cost_usd"
_METRIC_DURATION_SECONDS = "aios.workflow.duration_seconds"
_METRIC_GATE_FAILURES = "aios.workflow.gate_failures"
_METRIC_STEP_RETRIES = "aios.workflow.step_retries"


def new_metric_id() -> str:
    """Prefixed ULID, the identical `data_model.md` §2 scheme every
    other workflow-state/evaluation id in this codebase already uses
    (`wf_`/`stp_`/`gr_`/`rm_`) — not added to
    `ai_os_kernel.workflow_engine.ids` since this recorder has no real
    caller in that package yet (see this module's own docstring)."""
    return f"met_{ULID()}"


class MetricsCollectionError(Exception):
    """A completed run's own `evaluation.metrics` rows could not be
    recorded — wraps a persistence-layer failure (e.g. the real,
    documented `experiment_runs` foreign key this module's own
    docstring discloses) with a clear message; the underlying
    exception is chained via `from`, the identical shape
    `~ai_os_kernel.workflow_engine.gate_result_recorder.
    GateResultRecordingError` already establishes for its own,
    analogous writer."""


class MetricsCollector(Protocol):
    """Persistence boundary for collecting one completed run's own real
    metrics — the seam a fake implementation substitutes in unit tests
    (ADR-0004: interface-driven, configuration over code)."""

    async def collect(self, *, workflow_id: str, run_id: str) -> None: ...


class SqlMetricsCollector:
    """The only implementation of `MetricsCollector` at this stage:
    SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def collect(self, *, workflow_id: str, run_id: str) -> None:
        try:
            async with self._engine.begin() as connection:
                instance_row = (
                    await connection.execute(
                        sa.select(
                            workflow_instances.c.total_tokens,
                            workflow_instances.c.total_cost_usd,
                            workflow_instances.c.created_at,
                            workflow_instances.c.completed_at,
                        ).where(workflow_instances.c.workflow_id == workflow_id)
                    )
                ).one()

                gate_failure_count = (
                    await connection.execute(
                        sa.select(sa.func.count())
                        .select_from(gate_results)
                        .where(
                            gate_results.c.workflow_id == workflow_id,
                            gate_results.c.status != "completed",
                        )
                    )
                ).scalar_one()

                step_retry_count = (
                    await connection.execute(
                        sa.select(sa.func.count())
                        .select_from(workflow_steps)
                        .where(
                            workflow_steps.c.workflow_id == workflow_id,
                            workflow_steps.c.attempt > 1,
                        )
                    )
                ).scalar_one()

                recorded_at = instance_row.completed_at or datetime.now(UTC)
                duration_seconds = (
                    (instance_row.completed_at - instance_row.created_at).total_seconds()
                    if instance_row.completed_at is not None
                    else 0.0
                )

                rows: list[dict[str, Any]] = [
                    {
                        "metric_name": _METRIC_TOTAL_TOKENS,
                        "metric_value": instance_row.total_tokens,
                        "unit": "tokens",
                    },
                    {
                        "metric_name": _METRIC_TOTAL_COST_USD,
                        "metric_value": instance_row.total_cost_usd,
                        "unit": "usd",
                    },
                    {
                        "metric_name": _METRIC_DURATION_SECONDS,
                        "metric_value": duration_seconds,
                        "unit": "seconds",
                    },
                    {
                        "metric_name": _METRIC_GATE_FAILURES,
                        "metric_value": gate_failure_count,
                        "unit": "count",
                    },
                    {
                        "metric_name": _METRIC_STEP_RETRIES,
                        "metric_value": step_retry_count,
                        "unit": "count",
                    },
                ]
                await connection.execute(
                    sa.insert(metrics),
                    [
                        {
                            "metric_id": new_metric_id(),
                            "workflow_id": workflow_id,
                            "run_id": run_id,
                            "metric_name": row["metric_name"],
                            "metric_value": row["metric_value"],
                            "unit": row["unit"],
                            "source_component": _SOURCE_COMPONENT,
                            "recorded_at": recorded_at,
                        }
                        for row in rows
                    ],
                )
        except sa.exc.SQLAlchemyError as exc:
            raise MetricsCollectionError(
                f"failed to record metrics for workflow '{workflow_id}' run '{run_id}': {exc}"
            ) from exc
