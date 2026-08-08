"""The Coverage Analyzer's real query (``P04-S02-M16-T03``, FR-115):
"report requirements lacking a verifying test."

**Only a real, ``confirmed``-confidence, open ``verifies`` link counts
as coverage — the one real design decision this ticket needed a
product-owner call on.** ``trace.links.confidence`` (data_model.md
§8) has three real values: ``confirmed``/``inferred``/``provisional``.
A merely ``inferred`` or ``provisional`` link (an agent's best guess,
never reviewed) letting a requirement read as "covered" would let a
real gap hide behind an unconfirmed guess — the opposite of what a
compliance-facing coverage report exists for. A requirement stays
reported as uncovered until a real, ``confirmed`` verifying link
exists for it.

Only *open* links count (``closed_at IS NULL``) — the identical
"a closed link records a relationship no longer active" reasoning
:mod:`ai_os_kernel.traceability_engine.impact_query` already
establishes.

No recursion needed here, unlike impact analysis — coverage is a
direct property of each requirement's own incoming links, not a
transitive graph walk.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.trace_schema import artifacts, links
from ai_os_kernel.traceability_engine.models import TraceArtifact

_REQUIREMENT_TYPE = "requirement"
_VERIFIES_RELATIONSHIP = "verifies"
_CONFIRMED_CONFIDENCE = "confirmed"


async def find_uncovered_requirements(engine: AsyncEngine) -> list[TraceArtifact]:
    """Every real, persisted ``requirement`` artifact with no real,
    open, ``confirmed``-confidence ``verifies`` link pointing at it."""
    has_confirmed_verifying_link = sa.exists(
        sa.select(links.c.link_id).where(
            links.c.target_key == artifacts.c.artifact_key,
            links.c.relationship == _VERIFIES_RELATIONSHIP,
            links.c.confidence == _CONFIRMED_CONFIDENCE,
            links.c.closed_at.is_(None),
        )
    )
    query = (
        sa.select(artifacts)
        .where(artifacts.c.artifact_type == _REQUIREMENT_TYPE)
        .where(~has_confirmed_verifying_link)
    )

    async with engine.connect() as connection:
        rows = (await connection.execute(query)).mappings().all()
    return [TraceArtifact.model_validate(dict(row)) for row in rows]
