"""Canonical Core table definitions for traceability persistence.

Mirrors docs/08_database/data_model.md §8, in the same style as
:mod:`ai_os_kernel.persistence.governance_schema` and
:mod:`ai_os_kernel.persistence.platform_schema`: kept in its own module
with its own ``MetaData`` (schema ``trace``), a genuinely distinct
bounded context from ``workflow``, ``governance``, and ``platform``.
Combined into ``target_metadata`` in ``kernel/alembic/env.py`` alongside
the other three.

Both tables §8 documents are defined here: ``artifacts`` and ``links``
(schema ``trace`` — table names not prefixed with ``trace_``, the same
naming already used for ``workflow.approvals``: the doc's own header
gives the literal table name, and that is what is used).

Schema and migration only — no writer. §8 says "Impact analysis uses
recursive CTEs over `trace.links`" — no Traceability Engine exists yet
to run one, and nothing writes a traceability link yet either.

``artifacts.artifact_type`` gets a ``CHECK`` constraint: §8 gives it an
explicit ten-value list (``requirement``/``architecture_element``/
``adr``/``design_element``/``module``/``source_file``/``test_case``/
``documentation``/``release``/``workflow_run``), the same "canonical
list is documented, so enforce it" reasoning already applied to
``workflow_instances.status``, ``approvals.status``, and
``audit_log.outcome``. ``links.relationship`` (seven values),
``links.confidence`` (three values), and ``links.created_by_type``
(three values) each get one for the identical reason.

Unlike every table added in the ``governance``/``platform`` steps,
``links.source_key``/``target_key`` **do** get foreign keys — to
``artifacts.artifact_key`` — because, unlike those tables' polymorphic
or unscoped pointers, a traceability link's source and target are
unambiguously artifact keys; nothing else. Recursive-CTE impact
analysis depends on every link genuinely pointing to a real artifact.

``links.closed_at`` is nullable (§8 marks it so explicitly: "``closed_at``
NULL"); every other column in both tables is ``NOT NULL`` — §8 marks no
other column nullable in either table, the same "explicit ``NULL`` is
the only signal for nullable, everything else is required" convention
already followed for ``governance``/``platform``.

The documented ``UNIQUE (source_key, relationship, target_key)`` rule
applies only **where** ``closed_at IS NULL`` — a partial unique index,
not a plain table-level ``UniqueConstraint`` (which cannot carry a
``WHERE`` clause in standard SQL). This is what lets a link be closed
and the same triple re-asserted later without violating uniqueness on
the historical, closed row, while still forbidding two simultaneously
*open* links for the same triple.
"""

import sqlalchemy as sa

metadata = sa.MetaData(schema="trace")

ARTIFACT_TYPES = (
    "requirement",
    "architecture_element",
    "adr",
    "design_element",
    "module",
    "source_file",
    "test_case",
    "documentation",
    "release",
    "workflow_run",
)

artifacts = sa.Table(
    "artifacts",
    metadata,
    sa.Column("artifact_key", sa.Text, primary_key=True),
    sa.Column("artifact_type", sa.Text, nullable=False),
    sa.Column("external_id", sa.Text, nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("location", sa.Text, nullable=False),
    sa.Column("version", sa.Text, nullable=False),
    sa.CheckConstraint(
        "artifact_type IN (" + ", ".join(f"'{t}'" for t in ARTIFACT_TYPES) + ")",
        name="ck_artifacts_artifact_type",
    ),
)

sa.Index("ix_artifacts_artifact_type", artifacts.c.artifact_type)
sa.Index("ix_artifacts_external_id", artifacts.c.external_id)

LINK_RELATIONSHIPS = (
    "implements",
    "verifies",
    "realizes",
    "affects",
    "contains",
    "produced",
    "applies_to",
)

LINK_CONFIDENCES = (
    "confirmed",
    "inferred",
    "provisional",
)

LINK_CREATED_BY_TYPES = (
    "agent",
    "user",
    "process",
)

links = sa.Table(
    "links",
    metadata,
    sa.Column("link_id", sa.Text, primary_key=True),
    sa.Column(
        "source_key",
        sa.Text,
        sa.ForeignKey(artifacts.c.artifact_key),
        nullable=False,
    ),
    sa.Column("relationship", sa.Text, nullable=False),
    sa.Column(
        "target_key",
        sa.Text,
        sa.ForeignKey(artifacts.c.artifact_key),
        nullable=False,
    ),
    sa.Column("confidence", sa.Text, nullable=False),
    sa.Column("created_by", sa.Text, nullable=False),
    sa.Column("created_by_type", sa.Text, nullable=False),
    sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    sa.CheckConstraint(
        "relationship IN (" + ", ".join(f"'{r}'" for r in LINK_RELATIONSHIPS) + ")",
        name="ck_links_relationship",
    ),
    sa.CheckConstraint(
        "confidence IN (" + ", ".join(f"'{c}'" for c in LINK_CONFIDENCES) + ")",
        name="ck_links_confidence",
    ),
    sa.CheckConstraint(
        "created_by_type IN (" + ", ".join(f"'{t}'" for t in LINK_CREATED_BY_TYPES) + ")",
        name="ck_links_created_by_type",
    ),
)

sa.Index("ix_links_source_key", links.c.source_key)
sa.Index("ix_links_target_key", links.c.target_key)
sa.Index(
    "uq_links_open_source_relationship_target",
    links.c.source_key,
    links.c.relationship,
    links.c.target_key,
    unique=True,
    postgresql_where=links.c.closed_at.is_(None),
)
