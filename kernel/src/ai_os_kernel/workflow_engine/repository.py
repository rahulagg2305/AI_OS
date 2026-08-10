"""Persists a workflow instance, its events, and its state and step
progress — each write is one transaction spanning the snapshot
(`workflow_instances`), the log (`workflow_events`), and — when a step
actually runs — the materialised per-step state (`workflow_steps`,
data_model.md §4.3).

ADR-0011: "Both are written in one transaction, so the snapshot can
never disagree with the log." This is the first component to actually
exercise that guarantee against the Stage B persistence foundation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ai_os_kernel.persistence.schema import (
    workflow_events,
    workflow_instances,
    workflow_leases,
    workflow_steps,
)
from ai_os_kernel.workflow_engine.errors import (
    WorkflowInstanceCreationError,
    WorkflowInvalidTransitionError,
)
from ai_os_kernel.workflow_engine.event_record import WorkflowEventRecord
from ai_os_kernel.workflow_engine.ids import new_event_id, new_step_id, new_workflow_id
from ai_os_kernel.workflow_engine.instance import WorkflowInstance, WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.models import WorkflowStep
from ai_os_kernel.workflow_engine.step_record import WorkflowStepRecord


class WorkflowListCursor(BaseModel):
    """A keyset position in :meth:`WorkflowInstanceRepository.list_instances`'s
    ``created_at`` DESC, ``workflow_id`` DESC ordering — matches the
    existing ``ix_workflow_instances_created_at_desc`` index, with
    ``workflow_id`` (a ULID, itself time-sortable — data_model.md §2) as
    the tiebreaker for rows sharing one ``created_at`` value.

    This is the cursor's *value*, not its wire encoding: opaque-string
    encoding for the HTTP response (api_architecture.md §9:
    ``next_cursor``) is a transport concern that belongs in
    :mod:`ai_os_kernel.routes.workflows`, not here — the repository
    layer only needs to compare positions, never serialize one for a
    client.
    """

    model_config = ConfigDict(frozen=True)

    created_at: datetime
    workflow_id: str


_WORKFLOW_STARTED_EVENT_TYPE = "workflow.started"
_WORKFLOW_COMPLETED_EVENT_TYPE = "workflow.completed"
_WORKFLOW_EVENT_SCHEMA_VERSION = 1

_STATE_TRANSITIONED_EVENT_TYPE = "state.transitioned"
_STATE_TRANSITIONED_SCHEMA_VERSION = 1

_STEP_STARTED_EVENT_TYPE = "step.started"
_STEP_COMPLETED_EVENT_TYPE = "step.completed"
_STEP_FAILED_EVENT_TYPE = "step.failed"
_STEP_EVENT_SCHEMA_VERSION = 1

_STEP_RETRY_SCHEDULED_EVENT_TYPE = "workflow.step_retry_scheduled"
_STEP_RETRY_SCHEDULED_SCHEMA_VERSION = 1

# workflow_steps.status has no CHECK constraint (data_model.md §4.3
# gives it no canonical value list — see the column's own comment on
# the table definition), so a second real value needs no migration.
# "completed" was the only value that could ever exist while a raised
# step exception meant `advance_workflow` — the only writer — was never
# reached; `record_failed_attempt` (added 2026-07-30) is what makes
# "failed" a real, written value now.
_STEP_STATUS_COMPLETED = "completed"
_STEP_STATUS_FAILED = "failed"


class WorkflowInstanceRepository(Protocol):
    """Persistence boundary for workflow instance creation, state
    transitions, step progress, and reading back the snapshot, the
    per-step history, and the append-only event log — the seam a
    fake/in-memory implementation substitutes in unit tests (ADR-0004:
    interface-driven, configuration over code)."""

    async def create(
        self,
        *,
        definition_id: str,
        definition_version: str,
        inputs: dict[str, Any],
        principal_id: str,
        principal_permissions: frozenset[str] | None = None,
        scheduled_at: datetime | None = None,
    ) -> WorkflowInstance: ...

    async def transition_to_running(
        self,
        *,
        workflow_id: str,
        reason: str,
        triggering_event_id: str | None = None,
    ) -> WorkflowInstance: ...

    async def get_instance(self, workflow_id: str) -> WorkflowInstance | None: ...

    async def advance_workflow(
        self,
        *,
        workflow_id: str,
        definition_id: str,
        definition_version: str,
        expected_current_step_id: str | None,
        next_step: WorkflowStep | None,
        outputs: dict[str, Any],
    ) -> WorkflowInstance: ...

    async def reset_current_step(
        self,
        *,
        workflow_id: str,
        definition_id: str,
        definition_version: str,
        expected_current_step_id: str | None,
        retry_to_step_id: str | None,
        reason: str,
    ) -> WorkflowInstance: ...

    async def mark_waiting_for_human(
        self,
        *,
        workflow_id: str,
        definition_id: str,
        definition_version: str,
        expected_current_step_id: str | None,
        reason: str,
    ) -> WorkflowInstance: ...

    async def cancel(self, *, workflow_id: str, reason: str) -> WorkflowInstance: ...

    async def record_failed_attempt(
        self,
        *,
        workflow_id: str,
        definition_id: str,
        definition_version: str,
        expected_current_step_id: str | None,
        step: WorkflowStep,
        error: dict[str, Any],
    ) -> None: ...

    async def list_steps(self, workflow_id: str) -> list[WorkflowStepRecord]: ...

    async def list_events(self, workflow_id: str) -> list[WorkflowEventRecord]: ...

    async def list_instances(
        self, *, limit: int, before: WorkflowListCursor | None = None
    ) -> list[WorkflowInstance]: ...

    async def list_runnable_instances(
        self, *, limit: int, exclude_definition_ids: frozenset[str] = frozenset()
    ) -> list[WorkflowInstance]: ...

    async def list_startable_instances(self, *, limit: int) -> list[WorkflowInstance]: ...


class SqlWorkflowInstanceRepository:
    """The only implementation of :class:`WorkflowInstanceRepository` at
    this stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(
        self,
        *,
        definition_id: str,
        definition_version: str,
        inputs: dict[str, Any],
        principal_id: str,
        principal_permissions: frozenset[str] | None = None,
        scheduled_at: datetime | None = None,
    ) -> WorkflowInstance:
        workflow_id = new_workflow_id()
        event_id = new_event_id()
        # The event's own occurrence time, not the row's write time —
        # deliberately application-supplied rather than
        # database-generated, unlike created_at/updated_at below. An
        # event log should record when something happened, which the
        # application knows and the database commit clock does not.
        occurred_at = datetime.now(UTC)
        payload = {
            "definitionId": definition_id,
            "definitionVersion": definition_version,
            "inputs": inputs,
        }

        try:
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    sa.insert(workflow_instances)
                    .values(
                        workflow_id=workflow_id,
                        definition_id=definition_id,
                        definition_version=definition_version,
                        status=WorkflowInstanceStatus.CREATED.value,
                        inputs=inputs,
                        principal_id=principal_id,
                        principal_permissions=(
                            sorted(principal_permissions)
                            if principal_permissions is not None
                            else None
                        ),
                        scheduled_at=scheduled_at,
                        last_event_seq=1,
                    )
                    .returning(*workflow_instances.columns)
                )
                instance_row = result.mappings().one()

                await connection.execute(
                    sa.insert(workflow_events).values(
                        event_id=event_id,
                        workflow_id=workflow_id,
                        seq=1,
                        event_type=_WORKFLOW_STARTED_EVENT_TYPE,
                        schema_version=_WORKFLOW_EVENT_SCHEMA_VERSION,
                        payload=payload,
                        occurred_at=occurred_at,
                    )
                )
        except sa.exc.SQLAlchemyError as exc:
            raise WorkflowInstanceCreationError(
                f"failed to create workflow instance for definition "
                f"'{definition_id}@{definition_version}': {exc}"
            ) from exc

        return WorkflowInstance.model_validate(dict(instance_row))

    async def transition_to_running(
        self,
        *,
        workflow_id: str,
        reason: str,
        triggering_event_id: str | None = None,
    ) -> WorkflowInstance:
        """Move ``workflow_id`` from ``created`` to ``running``.

        Guarded by the ``UPDATE ... WHERE status = 'created'`` clause
        itself, so the check-and-transition is one atomic statement —
        no separate read-then-write race window. ``last_event_seq`` is
        incremented in the same statement (``last_event_seq + 1``)
        rather than a hardcoded ``2``, so this does not assume it is
        always the second event.
        """
        event_id = new_event_id()
        occurred_at = datetime.now(UTC)

        try:
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    sa.update(workflow_instances)
                    .where(
                        workflow_instances.c.workflow_id == workflow_id,
                        workflow_instances.c.status == WorkflowInstanceStatus.CREATED.value,
                    )
                    .values(
                        status=WorkflowInstanceStatus.RUNNING.value,
                        last_event_seq=workflow_instances.c.last_event_seq + 1,
                        updated_at=sa.func.now(),
                    )
                    .returning(*workflow_instances.columns)
                )
                instance_row = result.mappings().one_or_none()

                if instance_row is None:
                    raise WorkflowInvalidTransitionError(
                        await self._describe_rejected_transition(connection, workflow_id)
                    )

                payload = {
                    "previousStatus": WorkflowInstanceStatus.CREATED.value,
                    "newStatus": WorkflowInstanceStatus.RUNNING.value,
                    "reason": reason,
                    "triggeringEventId": triggering_event_id,
                }
                await connection.execute(
                    sa.insert(workflow_events).values(
                        event_id=event_id,
                        workflow_id=workflow_id,
                        seq=instance_row["last_event_seq"],
                        event_type=_STATE_TRANSITIONED_EVENT_TYPE,
                        schema_version=_STATE_TRANSITIONED_SCHEMA_VERSION,
                        payload=payload,
                        occurred_at=occurred_at,
                    )
                )
        except sa.exc.SQLAlchemyError as exc:
            raise WorkflowInstanceCreationError(
                f"failed to transition workflow instance '{workflow_id}' to running: {exc}"
            ) from exc

        return WorkflowInstance.model_validate(dict(instance_row))

    async def get_instance(self, workflow_id: str) -> WorkflowInstance | None:
        """A plain, unguarded read — used by the service to decide what
        the next step should be before calling :meth:`advance_workflow`,
        which is where the actual atomic guard lives. No leasing/locking
        here: out of scope at this stage."""
        async with self._engine.connect() as connection:
            result = await connection.execute(
                sa.select(workflow_instances).where(workflow_instances.c.workflow_id == workflow_id)
            )
            row = result.mappings().one_or_none()
        return WorkflowInstance.model_validate(dict(row)) if row is not None else None

    async def list_steps(self, workflow_id: str) -> list[WorkflowStepRecord]:
        """A plain, unguarded read — mirrors :meth:`get_instance`. Ordered
        by ``started_at``, the instance's actual execution order (not
        insertion order, though the two coincide today since every row
        is written inside the same transaction it is executed in)."""
        async with self._engine.connect() as connection:
            result = await connection.execute(
                sa.select(workflow_steps)
                .where(workflow_steps.c.workflow_id == workflow_id)
                .order_by(workflow_steps.c.started_at)
            )
            rows = result.mappings().all()
        return [WorkflowStepRecord.model_validate(dict(row)) for row in rows]

    async def list_events(self, workflow_id: str) -> list[WorkflowEventRecord]:
        """A plain, unguarded read — mirrors :meth:`get_instance` and
        :meth:`list_steps`. Ordered by ``seq``, the append-only log's
        own per-instance ordering (data_model.md §4.2: ``UNIQUE
        (workflow_id, seq)``)."""
        async with self._engine.connect() as connection:
            result = await connection.execute(
                sa.select(workflow_events)
                .where(workflow_events.c.workflow_id == workflow_id)
                .order_by(workflow_events.c.seq)
            )
            rows = result.mappings().all()
        return [WorkflowEventRecord.model_validate(dict(row)) for row in rows]

    async def list_instances(
        self, *, limit: int, before: WorkflowListCursor | None = None
    ) -> list[WorkflowInstance]:
        """A plain, unguarded read — mirrors :meth:`get_instance`. Ordered
        newest-first (``created_at`` DESC, ``workflow_id`` DESC —
        matches ``ix_workflow_instances_created_at_desc``), returning up
        to ``limit`` rows positioned strictly after ``before`` in that
        ordering, or the first ``limit`` rows when ``before`` is
        ``None``. The composite ``< (created_at, workflow_id)``
        comparison (a row-wise/tuple comparison, not two independent
        column filters) is what makes this correct keyset pagination
        rather than offset pagination in disguise — a row inserted or
        deleted between page requests cannot skip or duplicate a
        neighbouring row, which is exactly what api_architecture.md §9
        rules offset pagination out for a growing collection."""
        query = (
            sa.select(workflow_instances)
            .order_by(
                workflow_instances.c.created_at.desc(), workflow_instances.c.workflow_id.desc()
            )
            .limit(limit)
        )
        if before is not None:
            query = query.where(
                sa.tuple_(workflow_instances.c.created_at, workflow_instances.c.workflow_id)
                < (before.created_at, before.workflow_id)
            )
        async with self._engine.connect() as connection:
            result = await connection.execute(query)
            rows = result.mappings().all()
        return [WorkflowInstance.model_validate(dict(row)) for row in rows]

    async def list_runnable_instances(
        self, *, limit: int, exclude_definition_ids: frozenset[str] = frozenset()
    ) -> list[WorkflowInstance]:
        """A plain, unguarded read — mirrors :meth:`get_instance`; a
        worker loop's own subsequent :meth:`WorkflowLeaseService.acquire`
        call is the real exclusivity guard, exactly the same
        "list unguarded, then guard on the real write" split
        :meth:`list_instances` already has relative to
        :meth:`advance_workflow`.

        **Not the same query as `list_instances`.** That method serves
        api_architecture.md §9's own paginated, newest-first "browse
        every instance" listing; a worker loop needs the opposite
        question answered — "which `running` instances have no active
        claim right now" — so this is a genuinely different filter
        (``status = 'running'`` and no unexpired ``workflow_leases``
        row), not a parameter added to the existing method. Ordered
        ``created_at`` ASC (oldest-runnable-first), the opposite of
        `list_instances`'s newest-first: a display listing wants recent
        activity up top; a scheduler wants fairness — the
        longest-waiting runnable instance should not starve behind a
        stream of newly-created ones.

        **``exclude_definition_ids`` (``P03-S03-M30-T06``): a real,
        caller-supplied opt-out, not a generic filter.** A system-wide
        worker loop with one fixed executor composition (see
        :class:`~ai_os_kernel.workflow_engine.worker_loop.WorkflowWorkerLoop`'s
        own docstring) cannot correctly advance an instance whose
        definition declares step types that composition has no executor
        for — discovering one anyway would silently mis-advance it (a
        `human_approval` step falling through to a no-op default
        executor, an `agent` step failing to resolve against the wrong
        registry). Empty by default — the identical "absent means
        unaffected" shape every optional capability in this codebase
        already establishes; a caller with a single, fixed composition
        that genuinely handles every step type any definition might
        declare has no reason to exclude anything.
        """
        conditions = [
            workflow_instances.c.status == WorkflowInstanceStatus.RUNNING.value,
            sa.or_(
                workflow_leases.c.lease_id.is_(None),
                workflow_leases.c.expires_at < sa.func.now(),
            ),
        ]
        if exclude_definition_ids:
            conditions.append(workflow_instances.c.definition_id.notin_(exclude_definition_ids))
        query = (
            sa.select(workflow_instances)
            .select_from(
                workflow_instances.outerjoin(
                    workflow_leases,
                    workflow_leases.c.workflow_id == workflow_instances.c.workflow_id,
                )
            )
            .where(*conditions)
            .order_by(workflow_instances.c.created_at)
            .limit(limit)
        )
        async with self._engine.connect() as connection:
            result = await connection.execute(query)
            rows = result.mappings().all()
        return [WorkflowInstance.model_validate(dict(row)) for row in rows]

    async def list_startable_instances(self, *, limit: int) -> list[WorkflowInstance]:
        """A plain, unguarded read — mirrors :meth:`list_runnable_instances`;
        :class:`~ai_os_kernel.workflow_engine.scheduler.WorkflowScheduler`'s
        own subsequent :meth:`transition_to_running` call is the real
        exclusivity guard (its ``WHERE status = 'created'`` clause is
        one atomic check-and-transition, so two concurrent scheduler
        ticks racing the same instance can never both start it).

        The Scheduler's own question (workflow_engine.md §5.13): which
        ``created`` instances have a real, now-due ``scheduled_at`` —
        genuinely different from :meth:`list_runnable_instances`
        (``status = 'running'``, no active lease), since deciding
        *when* a not-yet-started instance should begin is a distinct
        question from discovering already-running work to advance.
        Ordered ``scheduled_at`` ASC (earliest-due-first, the identical
        fairness reasoning ``list_runnable_instances`` already
        establishes for ``created_at``) — a schedule due five minutes
        ago should not wait behind one due five seconds ago.
        """
        query = (
            sa.select(workflow_instances)
            .where(
                workflow_instances.c.status == WorkflowInstanceStatus.CREATED.value,
                workflow_instances.c.scheduled_at.is_not(None),
                workflow_instances.c.scheduled_at <= sa.func.now(),
            )
            .order_by(workflow_instances.c.scheduled_at)
            .limit(limit)
        )
        async with self._engine.connect() as connection:
            result = await connection.execute(query)
            rows = result.mappings().all()
        return [WorkflowInstance.model_validate(dict(row)) for row in rows]

    async def advance_workflow(
        self,
        *,
        workflow_id: str,
        definition_id: str,
        definition_version: str,
        expected_current_step_id: str | None,
        next_step: WorkflowStep | None,
        outputs: dict[str, Any],
    ) -> WorkflowInstance:
        """Advance a `running` instance by exactly one step, or complete
        it if ``next_step`` is ``None``.

        Guarded by the ``UPDATE ... WHERE`` clause: the instance must be
        ``running``, must belong to the given definition (id and
        version — columns that already exist, not a new concept), and
        its ``current_step_id`` must equal ``expected_current_step_id``
        (the value the caller read moments earlier). That last
        comparison is what makes a stale or duplicate call rejected
        rather than silently re-advancing past where the caller thinks
        the instance is — the same atomic check-and-write pattern as
        :meth:`transition_to_running`, generalised from "no step yet"
        (``None``) to "any specific step".

        If ``next_step`` is given: appends ``step.started`` then
        ``step.completed``, writes one ``workflow_steps`` row (materialised
        per-step state, data_model.md §4.3) mirroring those two events, and
        sets ``current_step_id``.
        If ``next_step`` is ``None``: appends ``workflow.completed`` and
        sets ``status = completed`` and ``completed_at``.

        ``workflow_steps.agent_id``/``tool_id``/``prompt_id``/
        ``prompt_version``/``model_alias`` are copied straight from
        ``next_step``'s identically-named attributes — all five of the
        step's own *declared* invocation fields (workflow_architecture.md's
        Step Contract), validated by :class:`~ai_os_kernel.workflow_engine.
        models.WorkflowStep` itself. This is a writer-only change: it
        records what a step *named*, not what actually ran — the
        executor still always dispatches to the same ``EchoAgent``/
        ``EchoTool`` regardless (see :mod:`ai_os_kernel.workflow_engine.
        step_executor`), and nothing here calls the Prompt Engine or the
        LLM Gateway. Resolving a declared id to a different real
        implementation needs a Capability Manager registry that does not
        exist yet.
        """
        occurred_at = datetime.now(UTC)
        current_step_clause = (
            workflow_instances.c.current_step_id.is_(None)
            if expected_current_step_id is None
            else workflow_instances.c.current_step_id == expected_current_step_id
        )

        if next_step is not None:
            values = {
                "current_step_id": next_step.id,
                "last_event_seq": workflow_instances.c.last_event_seq + 2,
                "updated_at": sa.func.now(),
            }
        else:
            values = {
                "status": WorkflowInstanceStatus.COMPLETED.value,
                "last_event_seq": workflow_instances.c.last_event_seq + 1,
                "completed_at": sa.func.now(),
                "updated_at": sa.func.now(),
            }

        try:
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    sa.update(workflow_instances)
                    .where(
                        workflow_instances.c.workflow_id == workflow_id,
                        workflow_instances.c.status == WorkflowInstanceStatus.RUNNING.value,
                        workflow_instances.c.definition_id == definition_id,
                        workflow_instances.c.definition_version == definition_version,
                        current_step_clause,
                    )
                    .values(**values)
                    .returning(*workflow_instances.columns)
                )
                instance_row = result.mappings().one_or_none()

                if instance_row is None:
                    raise WorkflowInvalidTransitionError(
                        await self._describe_rejected_advance(
                            connection,
                            workflow_id,
                            definition_id,
                            definition_version,
                            expected_current_step_id,
                        )
                    )

                if next_step is not None:
                    # The real attempt number — one more than however many
                    # prior rows this exact (workflow_id, step_name) already
                    # has. Every step has zero prior rows on its first-ever
                    # execution (attempt=1, identical to the old hardcoded
                    # constant this replaces), so this is a zero-behavior
                    # -change fix for every existing caller; a genuine
                    # bounded retry (`WorkflowInstanceService.
                    # retry_after_step_failure`, added 2026-07-30) is what
                    # makes a *second* row for the same step_name possible
                    # at all — `uq_workflow_steps_workflow_id_step_name_attempt`
                    # is exactly the constraint that makes reusing
                    # attempt=1 for that second row fail loudly instead of
                    # silently overwriting history.
                    prior_attempts = await connection.execute(
                        sa.select(sa.func.max(workflow_steps.c.attempt)).where(
                            workflow_steps.c.workflow_id == workflow_id,
                            workflow_steps.c.step_name == next_step.id,
                        )
                    )
                    attempt = (prior_attempts.scalar_one_or_none() or 0) + 1

                    completed_seq = instance_row["last_event_seq"]
                    started_seq = completed_seq - 1
                    started_payload = {
                        "stepId": next_step.id,
                        "stepType": next_step.type.value,
                        "attempt": attempt,
                    }
                    completed_payload = {**started_payload, "outputs": outputs}
                    await connection.execute(
                        sa.insert(workflow_events).values(
                            event_id=new_event_id(),
                            workflow_id=workflow_id,
                            seq=started_seq,
                            event_type=_STEP_STARTED_EVENT_TYPE,
                            schema_version=_STEP_EVENT_SCHEMA_VERSION,
                            payload=started_payload,
                            step_id=next_step.id,
                            occurred_at=occurred_at,
                        )
                    )
                    await connection.execute(
                        sa.insert(workflow_events).values(
                            event_id=new_event_id(),
                            workflow_id=workflow_id,
                            seq=completed_seq,
                            event_type=_STEP_COMPLETED_EVENT_TYPE,
                            schema_version=_STEP_EVENT_SCHEMA_VERSION,
                            payload=completed_payload,
                            step_id=next_step.id,
                            occurred_at=occurred_at,
                        )
                    )
                    await connection.execute(
                        sa.insert(workflow_steps).values(
                            step_id=new_step_id(),
                            workflow_id=workflow_id,
                            step_name=next_step.id,
                            step_type=next_step.type.value,
                            status=_STEP_STATUS_COMPLETED,
                            attempt=attempt,
                            agent_id=next_step.agent_id,
                            tool_id=next_step.tool_id,
                            prompt_id=next_step.prompt_id,
                            prompt_version=next_step.prompt_version,
                            model_alias=next_step.model_alias,
                            inputs={},
                            outputs=outputs,
                            error=None,
                            idempotency_key=f"{workflow_id}:{next_step.id}:{attempt}",
                            usage={},
                            started_at=occurred_at,
                            completed_at=occurred_at,
                        )
                    )
                else:
                    await connection.execute(
                        sa.insert(workflow_events).values(
                            event_id=new_event_id(),
                            workflow_id=workflow_id,
                            seq=instance_row["last_event_seq"],
                            event_type=_WORKFLOW_COMPLETED_EVENT_TYPE,
                            schema_version=_WORKFLOW_EVENT_SCHEMA_VERSION,
                            payload={},
                            occurred_at=occurred_at,
                        )
                    )
        except sa.exc.SQLAlchemyError as exc:
            raise WorkflowInstanceCreationError(
                f"failed to advance workflow instance '{workflow_id}': {exc}"
            ) from exc

        return WorkflowInstance.model_validate(dict(instance_row))

    async def reset_current_step(
        self,
        *,
        workflow_id: str,
        definition_id: str,
        definition_version: str,
        expected_current_step_id: str | None,
        retry_to_step_id: str | None,
        reason: str,
    ) -> WorkflowInstance:
        """Move ``current_step_id`` *backward* to ``retry_to_step_id`` —
        the one real, minimal primitive a bounded quality-gate retry
        needs (:meth:`~ai_os_kernel.workflow_engine.service.
        WorkflowInstanceService.retry_after_step_failure`) that
        :meth:`advance_workflow` cannot express: that method only ever
        moves ``current_step_id`` *forward*, to a step it just executed.

        Writes no ``workflow_steps`` row (no step actually ran) but does
        append one real, observable event
        (``workflow.step_retry_scheduled`` — error_handling_retry.md §4:
        "every retry ... must be observable"), so a retry is visible in
        the append-only log even though nothing else about this call
        resembles a normal step execution.

        Guarded by the identical ``UPDATE ... WHERE`` CAS pattern
        :meth:`advance_workflow` already uses (status must be
        ``running``, definition must match, ``current_step_id`` must
        equal ``expected_current_step_id``) — reusing
        :meth:`_describe_rejected_advance` for the rejection message,
        since the guard conditions are identical.
        """
        occurred_at = datetime.now(UTC)
        current_step_clause = (
            workflow_instances.c.current_step_id.is_(None)
            if expected_current_step_id is None
            else workflow_instances.c.current_step_id == expected_current_step_id
        )

        try:
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    sa.update(workflow_instances)
                    .where(
                        workflow_instances.c.workflow_id == workflow_id,
                        workflow_instances.c.status == WorkflowInstanceStatus.RUNNING.value,
                        workflow_instances.c.definition_id == definition_id,
                        workflow_instances.c.definition_version == definition_version,
                        current_step_clause,
                    )
                    .values(
                        current_step_id=retry_to_step_id,
                        last_event_seq=workflow_instances.c.last_event_seq + 1,
                        updated_at=sa.func.now(),
                    )
                    .returning(*workflow_instances.columns)
                )
                instance_row = result.mappings().one_or_none()

                if instance_row is None:
                    raise WorkflowInvalidTransitionError(
                        await self._describe_rejected_advance(
                            connection,
                            workflow_id,
                            definition_id,
                            definition_version,
                            expected_current_step_id,
                        )
                    )

                await connection.execute(
                    sa.insert(workflow_events).values(
                        event_id=new_event_id(),
                        workflow_id=workflow_id,
                        seq=instance_row["last_event_seq"],
                        event_type=_STEP_RETRY_SCHEDULED_EVENT_TYPE,
                        schema_version=_STEP_RETRY_SCHEDULED_SCHEMA_VERSION,
                        payload={
                            "previousStepId": expected_current_step_id,
                            "retryToStepId": retry_to_step_id,
                            "reason": reason,
                        },
                        occurred_at=occurred_at,
                    )
                )
        except sa.exc.SQLAlchemyError as exc:
            raise WorkflowInstanceCreationError(
                f"failed to reset workflow instance '{workflow_id}' for retry: {exc}"
            ) from exc

        return WorkflowInstance.model_validate(dict(instance_row))

    async def mark_waiting_for_human(
        self,
        *,
        workflow_id: str,
        definition_id: str,
        definition_version: str,
        expected_current_step_id: str | None,
        reason: str,
    ) -> WorkflowInstance:
        """Moves a `running` instance to `waiting_for_human` —
        `current_step_id` deliberately **unchanged** (the identical
        "no `workflow_steps` row, current_step_id untouched" shape
        :meth:`reset_current_step` already established for its own
        mid-flight, not-yet-completed transition): the human_approval
        step has not genuinely completed, so there is nothing to
        advance past yet. The *next* real `advance()` call resolves the
        identical human_approval step again — genuinely re-invoking
        :class:`~ai_os_kernel.workflow_engine.human_approval.
        HumanApprovalStepExecutor`, which this time either finds the
        approval still pending (calls back here, a real no-op re-write
        to the same state) or finds a real, recorded decision and
        resolves normally.

        Guarded by the identical CAS pattern
        :meth:`advance_workflow`/:meth:`reset_current_step` already use
        (status must be ``running``, definition must match,
        ``current_step_id`` must equal ``expected_current_step_id``).
        """
        occurred_at = datetime.now(UTC)
        current_step_clause = (
            workflow_instances.c.current_step_id.is_(None)
            if expected_current_step_id is None
            else workflow_instances.c.current_step_id == expected_current_step_id
        )

        try:
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    sa.update(workflow_instances)
                    .where(
                        workflow_instances.c.workflow_id == workflow_id,
                        workflow_instances.c.status == WorkflowInstanceStatus.RUNNING.value,
                        workflow_instances.c.definition_id == definition_id,
                        workflow_instances.c.definition_version == definition_version,
                        current_step_clause,
                    )
                    .values(
                        status=WorkflowInstanceStatus.WAITING_FOR_HUMAN.value,
                        last_event_seq=workflow_instances.c.last_event_seq + 1,
                        updated_at=sa.func.now(),
                    )
                    .returning(*workflow_instances.columns)
                )
                instance_row = result.mappings().one_or_none()

                if instance_row is None:
                    raise WorkflowInvalidTransitionError(
                        await self._describe_rejected_advance(
                            connection,
                            workflow_id,
                            definition_id,
                            definition_version,
                            expected_current_step_id,
                        )
                    )

                await connection.execute(
                    sa.insert(workflow_events).values(
                        event_id=new_event_id(),
                        workflow_id=workflow_id,
                        seq=instance_row["last_event_seq"],
                        event_type=_STATE_TRANSITIONED_EVENT_TYPE,
                        schema_version=_STATE_TRANSITIONED_SCHEMA_VERSION,
                        payload={
                            "previousStatus": WorkflowInstanceStatus.RUNNING.value,
                            "newStatus": WorkflowInstanceStatus.WAITING_FOR_HUMAN.value,
                            "reason": reason,
                        },
                        occurred_at=occurred_at,
                    )
                )
        except sa.exc.SQLAlchemyError as exc:
            raise WorkflowInstanceCreationError(
                f"failed to mark workflow instance '{workflow_id}' waiting for human: {exc}"
            ) from exc

        return WorkflowInstance.model_validate(dict(instance_row))

    async def cancel(self, *, workflow_id: str, reason: str) -> WorkflowInstance:
        """api_architecture.md §6.1's own documented ``POST
        /api/v1/workflows/{id}/cancel`` — workflow_engine.md §7's
        ``cancelled`` state ("Cancelled by an authorized principal"),
        genuinely reached for the first time. Guarded by the identical
        "affects zero rows means refuse" CAS shape
        :meth:`~ai_os_kernel.workflow_engine.human_approval.
        SqlApprovalRepository.decide` already establishes for its own
        one-way, terminal transition — no ``definition_id``/
        ``current_step_id`` match needed, since cancellation does not
        care which step an instance is on.

        **Real, disclosed, narrower scope than full preemption**: this
        stops the instance from ever being *discovered* again by
        ``list_runnable_instances``/``list_startable_instances`` (both
        already filter on a real, still-non-terminal status), the
        identical "prevents re-discovery, does not interrupt an
        already-in-flight step" limit ``mark_waiting_for_human`` already
        has. A worker holding a real lease on this instance right now
        finishes its current step normally; only the *next* attempt to
        advance a genuinely ``cancelled`` instance is refused.

        Only ``created``/``running``/``waiting_for_human`` are included
        in the guard — the only three of the nine declared states any
        real instance is ever actually written into today (`workflow_
        engine.md`'s own Implementation Status: ``waiting_for_retry``/
        ``quality_gate_failed``/``compensating`` are declared, never
        reached by any real writer) — guarding against unreachable
        states would be untestable, speculative code.
        """
        async with self._engine.begin() as connection:
            current = (
                await connection.execute(
                    sa.select(workflow_instances.c.status).where(
                        workflow_instances.c.workflow_id == workflow_id
                    )
                )
            ).scalar_one_or_none()

            result = await connection.execute(
                sa.update(workflow_instances)
                .where(
                    workflow_instances.c.workflow_id == workflow_id,
                    workflow_instances.c.status.in_(
                        (
                            WorkflowInstanceStatus.CREATED.value,
                            WorkflowInstanceStatus.RUNNING.value,
                            WorkflowInstanceStatus.WAITING_FOR_HUMAN.value,
                        )
                    ),
                )
                .values(
                    status=WorkflowInstanceStatus.CANCELLED.value,
                    last_event_seq=workflow_instances.c.last_event_seq + 1,
                    updated_at=sa.func.now(),
                )
                .returning(*workflow_instances.columns)
            )
            instance_row = result.mappings().one_or_none()

            if instance_row is None:
                if current is None:
                    raise WorkflowInvalidTransitionError(
                        f"workflow instance '{workflow_id}' does not exist"
                    )
                raise WorkflowInvalidTransitionError(
                    f"workflow instance '{workflow_id}' cannot be cancelled from its "
                    f"current status '{current}'"
                )

            await connection.execute(
                sa.insert(workflow_events).values(
                    event_id=new_event_id(),
                    workflow_id=workflow_id,
                    seq=instance_row["last_event_seq"],
                    event_type=_STATE_TRANSITIONED_EVENT_TYPE,
                    schema_version=_STATE_TRANSITIONED_SCHEMA_VERSION,
                    payload={
                        "previousStatus": current,
                        "newStatus": WorkflowInstanceStatus.CANCELLED.value,
                        "reason": reason,
                    },
                    occurred_at=datetime.now(UTC),
                )
            )

        return WorkflowInstance.model_validate(dict(instance_row))

    async def record_failed_attempt(
        self,
        *,
        workflow_id: str,
        definition_id: str,
        definition_version: str,
        expected_current_step_id: str | None,
        step: WorkflowStep,
        error: dict[str, Any],
    ) -> None:
        """Writes a real ``workflow_steps`` row (``status="failed"``)
        and a real ``step.failed`` event for a step whose executor
        genuinely raised — closing quality_gate_engine.md §9's own
        "every gate execution must record ... error details"
        requirement, and the identical gap for every other kind of step
        failure (:class:`~ai_os_kernel.workflow_engine.errors.
        AgentOutputValidationError`, etc.): before this method existed,
        a raised exception meant :meth:`advance_workflow` — the only
        writer — was never reached, so a failed attempt left no trace
        in ``workflow_steps`` at all, only the eventual successful one
        (if there ever was one).

        Called by :meth:`~ai_os_kernel.workflow_engine.service.
        WorkflowInstanceService.advance` from inside its own
        ``except Exception`` block, immediately before it re-raises the
        *original* exception unchanged — this method's own job is
        purely the recording side effect, never the failure decision
        itself (that remains :class:`~ai_os_kernel.workflow_engine.
        advance_runner.WorkflowAdvanceRunner`'s, unaffected by this
        method existing at all).

        The real ``attempt`` number is computed identically to
        :meth:`advance_workflow`'s own ``MAX(attempt)+1`` query against
        the same ``(workflow_id, step_name)`` — the two writers share
        one source of truth for "how many real attempts has this step
        had," so a failed attempt followed by a retried, successful one
        gets two distinct, correctly-numbered rows, and a step that
        never fails is completely unaffected (this method is never
        called for it).

        Guarded by the identical ``UPDATE ... WHERE`` CAS pattern
        :meth:`advance_workflow`/:meth:`reset_current_step` already
        use — the instance must still be ``running``, on the same
        definition, at the expected ``current_step_id``.
        ``current_step_id`` itself is never changed here: the step
        genuinely did not complete, so the instance's own position must
        not move.
        """
        occurred_at = datetime.now(UTC)
        current_step_clause = (
            workflow_instances.c.current_step_id.is_(None)
            if expected_current_step_id is None
            else workflow_instances.c.current_step_id == expected_current_step_id
        )

        try:
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    sa.update(workflow_instances)
                    .where(
                        workflow_instances.c.workflow_id == workflow_id,
                        workflow_instances.c.status == WorkflowInstanceStatus.RUNNING.value,
                        workflow_instances.c.definition_id == definition_id,
                        workflow_instances.c.definition_version == definition_version,
                        current_step_clause,
                    )
                    .values(last_event_seq=workflow_instances.c.last_event_seq + 2)
                    .returning(*workflow_instances.columns)
                )
                instance_row = result.mappings().one_or_none()

                if instance_row is None:
                    raise WorkflowInvalidTransitionError(
                        await self._describe_rejected_advance(
                            connection,
                            workflow_id,
                            definition_id,
                            definition_version,
                            expected_current_step_id,
                        )
                    )

                prior_attempts = await connection.execute(
                    sa.select(sa.func.max(workflow_steps.c.attempt)).where(
                        workflow_steps.c.workflow_id == workflow_id,
                        workflow_steps.c.step_name == step.id,
                    )
                )
                attempt = (prior_attempts.scalar_one_or_none() or 0) + 1

                failed_seq = instance_row["last_event_seq"]
                started_seq = failed_seq - 1
                started_payload = {
                    "stepId": step.id,
                    "stepType": step.type.value,
                    "attempt": attempt,
                }
                failed_payload = {**started_payload, "error": error}
                await connection.execute(
                    sa.insert(workflow_events).values(
                        event_id=new_event_id(),
                        workflow_id=workflow_id,
                        seq=started_seq,
                        event_type=_STEP_STARTED_EVENT_TYPE,
                        schema_version=_STEP_EVENT_SCHEMA_VERSION,
                        payload=started_payload,
                        step_id=step.id,
                        occurred_at=occurred_at,
                    )
                )
                await connection.execute(
                    sa.insert(workflow_events).values(
                        event_id=new_event_id(),
                        workflow_id=workflow_id,
                        seq=failed_seq,
                        event_type=_STEP_FAILED_EVENT_TYPE,
                        schema_version=_STEP_EVENT_SCHEMA_VERSION,
                        payload=failed_payload,
                        step_id=step.id,
                        occurred_at=occurred_at,
                    )
                )
                await connection.execute(
                    sa.insert(workflow_steps).values(
                        step_id=new_step_id(),
                        workflow_id=workflow_id,
                        step_name=step.id,
                        step_type=step.type.value,
                        status=_STEP_STATUS_FAILED,
                        attempt=attempt,
                        agent_id=step.agent_id,
                        tool_id=step.tool_id,
                        prompt_id=step.prompt_id,
                        prompt_version=step.prompt_version,
                        model_alias=step.model_alias,
                        inputs={},
                        outputs=None,
                        error=error,
                        idempotency_key=f"{workflow_id}:{step.id}:{attempt}",
                        usage={},
                        started_at=occurred_at,
                        completed_at=occurred_at,
                    )
                )
        except sa.exc.SQLAlchemyError as exc:
            raise WorkflowInstanceCreationError(
                f"failed to record a failed attempt for workflow instance '{workflow_id}': {exc}"
            ) from exc

    @staticmethod
    async def _describe_rejected_transition(connection: AsyncConnection, workflow_id: str) -> str:
        current = await connection.execute(
            sa.select(workflow_instances.c.status).where(
                workflow_instances.c.workflow_id == workflow_id
            )
        )
        status = current.scalar_one_or_none()
        if status is None:
            return f"workflow instance '{workflow_id}' does not exist"
        return (
            f"workflow instance '{workflow_id}' cannot transition to running: "
            f"current status is '{status}', not 'created'"
        )

    @staticmethod
    async def _describe_rejected_advance(
        connection: AsyncConnection,
        workflow_id: str,
        definition_id: str,
        definition_version: str,
        expected_current_step_id: str | None,
    ) -> str:
        current = await connection.execute(
            sa.select(
                workflow_instances.c.status,
                workflow_instances.c.definition_id,
                workflow_instances.c.definition_version,
                workflow_instances.c.current_step_id,
            ).where(workflow_instances.c.workflow_id == workflow_id)
        )
        row = current.mappings().one_or_none()
        if row is None:
            return f"workflow instance '{workflow_id}' does not exist"
        if row["status"] != WorkflowInstanceStatus.RUNNING.value:
            return (
                f"workflow instance '{workflow_id}' cannot advance: "
                f"current status is '{row['status']}', not 'running'"
            )
        if row["definition_id"] != definition_id or row["definition_version"] != definition_version:
            return (
                f"workflow instance '{workflow_id}' was created from definition "
                f"'{row['definition_id']}@{row['definition_version']}', not "
                f"'{definition_id}@{definition_version}'"
            )
        if row["current_step_id"] != expected_current_step_id:
            return (
                f"workflow instance '{workflow_id}' current step is "
                f"'{row['current_step_id']}', not the expected '{expected_current_step_id}' "
                "— it may have already advanced"
            )
        return f"workflow instance '{workflow_id}' rejected the advance"
