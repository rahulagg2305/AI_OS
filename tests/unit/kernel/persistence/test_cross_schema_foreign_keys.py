"""Unit coverage for the cross-schema FK wiring helper.

Everything else in ``persistence/`` is pure declarative schema, exercised
only against a real Postgres in ``tests/integration/persistence`` (ADR-0015
— no mocking the database). ``register_workflow_run_manifest_foreign_key()``
is different: it is real Python logic (an idempotency guard over
``Table.append_constraint``), the same kind of behaviour already unit
tested for ``configure_tracing()``/``configure_metrics()`` in
``tests/unit/kernel/observability/``.
"""

import sqlalchemy as sa

from ai_os_kernel.persistence.cross_schema_foreign_keys import (
    register_workflow_run_manifest_foreign_key,
)
from ai_os_kernel.persistence.schema import workflow_instances


def _run_manifest_foreign_keys() -> list[sa.ForeignKeyConstraint]:
    return [
        constraint
        for constraint in workflow_instances.constraints
        if isinstance(constraint, sa.ForeignKeyConstraint)
        and constraint.name == "fk_workflow_instances_run_manifest_id"
    ]


def test_register_attaches_the_foreign_key_exactly_once() -> None:
    register_workflow_run_manifest_foreign_key()
    register_workflow_run_manifest_foreign_key()  # safe to call twice

    matches = _run_manifest_foreign_keys()
    assert len(matches) == 1
    constraint = matches[0]
    assert [c.name for c in constraint.columns] == ["run_manifest_id"]
    assert [e.column.table.name for e in constraint.elements] == ["run_manifests"]
    assert [e.column.name for e in constraint.elements] == ["run_manifest_id"]
