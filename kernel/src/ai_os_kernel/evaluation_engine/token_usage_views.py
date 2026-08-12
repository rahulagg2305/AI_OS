"""Token Usage Views (`P06-S01-M36-T04`) — api_architecture.md §6.4's
own ``GET /api/v1/usage/tokens``, "Token usage incl. cache split".

**Why this is not already covered by
:mod:`ai_os_kernel.evaluation_engine.cost_and_quality_views`.** That
module answers FR-095 ("token and cost breakdown by model, workflow,
agent, and pack") and is already exposed at
``GET /api/v1/evaluation/cost-and-quality``. Its
:class:`~ai_os_kernel.evaluation_engine.cost_and_quality_views.
CostBreakdownEntry` carries ``total_input_tokens``,
``total_output_tokens`` and ``total_cost_usd`` — but **no cache
columns at all**, even though ``evaluation.llm_calls`` has recorded
``cache_read_tokens`` and ``cache_write_tokens`` on every real call
since the table existed. So the cache split §6.4 names by name is real,
already-populated production data that nothing anywhere reads. This
module is the reader.

**Deliberately a separate module rather than more fields on the cost
report.** Widening ``CostBreakdownEntry`` would change the response
shape of an endpoint the Dashboard already consumes
(``P06-S03-M39-T03``), for callers that asked for cost and never asked
for cache behaviour. A new, additive view leaves that contract intact —
the same "additive, never reshape a live contract" reasoning
``GET /experiments/{id}/runs`` used rather than widening
``comparison``.

**The same four dimensions as the cost report, deliberately.** FR-095
names model, workflow, agent and pack as the breakdown a real caller
needs, and §6.4's own ``usage/cost`` row names "by model/workflow/pack".
Answering the token question along different axes than the cost question
would make the two impossible to read side by side, which is exactly how
a caller uses them: "this model costs the most — is it also the one
missing the cache?" ``pack`` is derived through the real
``catalog.agents.pack_id`` foreign key, never by string-splitting
``agent_id``, matching the cost view's own explicit choice.

**Raw sums, no invented ratio.** A cache *hit rate* would require
deciding what the denominator is — input tokens, or input plus cache
reads — and the answer changes the number materially. Neither
``api_architecture.md`` nor ``nfr.md`` defines one, so this returns the
real recorded sums and lets a caller compute the ratio it means. A
plausible-looking number with an undocumented denominator would be a
guess presented as a measurement.

**No time filtering.** ``llm_calls`` gained a ``created_at`` column in
migration ``0035``, so a windowed query is now *possible* — but §6.4
documents no time parameters on this endpoint, and inventing them would
be undocumented API surface. Recorded here as a real, available
follow-up rather than silently added.
"""

from __future__ import annotations

from typing import Protocol

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.catalog_schema import agents
from ai_os_kernel.persistence.evaluation_schema import llm_calls


class TokenUsageEntry(BaseModel):
    """One real dimension value's own token totals, including the cache
    split — e.g. one real ``model_id`` together with every real call
    recorded against it."""

    dimension_value: str
    call_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_write_tokens: int


class TokenUsageReport(BaseModel):
    """§6.4's own "Token usage incl. cache split", across the same four
    dimensions the cost report uses."""

    by_model: list[TokenUsageEntry]
    by_workflow: list[TokenUsageEntry]
    by_agent: list[TokenUsageEntry]
    by_pack: list[TokenUsageEntry]


class TokenUsageViews(Protocol):
    """The seam a fake implementation substitutes in unit tests
    (ADR-0004: interface-driven, configuration over code)."""

    async def get_token_usage(self) -> TokenUsageReport: ...


def _token_usage_query(
    dimension_column: sa.ColumnElement[str],
) -> sa.Select[tuple[str, int, int, int, int, int]]:
    """One dimension's aggregate. ``coalesce`` on every sum for the same
    reason the cost view uses it: ``SUM`` over zero rows is ``NULL``, and
    a dimension that exists with no recorded tokens must report ``0``,
    never null."""
    return sa.select(
        dimension_column.label("dimension_value"),
        sa.func.count().label("call_count"),
        sa.func.coalesce(sa.func.sum(llm_calls.c.input_tokens), 0).label("total_input_tokens"),
        sa.func.coalesce(sa.func.sum(llm_calls.c.output_tokens), 0).label("total_output_tokens"),
        sa.func.coalesce(sa.func.sum(llm_calls.c.cache_read_tokens), 0).label(
            "total_cache_read_tokens"
        ),
        sa.func.coalesce(sa.func.sum(llm_calls.c.cache_write_tokens), 0).label(
            "total_cache_write_tokens"
        ),
    ).group_by(dimension_column)


class SqlTokenUsageViews:
    """The only implementation of :class:`TokenUsageViews` at this
    stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get_token_usage(self) -> TokenUsageReport:
        async with self._engine.connect() as connection:

            async def rows(
                statement: sa.Select[tuple[str, int, int, int, int, int]],
            ) -> list[TokenUsageEntry]:
                result = await connection.execute(statement)
                return [TokenUsageEntry(**row) for row in result.mappings().all()]

            by_model = await rows(
                _token_usage_query(llm_calls.c.model_id).order_by(llm_calls.c.model_id)
            )
            by_workflow = await rows(
                _token_usage_query(llm_calls.c.workflow_id).order_by(llm_calls.c.workflow_id)
            )
            by_agent = await rows(
                _token_usage_query(llm_calls.c.agent_id).order_by(llm_calls.c.agent_id)
            )
            # Real FK join, never a string-split on `agent_id`'s
            # conventional "<pack_id>/<name>" shape — the cost view's own
            # explicit choice, kept identical so the two reconcile.
            by_pack = await rows(
                _token_usage_query(agents.c.pack_id)
                .select_from(llm_calls.join(agents, llm_calls.c.agent_id == agents.c.agent_id))
                .order_by(agents.c.pack_id)
            )

        return TokenUsageReport(
            by_model=by_model,
            by_workflow=by_workflow,
            by_agent=by_agent,
            by_pack=by_pack,
        )
