"""``POST /api/v1/workflows/{id}/retry`` (`api_architecture.md` §6.1,
"Retry from last failure") through the real composition root
(``bootstrap.build_app()`` + ``_lifespan``), against a real Postgres
container (ADR-0015 — no mocking the database).

**What this route closes.** `P02-S01-M05-T17` made `failed` a state
production code genuinely writes (R-016) — which fixed an infinite retry
loop and, in the same stroke, created a dead end: a workflow could fail
permanently and no operator had any way to act on it. This is the way
out, and it is the last of §6.1's documented routes to be built.

**The test that actually matters is the last one.** Flipping the status
back to `running` is the easy half and proves almost nothing: a `failed`
instance has already spent *both* retry bounds
(``_fail_if_retries_exhausted`` fails a step when either its attempt
count or its elapsed window is gone), so a naive retry would let the
worker loop re-fail the instance on the very first new failure, no
matter what the definition declares. `test_a_retry_grants_a_genuinely_
fresh_retry_budget` drives the real worker loop through a real
exhaustion, a real retry, and a real second exhaustion, and asserts the
step ran the **full** budget again. Without the `retried_at` epoch that
assertion fails — which is the point of the column.
"""

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.advance_runner import WorkflowAdvanceRunner
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository, WorkflowLeaseService
from ai_os_kernel.workflow_engine.models import WorkflowDefinition, WorkflowStep
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import DispatchingStepExecutor, NoOpStepExecutor
from ai_os_kernel.workflow_engine.worker_loop import DEFAULT_RETRY_POLICY, WorkflowWorkerLoop
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "integration-test-signing-key-at-least-32-bytes"  # gitleaks:allow
_DEFINITION_ID = "se.retry_route_test"
_PACK_ID = "se.software_engineering"
_AGENT_ID = "se.software_engineering/analyst"
_STEP_ID = "always_fails"


@pytest.fixture(scope="module")
def database_url() -> Generator[str, None, None]:
    with postgres_container() as postgres:
        url = postgres.get_connection_url()
        previous = os.environ.get("AIOS_DATABASE_URL")
        os.environ["AIOS_DATABASE_URL"] = url
        try:
            command.upgrade(Config(str(ALEMBIC_INI)), "head")
            yield url
        finally:
            if previous is None:
                os.environ.pop("AIOS_DATABASE_URL", None)
            else:
                os.environ["AIOS_DATABASE_URL"] = previous


def _config() -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
    )


def _token(roles: list[str]) -> str:
    claims = {
        "sub": "integration-test-user",
        "roles": roles,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, _SIGNING_KEY, algorithm="HS256")


class _AlwaysFailingStepExecutor:
    """A genuinely, permanently broken step — the only kind that reaches
    a real terminal `failed`, and therefore the only kind this route can
    be honestly tested against.

    **Counts per workflow, not in total.** The database is module-scoped
    and `tick_once(limit=100)` discovers *every* runnable instance, so a
    `running` instance left behind by an earlier test in this file is
    genuinely picked up and executed by a later test's worker. A single
    shared counter therefore over-counts, and did: the budget assertion
    below first failed with `4 == 2` for exactly this reason. That is a
    test-isolation artefact, not a production defect — the worker loop
    is *supposed* to advance every runnable instance it finds.
    """

    def __init__(self) -> None:
        self.calls_by_workflow: dict[str | None, int] = {}

    def call_count_for(self, workflow_id: str) -> int:
        return self.calls_by_workflow.get(workflow_id, 0)

    async def execute(
        self,
        step: WorkflowStep,
        *,
        workflow_id: str | None = None,
        principal_permissions: frozenset[str] | None = None,
        workflow_permissions: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        self.calls_by_workflow[workflow_id] = self.calls_by_workflow.get(workflow_id, 0) + 1
        raise RuntimeError("this step is permanently broken")


def _definition(*, version: str) -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFINITION_ID,
            "name": "Retry Route Test",
            "description": "test fixture",
            "version": version,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [{"id": _STEP_ID, "type": "agent", "agentId": _AGENT_ID}],
            "failureHandling": {"onError": "halt"},
        }
    )


async def _create_running_instance(engine: AsyncEngine, definition: WorkflowDefinition) -> str:
    await SqlWorkflowDefinitionCatalog(engine).register(definition=definition, pack_id=_PACK_ID)
    repository = SqlWorkflowInstanceRepository(engine)
    created = await repository.create(
        definition_id=definition.id,
        definition_version=definition.version,
        inputs={},
        principal_id="retry-route-test-principal",
    )
    await repository.transition_to_running(
        workflow_id=created.workflow_id, reason="worker picked it up"
    )
    return created.workflow_id


def _make_worker(engine: AsyncEngine, executor: _AlwaysFailingStepExecutor) -> WorkflowWorkerLoop:
    repository = SqlWorkflowInstanceRepository(engine)
    catalog = SqlWorkflowDefinitionCatalog(engine)
    return WorkflowWorkerLoop(
        repository=repository,
        advance_runner=WorkflowAdvanceRunner(
            WorkflowInstanceService(
                repository,
                DispatchingStepExecutor(
                    agent_executor=executor,
                    tool_executor=NoOpStepExecutor(),
                    default_executor=NoOpStepExecutor(),
                ),
                catalog,
            ),
            WorkflowLeaseService(SqlWorkflowLeaseRepository(engine)),
        ),
        definition_catalog=catalog,
        worker_id="worker-1",
    )


async def _tick_until_terminal(
    worker: WorkflowWorkerLoop, repository: SqlWorkflowInstanceRepository, workflow_id: str
) -> WorkflowInstanceStatus:
    for _ in range(10):
        await worker.tick_once(limit=100, lease_duration_seconds=60)
        instance = await repository.get_instance(workflow_id)
        assert instance is not None
        if instance.status is not WorkflowInstanceStatus.RUNNING:
            return instance.status
    raise AssertionError("the instance never reached a terminal state")


def _fail_a_real_instance(database_url: str, *, version: str) -> tuple[str, int]:
    """Drive a real instance to a real, persisted `failed` through the
    real worker loop. Returns its id and how many times the step ran."""

    async def _run() -> tuple[str, int]:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(engine, _definition(version=version))
            executor = _AlwaysFailingStepExecutor()
            worker = _make_worker(engine, executor)
            status = await _tick_until_terminal(
                worker, SqlWorkflowInstanceRepository(engine), workflow_id
            )
            assert status is WorkflowInstanceStatus.FAILED
            return workflow_id, executor.call_count_for(workflow_id)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def test_retry_route_requires_authentication(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post("/api/v1/workflows/wf_whatever/retry", json={})

    assert response.status_code == 401


def test_retry_route_requires_workflow_control_not_merely_read(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`viewer` holds `workflow:read` but not `workflow:control`.
    Retrying is a control action — the same gate `cancel` uses, per
    authentication_authorization.md §4.2's own "start / cancel / retry"
    row — so a read-only principal must be refused."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/workflows/wf_whatever/retry",
            json={},
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    assert response.status_code == 403


def test_retrying_a_workflow_that_never_existed_is_404(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/workflows/wf_does_not_exist/retry",
            json={},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )

    assert response.status_code == 404


def test_retrying_a_non_failed_workflow_is_409_not_404(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "Exists but is not retryable" and "does not exist" are genuinely
    different answers and must not be conflated — the identical
    distinction `cancel` already makes."""

    async def _seed() -> str:
        engine = build_engine(database_url)
        try:
            return await _create_running_instance(engine, _definition(version="1.0.1"))
        finally:
            await engine.dispose()

    workflow_id = asyncio.run(_seed())

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/workflows/{workflow_id}/retry",
            json={},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )

    assert response.status_code == 409
    assert "running" in response.json()["detail"]


def test_retrying_a_really_failed_workflow_puts_it_back_to_running(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The documented behaviour, over a genuinely failed instance
    produced by the real worker loop — not a hand-set status."""
    workflow_id, _ = _fail_a_real_instance(database_url, version="1.0.2")

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/workflows/{workflow_id}/retry",
            json={"reason": "the flake is fixed"},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == WorkflowInstanceStatus.RUNNING.value
    # "Retry from last failure": `current_step_id` is left exactly as
    # the failure left it, so the worker resumes where it stopped.
    #
    # Here that value is genuinely `None`, and the first version of this
    # test asserted `_STEP_ID` and failed on it. `current_step_id` is
    # only ever written by `advance_workflow`, which records a step that
    # *completed* — a step whose executor raised never reaches it. So an
    # instance that died on its very first step has no completed step,
    # and `None` correctly means "resume from the beginning", which is
    # the failing step. The retry must not invent a value here.
    assert body["current_step_id"] is None
    # A run that is no longer over must not still read as one.
    assert body["error"] is None
    assert body["completed_at"] is None
    # The epoch is what makes the retry mean anything.
    assert body["retried_at"] is not None


def test_a_second_retry_of_an_already_retried_workflow_is_409(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guarded CAS, over HTTP: two operators racing produce one
    transition and one epoch, not two."""
    workflow_id, _ = _fail_a_real_instance(database_url, version="1.0.3")

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {_token(['operator'])}"}
        first = client.post(f"/api/v1/workflows/{workflow_id}/retry", json={}, headers=headers)
        second = client.post(f"/api/v1/workflows/{workflow_id}/retry", json={}, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 409


def test_a_retry_grants_a_genuinely_fresh_retry_budget(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The decisive test, and the reason `retried_at` exists.

    A failed instance has already spent both bounds
    (``failure_count >= max_attempts`` **and** an elapsed window far past
    ``max_duration_seconds``). Without the retry epoch, the first new
    failure after a retry would immediately re-fail the instance, so the
    step would run exactly **once** more however large the declared
    policy is — a retry in name only.

    With the epoch, ``step_failure_stats`` counts only failures at or
    after it, so the definition's own ``retryPolicy`` applies again in
    full. This drives real ticks through the real worker loop on both
    sides of a real HTTP retry and asserts the second budget equals the
    first.
    """
    workflow_id, first_run_calls = _fail_a_real_instance(database_url, version="1.0.4")
    assert first_run_calls == DEFAULT_RETRY_POLICY.max_attempts

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/workflows/{workflow_id}/retry",
            json={},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )
    assert response.status_code == 202

    async def _drive_again() -> tuple[int, WorkflowInstanceStatus]:
        engine = build_engine(database_url)
        try:
            executor = _AlwaysFailingStepExecutor()
            worker = _make_worker(engine, executor)
            status = await _tick_until_terminal(
                worker, SqlWorkflowInstanceRepository(engine), workflow_id
            )
            return executor.call_count_for(workflow_id), status
        finally:
            await engine.dispose()

    second_run_calls, status = asyncio.run(_drive_again())

    # A *full* second budget, not one grudging extra attempt. This is
    # the assertion that fails without the epoch.
    assert second_run_calls == DEFAULT_RETRY_POLICY.max_attempts, (
        "the retry did not grant a fresh budget — the step ran "
        f"{second_run_calls} time(s), not {DEFAULT_RETRY_POLICY.max_attempts}"
    )
    # And the bound is still real: a permanently-broken step still ends
    # up terminally failed rather than looping forever again.
    assert status is WorkflowInstanceStatus.FAILED
