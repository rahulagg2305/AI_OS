"""Canonical Core table definition for ``context.context_assemblies``
(``P02-S03-M08-T10``) — see docs/08_database/data_model.md §9b for the
full column-by-column reasoning.

Its own schema, its own ``MetaData``, mirroring every other bounded
context in this codebase (``workflow``, ``governance``, ``security``,
...) — the identical "one schema per genuinely distinct bounded
context" precedent :mod:`ai_os_kernel.persistence.knowledge_schema`'s
own docstring already states, applied again here since Context Manager
has never needed persistence before now. Combined into Alembic's own
``target_metadata`` sequence alongside every other schema's ``MetaData``
object, the identical mechanism ``governance_schema.py``'s own docstring
already documents.

**Considered and rejected: reusing ``governance.audit_log`` instead of
a new table.** That table already has a generic, JSON ``detail``
column and an open-ended ``event_type`` — superficially reusable. Its
own real, singular purpose (ADR-0017: tamper-evident, hash-chained
security audit trail — auth, secret access, config change, pack
lifecycle, sandbox execution) is a genuinely different concern from a
debugging/replay aid for ordinary context assembly, with different
consumers and no tamper-evidence requirement. Cramming this in would
blur that table's own well-scoped boundary, not "reuse existing
infrastructure" in the sense this codebase's own precedent means.

``included_items`` stores each :class:`~ai_os_kernel.context_manager.
models.ContextItem` at full fidelity (``content``/``provenance``/
``relevance_score``/``token_count``/``trust``), not a summary — the
only way this table can genuinely support §9's own "exact replay of
experiments," since none of that combined shape is durably recorded
anywhere else once an assembly returns.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData(schema="context")

context_assemblies = sa.Table(
    "context_assemblies",
    metadata,
    sa.Column("assembly_id", sa.Text, primary_key=True),
    sa.Column("workflow_id", sa.Text, nullable=False),
    sa.Column("step_id", sa.Text, nullable=False),
    sa.Column("agent_id", sa.Text, nullable=True),
    sa.Column("sources_queried", JSONB, nullable=False),
    sa.Column("included_items", JSONB, nullable=False),
    sa.Column("items_excluded_count", sa.Integer, nullable=False),
    sa.Column("total_tokens", sa.Integer, nullable=False),
    sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False),
)

sa.Index("ix_context_assemblies_workflow_id", context_assemblies.c.workflow_id)
sa.Index("ix_context_assemblies_recorded_at_desc", context_assemblies.c.recorded_at.desc())
