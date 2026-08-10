"""Unit tests for ``WorkflowWorkerLoop``'s own logic — fake
``repository``/``advance_runner``/``definition_catalog`` throughout,
isolating discovery, per-instance dispatch, and outcome bucketing from
what a real ``WorkflowInstanceRepository``/``WorkflowAdvanceRunner``/
``WorkflowDefinitionCatalog`` do internally, which is already proven,
real, end to end, against a real Postgres container by
``tests/integration/workflow_engine/test_worker_loop_execution.py``
(``P02-S01-M05-T12``, updated ``P02-S01-M05-T14`` for the real catalog
reader)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from ai_os_kernel.workflow_engine.errors import WorkflowLeaseUnavailableError
from ai_os_kernel.workflow_engine.instance import WorkflowInstance, WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.worker_loop import WorkflowWorkerLoop

_DEFINITION_ID = "se.product_creation"
_DEFINITION_VERSION = "1.0.0"


def _definition() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFINITION_ID,
            "name": "Full Product Creation",
            "description": "test fixture",
            "version": _DEFINITION_VERSION,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [
                {
                    "id": "analyze_requirements",
                    "type": "agent",
                    "agentId": "se.software_engineering/analyst",
                }
            ],
            "failureHandling": {"onError": "escalate"},
        }
    )


def _instance(
    *,
    workflow_id: str,
    definition_version: str = _DEFINITION_VERSION,
    definition_id: str = _DEFINITION_ID,
) -> WorkflowInstance:
    now = datetime.now(UTC)
    return WorkflowInstance(
        workflow_id=workflow_id,
        definition_id=definition_id,
        definition_version=definition_version,
        status=WorkflowInstanceStatus.RUNNING,
        current_step_id=None,
        inputs={},
        outputs=None,
        experiment_id=None,
        run_manifest_id=None,
        principal_id="user-42",
        principal_permissions=None,
        scheduled_at=None,
        last_event_seq=2,
        error=None,
        total_cost_usd=Decimal("0"),
        total_tokens=0,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )


class _FakeRepository:
    def __init__(self, instances: list[WorkflowInstance]) -> None:
        self._instances = instances
        self.exclude_definition_ids_calls: list[frozenset[str]] = []

    async def list_runnable_instances(
        self, *, limit: int, exclude_definition_ids: frozenset[str] = frozenset()
    ) -> list[WorkflowInstance]:
        self.exclude_definition_ids_calls.append(exclude_definition_ids)
        instances = [i for i in self._instances if i.definition_id not in exclude_definition_ids]
        return instances[:limit]


class _FakeDefinitionCatalog:
    """Records every lookup; returns whichever definition the test
    registered under the exact `(definition_id, version)` key, or
    `None` — the identical "resolved or genuinely absent" contract the
    real `SqlWorkflowDefinitionCatalog.get` has."""

    def __init__(self, definitions: dict[tuple[str, str], WorkflowDefinition]) -> None:
        self._definitions = definitions
        self.get_calls: list[tuple[str, str]] = []

    async def register(self, *, definition: WorkflowDefinition, pack_id: str) -> None:
        raise NotImplementedError("not exercised by these tests")

    async def get(self, *, definition_id: str, version: str) -> WorkflowDefinition | None:
        self.get_calls.append((definition_id, version))
        return self._definitions.get((definition_id, version))

    async def get_declared_permissions(self, *, definition_id: str, version: str) -> frozenset[str]:
        return frozenset()

    async def list_all(self) -> list[WorkflowDefinition]:
        raise NotImplementedError("not exercised by these tests")


class _FakeAdvanceRunner:
    """Records every call; either succeeds, raises
    ``WorkflowLeaseUnavailableError`` for a configured set of workflow
    ids (simulating a lost lease race), or raises a plain exception for
    another configured set (simulating a genuine per-instance failure)."""

    def __init__(
        self,
        *,
        lease_unavailable_for: set[str] | None = None,
        fails_for: set[str] | None = None,
    ) -> None:
        self._lease_unavailable_for = lease_unavailable_for or set()
        self._fails_for = fails_for or set()
        self.run_calls: list[dict[str, Any]] = []

    async def run_once(
        self,
        *,
        workflow_id: str,
        definition: WorkflowDefinition,
        worker_id: str,
        lease_duration_seconds: int,
    ) -> WorkflowInstance:
        self.run_calls.append(
            {
                "workflow_id": workflow_id,
                "definition": definition,
                "worker_id": worker_id,
                "lease_duration_seconds": lease_duration_seconds,
            }
        )
        if workflow_id in self._lease_unavailable_for:
            raise WorkflowLeaseUnavailableError(f"'{workflow_id}' already leased")
        if workflow_id in self._fails_for:
            raise RuntimeError(f"'{workflow_id}' genuinely failed")
        return _instance(workflow_id=workflow_id)


def _worker(
    *,
    instances: list[WorkflowInstance],
    advance_runner: _FakeAdvanceRunner,
    definitions: dict[tuple[str, str], WorkflowDefinition] | None = None,
) -> WorkflowWorkerLoop:
    return WorkflowWorkerLoop(
        repository=_FakeRepository(instances),  # type: ignore[arg-type]
        advance_runner=advance_runner,  # type: ignore[arg-type]
        definition_catalog=_FakeDefinitionCatalog(
            definitions
            if definitions is not None
            else {(_DEFINITION_ID, _DEFINITION_VERSION): _definition()}
        ),
        worker_id="worker-1",
    )


async def test_it_advances_every_discovered_instance_concurrently() -> None:
    instances = [_instance(workflow_id="wf_a"), _instance(workflow_id="wf_b")]
    advance_runner = _FakeAdvanceRunner()
    worker = _worker(instances=instances, advance_runner=advance_runner)

    result = await worker.tick_once(limit=100, lease_duration_seconds=30)

    assert set(result.advanced) == {"wf_a", "wf_b"}
    assert result.skipped_lease_unavailable == ()
    assert result.skipped_no_definition == ()
    assert result.failed == ()
    assert result.discovered == 2
    assert {call["workflow_id"] for call in advance_runner.run_calls} == {"wf_a", "wf_b"}
    assert all(call["worker_id"] == "worker-1" for call in advance_runner.run_calls)
    assert all(call["lease_duration_seconds"] == 30 for call in advance_runner.run_calls)


async def test_a_lost_lease_race_is_a_skip_not_a_failure() -> None:
    instances = [_instance(workflow_id="wf_a"), _instance(workflow_id="wf_b")]
    advance_runner = _FakeAdvanceRunner(lease_unavailable_for={"wf_b"})
    worker = _worker(instances=instances, advance_runner=advance_runner)

    result = await worker.tick_once(limit=100, lease_duration_seconds=30)

    assert result.advanced == ("wf_a",)
    assert result.skipped_lease_unavailable == ("wf_b",)
    assert result.failed == ()


async def test_a_genuine_per_instance_failure_is_isolated_from_the_rest_of_the_batch() -> None:
    instances = [_instance(workflow_id="wf_a"), _instance(workflow_id="wf_b")]
    advance_runner = _FakeAdvanceRunner(fails_for={"wf_a"})
    worker = _worker(instances=instances, advance_runner=advance_runner)

    result = await worker.tick_once(limit=100, lease_duration_seconds=30)

    assert result.failed == ("wf_a",)
    assert result.advanced == ("wf_b",)


async def test_an_instance_whose_definition_is_not_registered_is_skipped_not_advanced() -> None:
    instances = [_instance(workflow_id="wf_a", definition_version="9.9.9")]
    advance_runner = _FakeAdvanceRunner()
    worker = _worker(instances=instances, advance_runner=advance_runner)

    result = await worker.tick_once(limit=100, lease_duration_seconds=30)

    assert result.skipped_no_definition == ("wf_a",)
    assert result.advanced == ()
    assert advance_runner.run_calls == []


async def test_definitions_are_resolved_by_the_exact_id_and_version_pair() -> None:
    """Two concurrently-running instances of the *same* `definition_id`
    but different `definition_version` must each resolve to their own,
    correct definition object — never collapsed to one just because the
    id matches, the real correctness bug a plain-id-keyed lookup would
    risk once more than one version of a definition is running at
    once."""
    v1 = _definition()
    v2 = v1.model_copy(update={"version": "2.0.0"})
    instances = [
        _instance(workflow_id="wf_v1", definition_version="1.0.0"),
        _instance(workflow_id="wf_v2", definition_version="2.0.0"),
    ]
    advance_runner = _FakeAdvanceRunner()
    worker = _worker(
        instances=instances,
        advance_runner=advance_runner,
        definitions={(_DEFINITION_ID, "1.0.0"): v1, (_DEFINITION_ID, "2.0.0"): v2},
    )

    result = await worker.tick_once(limit=100, lease_duration_seconds=30)

    assert set(result.advanced) == {"wf_v1", "wf_v2"}
    calls_by_id = {call["workflow_id"]: call["definition"] for call in advance_runner.run_calls}
    assert calls_by_id["wf_v1"] is v1
    assert calls_by_id["wf_v2"] is v2


async def test_an_empty_discovery_result_advances_nothing() -> None:
    advance_runner = _FakeAdvanceRunner()
    worker = _worker(instances=[], advance_runner=advance_runner)

    result = await worker.tick_once(limit=100, lease_duration_seconds=30)

    assert result.discovered == 0
    assert advance_runner.run_calls == []


async def test_the_discovery_limit_is_forwarded_to_the_repository() -> None:
    instances = [_instance(workflow_id="wf_a"), _instance(workflow_id="wf_b")]
    advance_runner = _FakeAdvanceRunner()
    worker = _worker(instances=instances, advance_runner=advance_runner)

    result = await worker.tick_once(limit=1, lease_duration_seconds=30)

    assert result.discovered == 1


async def test_exclude_definition_ids_is_forwarded_to_the_repository_and_genuinely_excludes() -> (
    None
):
    """``P03-S03-M30-T06``: a real proof that ``WorkflowWorkerLoop``'s
    own constructor-time ``exclude_definition_ids`` genuinely reaches
    ``list_runnable_instances`` — not merely accepted and dropped — and
    that an instance whose own ``definition_id`` is excluded is never
    discovered, never advanced, at all. The real SQL-level exclusion
    (not merely this fake's own in-memory filter) is proven directly
    against a real Postgres instance in
    ``test_worker_loop_execution.py``."""
    excluded_instance = _instance(workflow_id="wf_excluded", definition_id="se.delivery_pipeline")
    included_instance = _instance(workflow_id="wf_included")
    repository = _FakeRepository([excluded_instance, included_instance])
    advance_runner = _FakeAdvanceRunner()
    worker = WorkflowWorkerLoop(
        repository=repository,  # type: ignore[arg-type]
        advance_runner=advance_runner,  # type: ignore[arg-type]
        definition_catalog=_FakeDefinitionCatalog(
            {(_DEFINITION_ID, _DEFINITION_VERSION): _definition()}
        ),
        worker_id="worker-1",
        exclude_definition_ids=frozenset({"se.delivery_pipeline"}),
    )

    result = await worker.tick_once(limit=100, lease_duration_seconds=30)

    assert repository.exclude_definition_ids_calls == [frozenset({"se.delivery_pipeline"})]
    assert set(result.advanced) == {"wf_included"}
    assert "wf_excluded" not in result.advanced
