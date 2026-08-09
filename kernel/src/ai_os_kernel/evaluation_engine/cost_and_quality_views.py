"""Cost and Quality Views (`P06-S03-M39-T03`, FR-094: "Show quality
gate trends and most frequent failures," FR-095: "Show token and cost
breakdown by model, workflow, agent, and pack").

**A new, general aggregation over already-real, already-populated
production data — not the experiment-scoped `EvaluationReportingInterface`
(`P04-S01-M12-T08`).** That interface answers "how did variant X do on
metric Y for experiment Z" — it requires a real `experiment_id`, and no
real experiment has ever been created in production (the Benchmarking
Pack, module 34, still has no `manifest.yaml`/submission path). FR-095's
own acceptance criterion — "Breakdown reconciles with
`evaluation.llm_calls`" — describes a different, more general query:
every real recorded LLM call, broken down by dimension, with no
experiment involved at all. Resolved via `AskUserQuestion`: build this
new, general query directly, rather than first building a real
experiment-submission path merely to unblock a narrower view.

**Real, disclosed scope limit: no genuine time-series trend.** Neither
`evaluation.llm_calls` nor `evaluation.gate_results` carries a
timestamp column (confirmed by reading `persistence/evaluation_schema.py`
directly) — FR-094's own "gate trends" is therefore built as a real,
honest *frequency* breakdown (which gates fail most often, and how
often), not a trend-over-time chart a missing column cannot support.
Adding a timestamp column is a real, disclosed, separate schema change,
not silently faked here with a placeholder.

**Four cost dimensions, not one flexible group-by.** FR-095 names all
four ("by model, workflow, agent, and pack") as things a real caller
needs to see — a single caller-chosen dimension would satisfy the
literal text with less real value. `pack` is derived via a real join to
`catalog.agents.pack_id` (the actual FK relationship), never a
string-split guess against `agent_id`'s own conventional
`"<pack_id>/<name>"` shape.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.catalog_schema import agents
from ai_os_kernel.persistence.evaluation_schema import gate_results, llm_calls


class CostBreakdownEntry(BaseModel):
    """One real dimension value's own aggregated cost — e.g. one real
    `model_id`, or one real `pack_id`, together with every real call
    this project has ever recorded against it."""

    dimension_value: str
    call_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: Decimal


class GateFailureSummaryEntry(BaseModel):
    """One real gate's own real failure count — FR-094's "most
    frequent failures," ordered by the caller (descending count)."""

    gate_id: str
    status: str
    count: int


class CostAndQualityReport(BaseModel):
    """The real, queryable artifact this ticket's own Output names:
    "Reconciling breakdowns" — every real cost dimension FR-095 names,
    plus FR-094's own real gate-failure frequency."""

    by_model: list[CostBreakdownEntry]
    by_workflow: list[CostBreakdownEntry]
    by_agent: list[CostBreakdownEntry]
    by_pack: list[CostBreakdownEntry]
    gate_failures: list[GateFailureSummaryEntry]


class CostAndQualityViews(Protocol):
    """The seam a fake implementation substitutes in unit tests
    (ADR-0004: interface-driven, configuration over code)."""

    async def get_report(self) -> CostAndQualityReport: ...


def _cost_breakdown_query(
    dimension_column: sa.ColumnElement[str],
) -> sa.Select[tuple[str, int, int, int, Decimal]]:
    return sa.select(
        dimension_column.label("dimension_value"),
        sa.func.count().label("call_count"),
        sa.func.coalesce(sa.func.sum(llm_calls.c.input_tokens), 0).label("total_input_tokens"),
        sa.func.coalesce(sa.func.sum(llm_calls.c.output_tokens), 0).label("total_output_tokens"),
        sa.func.coalesce(sa.func.sum(llm_calls.c.cost_usd), 0).label("total_cost_usd"),
    ).group_by(dimension_column)


class SqlCostAndQualityViews:
    """The only implementation of :class:`CostAndQualityViews` at this
    stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get_report(self) -> CostAndQualityReport:
        async with self._engine.connect() as connection:
            by_model_rows = (
                (
                    await connection.execute(
                        _cost_breakdown_query(llm_calls.c.model_id).order_by(llm_calls.c.model_id)
                    )
                )
                .mappings()
                .all()
            )
            by_workflow_rows = (
                (
                    await connection.execute(
                        _cost_breakdown_query(llm_calls.c.workflow_id).order_by(
                            llm_calls.c.workflow_id
                        )
                    )
                )
                .mappings()
                .all()
            )
            by_agent_rows = (
                (
                    await connection.execute(
                        _cost_breakdown_query(llm_calls.c.agent_id).order_by(llm_calls.c.agent_id)
                    )
                )
                .mappings()
                .all()
            )
            by_pack_rows = (
                (
                    await connection.execute(
                        _cost_breakdown_query(agents.c.pack_id)
                        .select_from(
                            llm_calls.join(agents, llm_calls.c.agent_id == agents.c.agent_id)
                        )
                        .order_by(agents.c.pack_id)
                    )
                )
                .mappings()
                .all()
            )
            gate_failure_rows = (
                (
                    await connection.execute(
                        sa.select(
                            gate_results.c.gate_id,
                            gate_results.c.status,
                            sa.func.count().label("count"),
                        )
                        .group_by(gate_results.c.gate_id, gate_results.c.status)
                        .order_by(sa.func.count().desc(), gate_results.c.gate_id)
                    )
                )
                .mappings()
                .all()
            )

        return CostAndQualityReport(
            by_model=[CostBreakdownEntry(**row) for row in by_model_rows],
            by_workflow=[CostBreakdownEntry(**row) for row in by_workflow_rows],
            by_agent=[CostBreakdownEntry(**row) for row in by_agent_rows],
            by_pack=[CostBreakdownEntry(**row) for row in by_pack_rows],
            gate_failures=[GateFailureSummaryEntry(**row) for row in gate_failure_rows],
        )
