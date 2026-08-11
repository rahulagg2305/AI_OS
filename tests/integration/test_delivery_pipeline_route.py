"""Deterministic, real-database verification that the Software
Engineering pack's own real HTTP trigger route
(``POST /api/v1/workflows/se.delivery_pipeline``) genuinely fronts the
real production composition (``ai_os_kernel.bootstrap.build_app()`` +
``_lifespan``'s own ``_build_se_delivery_pipeline_registry``/
``build_pipeline_trigger`` wiring) — not a hand-assembled equivalent,
and not the no-database unit tests in
``tests/unit/kernel/routes/test_delivery_pipeline.py``.

No real Anthropic credential and no seeded ``catalog.agents``/
``catalog.prompts`` rows are used here: the real
``SqlAgentRegistry``-resolved agents can therefore never actually run,
so an authorized request reaches all the way through authentication,
authorization, and the real Workflow Engine machinery, and gets a real,
structured ``failed`` outcome back — proving the security boundary and
the real trigger wiring both work, without needing a live credential or
any real pack registration at all.
Mirrors exactly how ``tests/integration/test_workflows_route.py``'s own
``test_an_authorized_request_reaches_the_real_workflow_engine`` proves
the platform demo route's identical plumbing.

The opt-in live counterpart,
``tests/integration/test_delivery_pipeline_route_live.py``, proves the
full path all the way to a genuine, completed 5-agent run, reusing the
same real ``_register_and_activate_pack`` helper
``tests/integration/workflow_engine/test_delivery_pipeline.py``'s own
live test already established (now backed by the real manifest -> catalog
installer, ``ai_os_kernel.capability_manager.manifest_catalog_installer``).

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

import asyncio
import os
from collections.abc import Generator, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import jwt
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.trace_schema import links
from ai_os_kernel.traceability_engine.ids import compute_artifact_key
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome, WorkflowRunResult
from ai_os_kernel.workflow_engine.delivery_pipeline import DEFINITION_ID
from ai_os_kernel.workflow_engine.instance import WorkflowInstance, WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.models import StepType
from ai_os_kernel.workflow_engine.step_record import WorkflowStepRecord
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "integration-test-signing-key-at-least-32-bytes"
_ROUTE = "/api/v1/workflows/se.delivery_pipeline"


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


def test_an_authorized_request_reaches_the_real_pipeline_trigger(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", raising=False)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            _ROUTE,
            json={"requirement": "print a friendly message"},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_id"]
    # No real Anthropic credential and no seeded catalog rows, so
    # Requirements Analyst (the pipeline's own real first step) cannot
    # actually resolve/run — a real, structured failure, not a security
    # boundary rejection (401/403) or an unhandled crash.
    assert body["outcome"] == "failed"
    assert body["error"]
    assert body["documentation_path"] is None


def test_an_unauthorized_request_never_reaches_the_real_pipeline_trigger(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            _ROUTE,
            json={"requirement": "print a friendly message"},
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    assert response.status_code == 403


_DEFINITION_VERSION = "1.9.0"
_DOCUMENTATION_PATH = "workspace/docs/generated/greeting.md"


def _completed_documentation_instance(workflow_id: str) -> WorkflowInstance:
    """A real ``WorkflowInstance`` as the pipeline would present it when
    paused at ``approve-git-push`` (documentation already produced) —
    every field a genuine value, none a placeholder the route reads."""
    now = datetime.now(UTC)
    return WorkflowInstance(
        workflow_id=workflow_id,
        definition_id=DEFINITION_ID,
        definition_version=_DEFINITION_VERSION,
        status=WorkflowInstanceStatus.WAITING_FOR_HUMAN,
        current_step_id="approve-git-push",
        inputs={"requirement": "print a friendly message"},
        outputs=None,
        experiment_id=None,
        run_manifest_id=None,
        principal_id="integration-test-user",
        principal_permissions=None,
        scheduled_at=None,
        last_event_seq=9,
        error=None,
        total_cost_usd=Decimal("0"),
        total_tokens=0,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )


def _documentation_step(workflow_id: str) -> WorkflowStepRecord:
    now = datetime.now(UTC)
    return WorkflowStepRecord(
        step_id="documentation",
        workflow_id=workflow_id,
        step_name="documentation",
        step_type=StepType.AGENT,
        status="completed",
        attempt=1,
        agent_id="software-engineering/documentation",
        tool_id=None,
        prompt_id="documentation.record_artifact",
        prompt_version="0.1.0",
        model_alias="coding-strong",
        inputs={},
        outputs={"documentationPath": _DOCUMENTATION_PATH},
        error=None,
        idempotency_key=f"{workflow_id}:documentation:1",
        usage={},
        started_at=now,
        completed_at=now,
    )


class _StepsOnlyRepository:
    """Stands in for the real ``workflow_instance_repository`` for the one
    method this route reads (``list_steps``). The pipeline's own real
    step persistence is proven by ``test_delivery_pipeline.py``; what this
    test isolates is the *route's own new trace-writing wiring*, exercised
    through the real ``build_app()`` composition and the real
    ``app.state.trace_link_writer`` bootstrap sets — not a hand-injected
    writer (the exact R-017 anti-pattern this project just fixed)."""

    def __init__(self, step: WorkflowStepRecord) -> None:
        self._step = step

    async def list_steps(self, workflow_id: str) -> list[WorkflowStepRecord]:
        return [self._step]


def test_a_paused_run_records_a_real_produced_documentation_trace_link(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The production-path proof for ``P04-S02-M16-T04``: a real
    ``se.delivery_pipeline`` run that has produced its documentation (and
    paused at ``approve-git-push``) causes the real route — through the
    real ``build_app()`` bootstrap wiring — to write a real
    ``workflow_run --produced--> documentation`` row to real Postgres.

    The trigger and the step-repository read are substituted (their real
    behaviour is proven in ``test_delivery_pipeline.py``); the writer is
    **not** — it is the one bootstrap itself constructs. Reverting the
    route's trace-writing wiring leaves no row and fails this test."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", raising=False)
    workflow_id = "wf_route_produced_documentation"

    async def _fake_trigger(
        inputs: dict[str, Any], principal_id: str, **_: Any
    ) -> WorkflowRunResult:
        return WorkflowRunResult(
            workflow_id=workflow_id,
            outcome=WorkflowRunOutcome.WAITING_FOR_HUMAN,
            iterations=8,
            last_instance=_completed_documentation_instance(workflow_id),
        )

    app = build_app(_config())
    with TestClient(app) as client:
        # Override AFTER lifespan startup, so the real
        # app.state.trace_link_writer bootstrap set stays in place.
        app.state.trigger_se_delivery_pipeline = _fake_trigger
        app.state.workflow_instance_repository = _StepsOnlyRepository(
            _documentation_step(workflow_id)
        )
        response = client.post(
            _ROUTE,
            json={"requirement": "print a friendly message"},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "waiting_for_human"
    # Now populated for a paused run too — the doc genuinely exists.
    assert body["documentation_path"] == _DOCUMENTATION_PATH

    source_key = compute_artifact_key(artifact_type="workflow_run", external_id=workflow_id)
    target_key = compute_artifact_key(
        artifact_type="documentation", external_id=_DOCUMENTATION_PATH
    )

    async def _read_link() -> Sequence[Any]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:
                return (
                    await connection.execute(
                        select(links).where(
                            links.c.source_key == source_key,
                            links.c.target_key == target_key,
                            links.c.relationship == "produced",
                            links.c.closed_at.is_(None),
                        )
                    )
                ).all()
        finally:
            await engine.dispose()

    rows = asyncio.run(_read_link())
    assert len(rows) == 1, "the real route did not write the produced-documentation trace link"
    assert rows[0].confidence == "confirmed"
    assert rows[0].created_by == DEFINITION_ID
    assert rows[0].created_by_type == "process"
