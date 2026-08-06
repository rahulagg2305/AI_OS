"""Persists a Capability Pack's lifecycle: registering (installing) a
pack record, activating it, deactivating it, and recording every state
transition in ``catalog.pack_state_transitions`` — the "minimal write
path ... enough to make activation real, not seed-only" this step
approves.

**``register()`` now also derives and writes real ``catalog.agents``/
``catalog.prompts``/``catalog.tools``/``catalog.workflow_definitions``
rows from the pack's own manifest — closing the "no automated manifest
-> catalog installer exists yet" gap several integration tests' own
docstrings named explicitly.** See
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

**``mark_failed()`` and ``record_health()`` close capability_manager.md
§9's own "health check protocols" gap — the real consequence of a
genuine Pack Health Collector poll, not health monitoring itself.**
:mod:`~ai_os_kernel.capability_manager.health_poller` is the real
caller: ``record_health()`` writes a plain, informational
``catalog.packs.health`` snapshot on every poll (healthy or not — never
itself a lifecycle transition); ``mark_failed()`` is the one real,
audited transition this module gains beyond register/activate/
deactivate, called only after that poller's own consecutive-failure
threshold is crossed, following the identical lock/validate/write/
record shape ``activate``/``deactivate`` already establish.

**The smallest useful slice of the full canonical lifecycle**
(capability_manager.md §4: ``discovered -> validated -> installed ->
configured -> activated -> {deactivated, failed} -> uninstalled``) —
register/install, activate, deactivate, and the one real ``-> failed``
transition. Still no ``configured``/``uninstalled`` transitions, no
permissions matrix, no sandboxing, no remote download.

**``upgrade()`` (``P02-S05-M13-T07``) closes capability_manager.md §9's
own "Upgrade strategies" row — the real, buildable slice of it.** See
that method's own docstring for exactly which of its three named open
questions this settles (two, by the schema's own existing structure) and
which it deliberately leaves open (in-flight workflow instances of the
old version, still genuinely undecided).

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
from packaging.version import InvalidVersion, Version
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ai_os_kernel.capability_manager.errors import (
    InvalidPackTransitionError,
    InvalidPackUpgradeError,
    PackAlreadyRegisteredError,
    PackNotFoundError,
    PackRegistrationError,
)
from ai_os_kernel.capability_manager.ids import new_transition_id
from ai_os_kernel.capability_manager.manifest_catalog_installer import (
    derive_agent_rows,
    derive_prompt_rows,
    derive_tool_rows,
    derive_workflow_definition_rows,
)
from ai_os_kernel.capability_manager.models import PackRecord
from ai_os_kernel.persistence.catalog_schema import (
    agents,
    pack_state_transitions,
    packs,
    prompts,
    tools,
    workflow_definitions,
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

# See module docstring: only a currently-ACTIVATED pack can genuinely
# fail — a pack that was never serving (installed/deactivated) has
# nothing running to fail. Deliberately excludes ACTIVATABLE_FROM_STATES
# so `failed` stays a distinct, one-way consequence of real, observed
# health polling, not something reachable from every other state.
_FAILABLE_FROM_STATES = frozenset({PackState.ACTIVATED})

# capability_manager.md §9's own Upgrade Strategies row settles question
# (a) by omission, not by a new ADR: no `upgrading` state exists in the
# canonical 8-value lifecycle (`_PACK_STATES`, catalog_schema.py's own
# `CHECK` constraint), so upgrading a pack that is not already serving
# traffic has no real, observable meaning yet to build against — you
# upgrade a pack that is live, matching this ticket's own Goal ("Upgrade
# an *activated* pack"). Restricting to this one state, rather than also
# allowing `installed`/`deactivated`, keeps the real, decided question
# (c) — "no two versions of one pack may be simultaneously activated,
# `catalog.packs` is keyed on `pack_id` alone" — the only version
# question this method answers; question (b) (in-flight workflow
# instances of the old version) remains genuinely open, unanswered here.
_UPGRADABLE_FROM_STATES = frozenset({PackState.ACTIVATED})


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

    async def upgrade(
        self,
        *,
        pack_id: str,
        version: str,
        manifest: dict[str, Any],
        sdk_version: str,
        min_kernel_version: str,
        pack_root: Path,
        actor: str,
        reason: str,
    ) -> PackRecord: ...

    async def mark_failed(self, *, pack_id: str, actor: str, reason: str) -> PackRecord: ...

    async def record_health(self, *, pack_id: str, health: dict[str, Any]) -> None: ...

    async def get_pack(self, pack_id: str) -> PackRecord | None: ...

    async def list_packs(self) -> list[PackRecord]: ...


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
        workflow_definition_rows: list[dict[str, Any]] = []
        if pack_root is not None:
            agent_rows = derive_agent_rows(manifest, pack_id=pack_id)
            prompt_rows = derive_prompt_rows(manifest, pack_id=pack_id, pack_root=pack_root)
            tool_rows = derive_tool_rows(manifest, pack_id=pack_id)
            workflow_definition_rows = derive_workflow_definition_rows(
                manifest, pack_id=pack_id, pack_root=pack_root
            )

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
                if workflow_definition_rows:
                    await connection.execute(
                        pg_insert(workflow_definitions)
                        .values(workflow_definition_rows)
                        .on_conflict_do_nothing(index_elements=["definition_id", "version"])
                    )
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

    async def upgrade(
        self,
        *,
        pack_id: str,
        version: str,
        manifest: dict[str, Any],
        sdk_version: str,
        min_kernel_version: str,
        pack_root: Path,
        actor: str,
        reason: str,
    ) -> PackRecord:
        """Migrates an already-``activated`` pack to a new version, in
        place — capability_manager.md §9's own real, buildable slice of
        "Upgrade strategies" (see :data:`_UPGRADABLE_FROM_STATES`'s own
        comment for the two of its three open questions this method
        settles, and the one — in-flight workflow instances of the old
        version — it deliberately does not).

        **Unlike :meth:`register`, ``pack_root`` is required, not
        optional.** An upgrade that updated ``catalog.packs.manifest``
        without re-deriving ``catalog.agents``/``catalog.prompts``/
        ``catalog.tools`` would leave the pack claiming a new version
        while every real component row still reflected the old one —
        exactly the silent state corruption this ticket's own proof
        requirement names. There is no safe partial upgrade.

        **Refuses a same-or-older ``version``** (:class:`InvalidPackUpgradeError`)
        before touching any row — an upgrade must prove real forward
        progress, per PEP 440 ordering (:mod:`packaging.version`, the
        same library ``manifest_loader.semantic`` already uses for
        version-range checks).

        **Reconciles, not replaces, ``catalog.agents``/``catalog.tools``**:
        an id present in the new manifest is upserted (its row's content
        may have genuinely changed between versions); an id no longer
        declared is deleted outright, not left orphaned pointing at a
        pack that no longer claims it. ``catalog.prompts`` and
        ``catalog.workflow_definitions`` are append-only instead,
        matching their own "versions are immutable" rule (data_model.md
        §5) — a prompt or workflow-definition version already on disk is
        inserted idempotently (``ON CONFLICT DO NOTHING`` on its real
        composite key), never overwritten.
        """
        try:
            new_version = Version(version)
        except InvalidVersion as exc:
            raise InvalidPackUpgradeError(
                f"cannot upgrade pack '{pack_id}': {version!r} is not a valid version: {exc}"
            ) from exc

        # Derived before the transaction opens — the identical "a bad
        # manifest reference must never leave a half-migrated pack
        # behind" discipline `register()` already establishes.
        agent_rows = derive_agent_rows(manifest, pack_id=pack_id)
        prompt_rows = derive_prompt_rows(manifest, pack_id=pack_id, pack_root=pack_root)
        tool_rows = derive_tool_rows(manifest, pack_id=pack_id)
        workflow_definition_rows = derive_workflow_definition_rows(
            manifest, pack_id=pack_id, pack_root=pack_root
        )
        new_agent_ids = {row["agent_id"] for row in agent_rows}
        new_tool_ids = {row["tool_id"] for row in tool_rows}

        occurred_at = datetime.now(UTC)
        try:
            async with self._engine.begin() as connection:
                from_state = await self._lock_current_state(connection, pack_id)
                if from_state not in _UPGRADABLE_FROM_STATES:
                    raise InvalidPackTransitionError(
                        f"cannot upgrade pack '{pack_id}': current state is "
                        f"{from_state.value!r}, expected one of "
                        f"({', '.join(sorted(s.value for s in _UPGRADABLE_FROM_STATES))})"
                    )

                current_version_row = await connection.execute(
                    sa.select(packs.c.version).where(packs.c.pack_id == pack_id)
                )
                current_version = Version(current_version_row.scalar_one())
                if new_version <= current_version:
                    raise InvalidPackUpgradeError(
                        f"cannot upgrade pack '{pack_id}' from {current_version} to "
                        f"{new_version}: an upgrade must be a strictly newer version"
                    )

                result = await connection.execute(
                    sa.update(packs)
                    .where(packs.c.pack_id == pack_id)
                    .values(
                        version=version,
                        manifest=manifest,
                        sdk_version=sdk_version,
                        min_kernel_version=min_kernel_version,
                    )
                    .returning(*packs.columns)
                )
                pack_row = result.mappings().one()

                await self._record_transition(
                    connection,
                    pack_id=pack_id,
                    from_state=PackState.ACTIVATED,
                    to_state=PackState.ACTIVATED,
                    actor=actor,
                    reason=f"{reason} (upgrade {current_version} -> {new_version})",
                    occurred_at=occurred_at,
                )

                if new_agent_ids:
                    await connection.execute(
                        sa.delete(agents).where(
                            agents.c.pack_id == pack_id, agents.c.agent_id.notin_(new_agent_ids)
                        )
                    )
                else:
                    await connection.execute(sa.delete(agents).where(agents.c.pack_id == pack_id))

                if new_tool_ids:
                    await connection.execute(
                        sa.delete(tools).where(
                            tools.c.pack_id == pack_id, tools.c.tool_id.notin_(new_tool_ids)
                        )
                    )
                else:
                    await connection.execute(sa.delete(tools).where(tools.c.pack_id == pack_id))

                if agent_rows:
                    agent_upsert = pg_insert(agents).values(agent_rows)
                    await connection.execute(
                        agent_upsert.on_conflict_do_update(
                            index_elements=["agent_id"],
                            set_={
                                col.name: agent_upsert.excluded[col.name]
                                for col in agents.columns
                                if col.name != "agent_id"
                            },
                        )
                    )
                if tool_rows:
                    tool_upsert = pg_insert(tools).values(tool_rows)
                    await connection.execute(
                        tool_upsert.on_conflict_do_update(
                            index_elements=["tool_id"],
                            set_={
                                col.name: tool_upsert.excluded[col.name]
                                for col in tools.columns
                                if col.name != "tool_id"
                            },
                        )
                    )
                if prompt_rows:
                    await connection.execute(
                        pg_insert(prompts)
                        .values(prompt_rows)
                        .on_conflict_do_nothing(index_elements=["prompt_id", "version"])
                    )
                if workflow_definition_rows:
                    await connection.execute(
                        pg_insert(workflow_definitions)
                        .values(workflow_definition_rows)
                        .on_conflict_do_nothing(index_elements=["definition_id", "version"])
                    )
        except (InvalidPackTransitionError, InvalidPackUpgradeError):
            raise
        except sa.exc.SQLAlchemyError as exc:
            raise PackRegistrationError(f"failed to upgrade pack '{pack_id}': {exc}") from exc

        return PackRecord.model_validate(dict(pack_row))

    async def mark_failed(self, *, pack_id: str, actor: str, reason: str) -> PackRecord:
        """The real consequence capability_manager.md §9 names ("the
        number of consecutive failures that moves a pack to `failed`")
        — called by
        :mod:`ai_os_kernel.capability_manager.health_poller` once a
        pack's own consecutive unhealthy-poll count crosses its
        threshold. The identical audited-transition shape
        :meth:`activate`/:meth:`deactivate` already establish (lock,
        validate, write, record), not a special case."""
        occurred_at = datetime.now(UTC)
        try:
            async with self._engine.begin() as connection:
                from_state = await self._lock_current_state(connection, pack_id)
                if from_state not in _FAILABLE_FROM_STATES:
                    raise InvalidPackTransitionError(
                        f"cannot mark pack '{pack_id}' failed: current state is "
                        f"{from_state.value!r}, expected one of "
                        f"({', '.join(sorted(s.value for s in _FAILABLE_FROM_STATES))})"
                    )

                result = await connection.execute(
                    sa.update(packs)
                    .where(packs.c.pack_id == pack_id, packs.c.state == from_state.value)
                    .values(state=PackState.FAILED.value)
                    .returning(*packs.columns)
                )
                pack_row = result.mappings().one()

                await self._record_transition(
                    connection,
                    pack_id=pack_id,
                    from_state=from_state,
                    to_state=PackState.FAILED,
                    actor=actor,
                    reason=reason,
                    occurred_at=occurred_at,
                )
        except sa.exc.SQLAlchemyError as exc:
            raise PackRegistrationError(f"failed to mark pack '{pack_id}' failed: {exc}") from exc

        return PackRecord.model_validate(dict(pack_row))

    async def record_health(self, *, pack_id: str, health: dict[str, Any]) -> None:
        """A plain metadata write, deliberately outside the audited
        state-transition machinery above — recording a pack's own
        health snapshot is not itself a lifecycle transition (unlike
        `mark_failed`, its real consequence), the same distinction
        capability_manager.md draws between `catalog.packs.health`
        (informational) and `catalog.pack_state_transitions` (the
        audited log). Silently a no-op if `pack_id` does not exist —
        the caller (`health_poller`) already knows it does, since it
        just resolved the pack's own agents against it."""
        async with self._engine.begin() as connection:
            await connection.execute(
                sa.update(packs).where(packs.c.pack_id == pack_id).values(health=health)
            )

    async def get_pack(self, pack_id: str) -> PackRecord | None:
        """A plain, unguarded read — mirrors
        :meth:`~ai_os_kernel.workflow_engine.repository.WorkflowInstanceRepository.get_instance`."""
        async with self._engine.connect() as connection:
            result = await connection.execute(sa.select(packs).where(packs.c.pack_id == pack_id))
            row = result.mappings().one_or_none()
        return PackRecord.model_validate(dict(row)) if row is not None else None

    async def list_packs(self) -> list[PackRecord]:
        """Every real, registered pack (api_architecture.md §6.5:
        "Installed packs + state" — no state filter documented, so none
        is applied here), ordered by ``pack_id`` for a stable,
        deterministic response."""
        async with self._engine.connect() as connection:
            rows = (
                (await connection.execute(sa.select(packs).order_by(packs.c.pack_id)))
                .mappings()
                .all()
            )
        return [PackRecord.model_validate(dict(row)) for row in rows]

    @staticmethod
    async def _lock_current_state(connection: AsyncConnection, pack_id: str) -> PackState:
        """Takes a row lock (``FOR UPDATE``) on ``pack_id``'s row and
        returns its current state — the read half of the atomic
        "read current state, validate, write" sequence :meth:`activate`/
        :meth:`deactivate`/:meth:`mark_failed` all need. Raises
        :class:`PackNotFoundError` if no such row exists; ``pack_id`` is
        not itself the caller's to create here (that is
        :meth:`register`'s job)."""
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
