"""The Impact Analyzer's real query (``P04-S02-M16-T02``): "what is
affected by changing artifact X" — data_model.md §8's own documented
mechanism, "recursive CTEs over trace.links... no graph database is
required at this scale," now genuinely built, not merely cited.

**Bidirectional traversal — the one real design decision this ticket
needed a product-owner call on.** Neither data_model.md §8 nor
traceability_model.md §4 names a canonical direction per relationship
(some of §4's own illustrative examples point a module the traversal
should reach it *as source*; others, *as target* — e.g. "an ADR
affects a module" is recorded ``adr --affects--> module``, the module
as the link's *target*). A one-directional query could silently miss a
real, recorded relationship depending on which way its own
relationship happened to point. This query instead walks every open
link touching the current frontier in *either* direction — safer for
a tool whose whole purpose is "don't let a reviewer miss something,"
at the cost of also surfacing relationships a stricter dependency-only
tool would consider out of scope.

**Only open links are traversed** (``closed_at IS NULL``) — a closed
link records a relationship that is no longer active
(traceability_model.md §6: "when artifacts are superseded, related
links must be ... closed"), so it should not make an unrelated,
already-superseded artifact look impacted today.

**A real, bounded depth, not unbounded recursion.** Real cycles are
possible in this graph (nothing in the schema forbids `A affects B`
and `B affects A`), so cycle protection is real, not decorative: each
recursion step carries the full path of keys visited so far and
refuses to revisit one (the standard Postgres recursive-CTE cycle
guard). ``_MAX_TRAVERSAL_DEPTH`` additionally bounds the recursion
itself — a second, independent safety margin in case a real graph
this large ever exists, not required for correctness on any
graph this codebase's own scale would produce today.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, array
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.trace_schema import artifacts, links
from ai_os_kernel.traceability_engine.ids import compute_artifact_key
from ai_os_kernel.traceability_engine.models import TraceArtifact

# A real, disclosed bound, not an arbitrary one: this codebase's own
# real traceability graph (a handful of requirements/modules/tests) is
# nowhere near this deep — this exists only as a second, independent
# safety margin alongside the real cycle guard below, never expected
# to bind in practice.
_MAX_TRAVERSAL_DEPTH = 50


async def find_affected_artifacts(
    engine: AsyncEngine, *, artifact_type: str, external_id: str
) -> list[TraceArtifact]:
    """Every real artifact reachable from ``(artifact_type, external_id)``
    by following open ``trace.links`` rows in either direction,
    transitively — the artifact itself is never included in its own
    result."""
    start_key = compute_artifact_key(artifact_type=artifact_type, external_id=external_id)

    anchor = (
        sa.select(
            sa.literal(start_key).label("artifact_key"),
            sa.cast(array([start_key]), ARRAY(sa.Text)).label("path"),
            sa.literal(0).label("depth"),
        )
    ).cte(name="reachable", recursive=True)

    next_key = sa.case(
        (links.c.source_key == anchor.c.artifact_key, links.c.target_key),
        else_=links.c.source_key,
    )

    recursive_step = (
        sa.select(
            next_key.label("artifact_key"),
            (anchor.c.path + array([next_key])).label("path"),
            (anchor.c.depth + 1).label("depth"),
        )
        .select_from(
            links.join(
                anchor,
                sa.or_(
                    links.c.source_key == anchor.c.artifact_key,
                    links.c.target_key == anchor.c.artifact_key,
                ),
            )
        )
        .where(links.c.closed_at.is_(None))
        .where(anchor.c.depth < _MAX_TRAVERSAL_DEPTH)
        .where(~(next_key == sa.any_(anchor.c.path)))
    )

    reachable = anchor.union_all(recursive_step)

    query = (
        sa.select(artifacts)
        .select_from(
            artifacts.join(reachable, artifacts.c.artifact_key == reachable.c.artifact_key)
        )
        .where(artifacts.c.artifact_key != start_key)
        .distinct()
    )

    async with engine.connect() as connection:
        rows = (await connection.execute(query)).mappings().all()
    return [TraceArtifact.model_validate(dict(row)) for row in rows]
