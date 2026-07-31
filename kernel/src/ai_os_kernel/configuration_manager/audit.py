"""The tamper-evident ``governance.config_changes`` writer (data_model.md
§9.2) — ``P01-S02-M01-T08``, this table's first real writer. Until now
nothing wrote a row here at all
(:mod:`ai_os_kernel.persistence.governance_schema`'s own docstring: "no
writer, for either table").

**Not a hash chain — a deliberate, documented difference from
``governance.audit_log`` (``P01-S05-M04-T05``/``P01-S05-M04-T06``).**
data_model.md §9.2 defines ``config_changes`` with no ``seq``/
``prev_hash``/``row_hash`` columns at all: "Digests rather than values,
so a secret reference change never leaks a value." There is nothing to
chain — each row is independent, and the whole point of the table is
that it never stores enough to reconstruct a value, only enough to
prove a claimed value matches (or doesn't) a digest computed the same
way ``audit_log``'s own ``row_hash`` is. **This module reuses that exact
primitive** —
:func:`~ai_os_kernel.observability.audit.canonical_json_sha256` — for
its own per-value digests, rather than reimplementing hashing for a
second table.

**Verification here therefore means something adapted, not identical.**
Given the *real* old/new value (known to the caller; never persisted),
:func:`verify_config_change` recomputes its digest and confirms it
matches what's stored — detecting a digest tampered with directly in
the database, the same detection property
:func:`~ai_os_kernel.observability.audit.verify_chain` proves for a
whole row, applied here to a single stored value instead of a
row-linking chain, because the real schema has no chain to verify.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.configuration_manager.errors import ConfigChangeAuditError
from ai_os_kernel.configuration_manager.ids import new_config_change_id
from ai_os_kernel.observability.audit import canonical_json_sha256
from ai_os_kernel.persistence.governance_schema import config_changes


def compute_value_digest(value: Any) -> str | None:
    """``None`` in, ``None`` out — data_model.md §9.2: ``old_value_digest``
    is ``NULL`` for a key's first-ever value, ``new_value_digest`` is
    ``NULL`` when a change removes a key entirely. Any other value is
    digested via the shared, already-proven hashing primitive."""
    if value is None:
        return None
    return canonical_json_sha256(value)


class ConfigChangeRecord(BaseModel):
    """One real, persisted ``governance.config_changes`` row."""

    model_config = ConfigDict(frozen=True)

    change_id: str
    config_key: str
    old_value_digest: str | None
    new_value_digest: str | None
    changed_by: str
    reason: str
    changed_at: datetime


class ConfigChangeVerificationResult(BaseModel):
    """The real outcome of :func:`verify_config_change` — a result to
    inspect, never an exception to catch, the same shape
    :class:`~ai_os_kernel.observability.audit.ChainVerificationResult`
    already established."""

    model_config = ConfigDict(frozen=True)

    valid: bool
    reason: str | None = None


def verify_config_change(
    record: ConfigChangeRecord, *, old_value: Any = None, new_value: Any = None
) -> ConfigChangeVerificationResult:
    """Recomputes both digests from the *real* old/new values the
    caller supplies and confirms they match what's persisted. The
    caller must already know these values — that is the entire reason
    ``config_changes`` stores only digests, never the values
    themselves."""
    expected_old = compute_value_digest(old_value)
    if expected_old != record.old_value_digest:
        return ConfigChangeVerificationResult(
            valid=False,
            reason=(
                f"change {record.change_id!r}: old_value_digest does not match a "
                "recomputation of the real old value — this record was modified "
                "after it was written"
            ),
        )
    expected_new = compute_value_digest(new_value)
    if expected_new != record.new_value_digest:
        return ConfigChangeVerificationResult(
            valid=False,
            reason=(
                f"change {record.change_id!r}: new_value_digest does not match a "
                "recomputation of the real new value — this record was modified "
                "after it was written"
            ),
        )
    return ConfigChangeVerificationResult(valid=True)


class ConfigChangeWriter(Protocol):
    """Persistence boundary for recording one configuration change —
    the seam a fake implementation substitutes in unit tests
    (ADR-0004: interface-driven, configuration over code)."""

    async def record(
        self,
        *,
        config_key: str,
        old_value: Any,
        new_value: Any,
        changed_by: str,
        reason: str,
    ) -> None: ...


class SqlConfigChangeWriter:
    """The only implementation of :class:`ConfigChangeWriter` at this
    stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def record(
        self,
        *,
        config_key: str,
        old_value: Any,
        new_value: Any,
        changed_by: str,
        reason: str,
    ) -> None:
        change_id = new_config_change_id()
        changed_at = datetime.now(UTC)
        old_value_digest = compute_value_digest(old_value)
        new_value_digest = compute_value_digest(new_value)

        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    sa.insert(config_changes).values(
                        change_id=change_id,
                        config_key=config_key,
                        old_value_digest=old_value_digest,
                        new_value_digest=new_value_digest,
                        changed_by=changed_by,
                        reason=reason,
                        changed_at=changed_at,
                    )
                )
        except sa.exc.SQLAlchemyError as exc:
            raise ConfigChangeAuditError(
                f"failed to record config change for key {config_key!r} by {changed_by!r}: {exc}"
            ) from exc

    async def list_all(self) -> list[ConfigChangeRecord]:
        """Every real, persisted row, ordered by ``changed_at`` — what a
        real verification pass (this Task's own tests) reads."""
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(config_changes).order_by(config_changes.c.changed_at)
                    )
                )
                .mappings()
                .all()
            )
        return [ConfigChangeRecord.model_validate(dict(row)) for row in rows]
