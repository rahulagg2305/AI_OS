"""Canonical Core table definition for ``security.role_grants``
(``P03-S05-M14-T07``) — see docs/08_database/data_model.md §9a for the
full column-by-column reasoning.

Its own schema, its own ``MetaData``, mirroring every other bounded
context in this codebase (``workflow``, ``catalog``, ``governance``,
...) — Security Manager has simply never needed persistence before now:
every role has come solely from a bearer token's own ``roles`` claim
(:mod:`ai_os_kernel.security_manager.token_verifier`). Combined into
Alembic's own ``target_metadata`` sequence alongside every other
schema's ``MetaData`` object, the identical mechanism
``governance_schema.py``'s own docstring already documents.

A grant is never deleted, and revocation is a real ``UPDATE`` in place
(``status`` flips ``active`` -> ``revoked``) — unlike
``governance.audit_log``'s own append-only rule, since this table
answers "what is true *right now*," not "what happened, in order."
The append-only, tamper-evident record of *that a grant/revoke
happened* lives in ``governance.audit_log`` instead
(``security.role_granted``/``security.role_revoked``), reused, not
duplicated here.
"""

import sqlalchemy as sa

metadata = sa.MetaData(schema="security")

_ROLE_GRANT_STATUSES = ("active", "revoked")

role_grants = sa.Table(
    "role_grants",
    metadata,
    sa.Column("grant_id", sa.Text, primary_key=True),
    sa.Column("principal_id", sa.Text, nullable=False),
    sa.Column("role", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("granted_by", sa.Text, nullable=False),
    sa.Column("granted_reason", sa.Text, nullable=False),
    sa.Column("granted_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("revoked_by", sa.Text, nullable=True),
    sa.Column("revoked_reason", sa.Text, nullable=True),
    sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
    sa.CheckConstraint(
        "status IN (" + ", ".join(f"'{s}'" for s in _ROLE_GRANT_STATUSES) + ")",
        name="ck_role_grants_status",
    ),
)

sa.Index("ix_role_grants_principal_id", role_grants.c.principal_id)

# The real, enforced invariant this table's own docstring names: at
# most one *active* grant of a given role for a given principal at a
# time — a partial index, since two *revoked* rows for the identical
# (principal_id, role) pair are genuinely fine (real history, not a
# conflict).
sa.Index(
    "uq_role_grants_active_principal_role",
    role_grants.c.principal_id,
    role_grants.c.role,
    unique=True,
    postgresql_where=sa.text("status = 'active'"),
)
