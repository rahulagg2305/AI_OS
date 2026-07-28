"""Foreign keys that cross two bounded-context schema modules.

Every schema module in this package (`schema.py` for `workflow`,
`governance_schema.py`, `platform_schema.py`, `trace_schema.py`,
`catalog_schema.py`, `evaluation_schema.py`) owns exactly one ``MetaData``
object, by design (see `schema.py`'s own module docstring). A foreign key
between two tables that live in *different* schema modules therefore
needs a real, already-constructed ``Column`` object from the other
module — SQLAlchemy resolves a plain string reference (e.g.
``"evaluation.run_manifests.run_manifest_id"``) only against the
*referencing* column's own ``Table.metadata.tables``, never against a
different ``MetaData`` (verified directly: it raises
``NoReferencedTableError`` the moment anything compiles or resolves it).

That is exactly what already makes ``evaluation_schema.run_manifests.
workflow_id`` work: it imports the real
:data:`ai_os_kernel.persistence.schema.workflow_instances` object.

The *reverse* direction — attaching a foreign key from
``workflow.workflow_instances.run_manifest_id`` to
``evaluation.run_manifests.run_manifest_id`` — cannot be declared the
same way, inline, inside `schema.py`'s own ``sa.Table(...)`` call:
`evaluation_schema.py` already imports `schema.py` (for the FK above),
so `schema.py` importing `evaluation_schema.py` back, at module level,
would be a genuine circular import (`schema.py` half-initialized when
`evaluation_schema.py` asks for `workflow_instances`, or vice versa,
depending on which module happens to be imported first) — one of the
Coding Standards' explicitly forbidden practices ("circular or hidden
dependencies").

This module is the resolution: a small, standalone composition step,
analogous to how `bootstrap.build_app()` wires concrete dependencies
together explicitly rather than modules reaching into each other. It is
imported by neither `schema.py` nor `evaluation_schema.py`, so importing
*it* can never itself be part of a cycle — by the time anything imports
this module, both schema modules it depends on are guaranteed to already
be fully initialized (whichever of the two happened to trigger the
other's import first has already completed). `kernel/alembic/env.py`
calls :func:`register_workflow_run_manifest_foreign_key` once, after
importing every schema module's ``MetaData``, mirroring the explicit,
idempotency-guarded ``configure_tracing()``/``configure_metrics()``
composition calls in `bootstrap.py`.

Only ``workflow_instances.run_manifest_id`` is wired here. The two other
foreign keys `schema.py`'s docstring still lists as deferred —
``workflow_instances``/``workflow_events`` → ``catalog.workflow_definitions``
(additionally blocked on the open ``definition_id`` versioning ambiguity)
and → ``evaluation.experiments`` (that table does not exist yet) — remain
untouched and are not this step's concern.
"""

import sqlalchemy as sa

from ai_os_kernel.persistence.evaluation_schema import run_manifests
from ai_os_kernel.persistence.schema import workflow_instances

_RUN_MANIFEST_FK_NAME = "fk_workflow_instances_run_manifest_id"


def register_workflow_run_manifest_foreign_key() -> None:
    """Attach ``workflow_instances.run_manifest_id`` → ``run_manifests.run_manifest_id``.

    Idempotency-guarded: SQLAlchemy raises if a same-named constraint is
    appended to a ``Table`` twice, and this function may legitimately be
    called more than once within a single process (e.g. once by
    ``env.py``, once by a test that imports this module directly).
    """
    already_registered = any(
        isinstance(constraint, sa.ForeignKeyConstraint) and constraint.name == _RUN_MANIFEST_FK_NAME
        for constraint in workflow_instances.constraints
    )
    if already_registered:
        return

    workflow_instances.append_constraint(
        sa.ForeignKeyConstraint(
            ["run_manifest_id"],
            [run_manifests.c.run_manifest_id],
            name=_RUN_MANIFEST_FK_NAME,
        )
    )
