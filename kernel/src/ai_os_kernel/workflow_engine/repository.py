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

from ai_os_kernel.persistence.schema import workflow_events, workflow_instances, workflow_steps
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
_STEP_EVENT_SCHEMA_VERSION = 1

# The only attempt number that can exist while retry logic is out of
# scope (error_handling_retry.md; data_model.md §4.3 idempotency key is
# derived from (workflow_id, step_name, attempt)).
_FIRST_ATTEMPT = 1

# The only status a workflow_steps row can ever be written with today:
# the executor already ran to completion (or raised, in which case
# nothing is written at all) before advance_workflow's transaction
# opens, so there is no persisted "running" phase to model yet.
_STEP_STATUS_COMPLETED = "completed"


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

    async def list_steps(self, workflow_id: str) -> list[WorkflowStepRecord]: ...

    async def list_events(self, workflow_id: str) -> list[WorkflowEventRecord]: ...

    async def list_instances(
        self, *, limit: int, before: WorkflowListCursor | None = None
    ) -> list[WorkflowInstance]: ...


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
                    completed_seq = instance_row["last_event_seq"]
                    started_seq = completed_seq - 1
                    started_payload = {
                        "stepId": next_step.id,
                        "stepType": next_step.type.value,
                        "attempt": _FIRST_ATTEMPT,
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
                            attempt=_FIRST_ATTEMPT,
                            agent_id=next_step.agent_id,
                            tool_id=next_step.tool_id,
                            prompt_id=next_step.prompt_id,
                            prompt_version=next_step.prompt_version,
                            model_alias=next_step.model_alias,
                            inputs={},
                            outputs=outputs,
                            error=None,
                            idempotency_key=f"{workflow_id}:{next_step.id}:{_FIRST_ATTEMPT}",
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
