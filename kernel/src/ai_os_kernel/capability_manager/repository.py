"""Persists a Capability Pack's lifecycle: registering (installing) a
pack record, activating it, deactivating it, and recording every state
transition in ``catalog.pack_state_transitions`` — the "minimal write
path ... enough to make activation real, not seed-only" this step
approves.

**``register()`` now also derives and writes real ``catalog.agents``/
``catalog.prompts``/``catalog.tools`` rows from the pack's own manifest
— closing the "no automated manifest -> catalog installer exists yet"
gap several integration tests' own docstrings named explicitly.** See
:mod:`~ai_os_kernel.capability_manager.manifest_catalog_installer` for
the real derivation logic (pure functions, no database access); this
module's own job is only to run that derivation *before* opening the
write transaction (so a derivation failure — an unresolvable
``inputSchema`` import, an unreadable prompt file — never leaves a
partially-registered pack behind) and then insert the derived rows
inside the same transaction as the pack row itself, so registration
remains genuinely all-or-nothing.

**Catalog derivation is opt-in via the new ``pack_root`` parameter,
defaulting to ``None`` (unchanged behaviour) — a deliberate, load-bearing
choice, not an oversight.** ``POST /api/v1/packs``
(:mod:`ai_os_kernel.routes.packs`) already calls :meth:`register` today
with a client-supplied manifest **dict** over HTTP — there is no pack
directory on disk for that caller to point at, and ``catalog.prompts``
derivation genuinely needs one (prompt *content* is a real file on
disk, never inline in the manifest). Defaulting to ``None`` means that
route's existing behaviour is provably unchanged by this step (zero new
code there, zero new side effect); every caller that *does* have a real
pack directory (every integration test that used to hand-seed rows,
and any future pack-directory-driven registration path) opts in
explicitly by passing it.

**The smallest useful slice of the full canonical lifecycle**
(capability_manager.md §4: ``discovered -> validated -> installed ->
configured -> activated -> {deactivated, failed} -> uninstalled``) —
register/install, activate, deactivate only. No ``configured``/
``failed``/``uninstalled`` transitions, no health monitoring, no
upgrade path, no permissions matrix, no sandboxing, no remote download.

**Why ``register()`` records ``discovered -> installed``, not
``validated -> installed`` or two separate transitions.** Nothing in
this codebase persists a pack row before this writer exists — the
Manifest Loader already validates a manifest in memory
(:mod:`ai_os_kernel.manifest_loader`) without writing anything, so
there is no earlier persisted ``discovered``/``validated`` row for a
fresh registration to transition from. One combined recorded
transition, from the lifecycle's first canonical state, is the honest
reduction: it does not invent two rows this step has no mechanism to
produce, and does not silently skip recording the pack's first
transition either.

**Why ``activate()`` accepts a pack currently ``installed`` *or*
``deactivated``.** capability_manager.md §4's lifecycle diagram draws
only the primary forward path (an arrow from ``activated`` to
``deactivated``, none back), but its own state table calls
``deactivated`` explicitly "reactivatable" — the prose, not the
diagram's arrows, is what makes re-activation a real, intended
operation.

ADR-0011: writes to ``catalog.packs`` and ``catalog.pack_state_transitions``
happen in one transaction, mirroring every other snapshot+log pair in
this codebase (``workflow_instances``+``workflow_events``). ``activate``/
``deactivate`` additionally lock the pack's row (``SELECT ... FOR
UPDATE``) before validating its current state, so two concurrent calls
against the same pack cannot both observe the same pre-transition state
and both proceed — the identical "the guard is atomic, not a
read-then-write race" discipline already applied throughout
:mod:`ai_os_kernel.workflow_engine.repository`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ai_os_kernel.capability_manager.errors import (
    InvalidPackTransitionError,
    PackAlreadyRegisteredError,
    PackNotFoundError,
    PackRegistrationError,
)
from ai_os_kernel.capability_manager.ids import new_transition_id
from ai_os_kernel.capability_manager.manifest_catalog_installer import (
    derive_agent_rows,
    derive_prompt_rows,
    derive_tool_rows,
)
from ai_os_kernel.capability_manager.models import PackRecord
from ai_os_kernel.persistence.catalog_schema import (
    agents,
    pack_state_transitions,
    packs,
    prompts,
    tools,
)
from ai_os_kernel.workflow_engine.pack_state import PackState

# The lifecycle's first canonical state — see module docstring for why
# every fresh registration's own recorded transition reads as coming
# from here, rather than "validated" or two separate rows.
_REGISTER_FROM_STATE = PackState.DISCOVERED

# See module docstring: "deactivated" is explicitly documented as
# reactivatable, so both states are valid pre-activation states.
_ACTIVATABLE_FROM_STATES = frozenset({PackState.INSTALLED, PackState.DEACTIVATED})
_DEACTIVATABLE_FROM_STATES = frozenset({PackState.ACTIVATED})


class PackLifecycleRepository(Protocol):
    """Persistence boundary for the Capability Pack lifecycle's write
    path — the seam a fake/in-memory implementation substitutes in unit
    tests (ADR-0004: interface-driven, configuration over code)."""

    async def register(
        self,
        *,
        pack_id: str,
        version: str,
        manifest: dict[str, Any],
        sdk_version: str,
        min_kernel_version: str,
        actor: str,
        reason: str,
        pack_root: Path | None = None,
    ) -> PackRecord: ...

    async def activate(self, *, pack_id: str, actor: str, reason: str) -> PackRecord: ...

    async def deactivate(self, *, pack_id: str, actor: str, reason: str) -> PackRecord: ...

    async def get_pack(self, pack_id: str) -> PackRecord | None: ...


class SqlPackLifecycleRepository:
    """The only implementation of :class:`PackLifecycleRepository` at
    this stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def register(
        self,
        *,
        pack_id: str,
        version: str,
        manifest: dict[str, Any],
        sdk_version: str,
        min_kernel_version: str,
        actor: str,
        reason: str,
        pack_root: Path | None = None,
    ) -> PackRecord:
        # Derived before the transaction opens, deliberately — see this
        # module's own docstring: a bad manifest reference must never
        # leave a half-registered pack behind, and a pure, DB-free
        # derivation failure here can't, since nothing has been written
        # yet.
        agent_rows: list[dict[str, Any]] = []
        prompt_rows: list[dict[str, Any]] = []
        tool_rows: list[dict[str, Any]] = []
        if pack_root is not None:
            agent_rows = derive_agent_rows(manifest, pack_id=pack_id)
            prompt_rows = derive_prompt_rows(manifest, pack_id=pack_id, pack_root=pack_root)
            tool_rows = derive_tool_rows(manifest, pack_id=pack_id)

        occurred_at = datetime.now(UTC)
        try:
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    sa.insert(packs)
                    .values(
                        pack_id=pack_id,
                        version=version,
                        state=PackState.INSTALLED.value,
                        manifest=manifest,
                        sdk_version=sdk_version,
                        min_kernel_version=min_kernel_version,
                        installed_at=occurred_at,
                    )
                    .returning(*packs.columns)
                )
                pack_row = result.mappings().one()

                await self._record_transition(
                    connection,
                    pack_id=pack_id,
                    from_state=_REGISTER_FROM_STATE,
                    to_state=PackState.INSTALLED,
                    actor=actor,
                    reason=reason,
                    occurred_at=occurred_at,
                )

                if agent_rows:
                    await connection.execute(sa.insert(agents), agent_rows)
                if prompt_rows:
                    await connection.execute(sa.insert(prompts), prompt_rows)
                if tool_rows:
                    await connection.execute(sa.insert(tools), tool_rows)
        except sa.exc.IntegrityError as exc:
            raise PackAlreadyRegisteredError(
                f"pack '{pack_id}' is already registered in catalog.packs"
            ) from exc
        except sa.exc.SQLAlchemyError as exc:
            raise PackRegistrationError(f"failed to register pack '{pack_id}': {exc}") from exc

        return PackRecord.model_validate(dict(pack_row))

    async def activate(self, *, pack_id: str, actor: str, reason: str) -> PackRecord:
        occurred_at = datetime.now(UTC)
        try:
            async with self._engine.begin() as connection:
                from_state = await self._lock_current_state(connection, pack_id)
                if from_state not in _ACTIVATABLE_FROM_STATES:
                    raise InvalidPackTransitionError(
                        f"cannot activate pack '{pack_id}': current state is "
                        f"{from_state.value!r}, expected one of "
                        f"({', '.join(sorted(s.value for s in _ACTIVATABLE_FROM_STATES))})"
                    )

                result = await connection.execute(
                    sa.update(packs)
                    .where(packs.c.pack_id == pack_id, packs.c.state == from_state.value)
                    .values(state=PackState.ACTIVATED.value, activated_at=occurred_at)
                    .returning(*packs.columns)
                )
                pack_row = result.mappings().one()

                await self._record_transition(
                    connection,
                    pack_id=pack_id,
                    from_state=from_state,
                    to_state=PackState.ACTIVATED,
                    actor=actor,
                    reason=reason,
                    occurred_at=occurred_at,
                )
        except sa.exc.SQLAlchemyError as exc:
            raise PackRegistrationError(f"failed to activate pack '{pack_id}': {exc}") from exc

        return PackRecord.model_validate(dict(pack_row))

    async def deactivate(self, *, pack_id: str, actor: str, reason: str) -> PackRecord:
        occurred_at = datetime.now(UTC)
        try:
            async with self._engine.begin() as connection:
                from_state = await self._lock_current_state(connection, pack_id)
                if from_state not in _DEACTIVATABLE_FROM_STATES:
                    raise InvalidPackTransitionError(
                        f"cannot deactivate pack '{pack_id}': current state is "
                        f"{from_state.value!r}, expected one of "
                        f"({', '.join(sorted(s.value for s in _DEACTIVATABLE_FROM_STATES))})"
                    )

                result = await connection.execute(
                    sa.update(packs)
                    .where(packs.c.pack_id == pack_id, packs.c.state == from_state.value)
                    .values(state=PackState.DEACTIVATED.value)
                    .returning(*packs.columns)
                )
                pack_row = result.mappings().one()

                await self._record_transition(
                    connection,
                    pack_id=pack_id,
                    from_state=from_state,
                    to_state=PackState.DEACTIVATED,
                    actor=actor,
                    reason=reason,
                    occurred_at=occurred_at,
                )
        except sa.exc.SQLAlchemyError as exc:
            raise PackRegistrationError(f"failed to deactivate pack '{pack_id}': {exc}") from exc

        return PackRecord.model_validate(dict(pack_row))

    async def get_pack(self, pack_id: str) -> PackRecord | None:
        """A plain, unguarded read — mirrors
        :meth:`~ai_os_kernel.workflow_engine.repository.WorkflowInstanceRepository.get_instance`."""
        async with self._engine.connect() as connection:
            result = await connection.execute(sa.select(packs).where(packs.c.pack_id == pack_id))
            row = result.mappings().one_or_none()
        return PackRecord.model_validate(dict(row)) if row is not None else None

    @staticmethod
    async def _lock_current_state(connection: AsyncConnection, pack_id: str) -> PackState:
        """Takes a row lock (``FOR UPDATE``) on ``pack_id``'s row and
        returns its current state — the read half of the atomic
        "read current state, validate, write" sequence :meth:`activate`/
        :meth:`deactivate` both need. Raises :class:`PackNotFoundError`
        if no such row exists; ``pack_id`` is not itself the caller's to
        create here (that is :meth:`register`'s job)."""
        result = await connection.execute(
            sa.select(packs.c.state).where(packs.c.pack_id == pack_id).with_for_update()
        )
        row = result.one_or_none()
        if row is None:
            raise PackNotFoundError(f"no pack '{pack_id}' is registered in catalog.packs")
        return PackState(row.state)

    @staticmethod
    async def _record_transition(
        connection: AsyncConnection,
        *,
        pack_id: str,
        from_state: PackState,
        to_state: PackState,
        actor: str,
        reason: str,
        occurred_at: datetime,
    ) -> None:
        await connection.execute(
            sa.insert(pack_state_transitions).values(
                transition_id=new_transition_id(),
                pack_id=pack_id,
                from_state=from_state.value,
                to_state=to_state.value,
                reason=reason,
                actor=actor,
                occurred_at=occurred_at,
            )
        )
