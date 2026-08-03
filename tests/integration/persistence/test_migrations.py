"""Alembic migrations against a real Postgres container (ADR-0015 — no
mocking the database; the schema/constraint behaviour under test is
exactly what a mock would hide).

Migration commands (``command.upgrade``/``command.downgrade``) are
synchronous and drive Alembic's own async engine internally
(``kernel/alembic/env.py``); calling them from a synchronous test avoids
nesting one asyncio event loop inside another.
"""

import asyncio
import os
from collections.abc import Generator
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.engine import build_engine
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_EXPECTED_TABLES = {
    "workflow_instances",
    "workflow_events",
    "workflow_leases",
    "workflow_steps",
    "approvals",
}

_EXPECTED_GOVERNANCE_TABLES = {"audit_log", "config_changes"}

_EXPECTED_PLATFORM_TABLES = {"event_outbox", "idempotency_keys"}

_EXPECTED_TRACE_TABLES = {"artifacts", "links"}

_EXPECTED_CATALOG_TABLES = {
    "workflow_definitions",
    "prompts",
    "tools",
    "agents",
    "packs",
    "pack_state_transitions",
}

_EXPECTED_EVALUATION_TABLES = {
    "run_manifests",
    "experiment_runs",
    "experiments",
    "gate_results",
    "metrics",
    "llm_calls",
}

_EXPECTED_KNOWLEDGE_TABLES = {"documents", "chunks", "embeddings", "memory_items"}


@pytest.fixture(scope="module")
def database_url() -> Generator[str, None, None]:
    with postgres_container() as postgres:
        url = postgres.get_connection_url()
        previous = os.environ.get("AIOS_DATABASE_URL")
        os.environ["AIOS_DATABASE_URL"] = url
        try:
            yield url
        finally:
            if previous is None:
                os.environ.pop("AIOS_DATABASE_URL", None)
            else:
                os.environ["AIOS_DATABASE_URL"] = previous


@pytest.fixture()
def alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


@pytest.fixture(autouse=True)
def _ensure_default_workflow_definition_registered(
    database_url: str, alembic_config: Config
) -> None:
    """Every test in this file that inserts a `workflow.workflow_instances`
    row uses the same (`def_test`, `1.0.0`) definition_id/definition_version
    pair. Since `workflow_instances` now carries a real composite foreign
    key to `catalog.workflow_definitions` (migration
    `0023_workflow_definition_fk`), that row must already exist.

    Idempotent (`ON CONFLICT DO NOTHING`) and re-run before *every* test
    in this file (not just once) because
    `test_migration_up_down_up_round_trip` downgrades all the way to
    `base` and back up — which would otherwise wipe this row for every
    test that runs after it.
    """
    command.upgrade(alembic_config, "head")

    async def _ensure() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.workflow_definitions "
                        "(definition_id, version, pack_id, graph, inputs_schema, "
                        " outputs_schema, declared_permissions, validated_at) "
                        "VALUES ('def_test', '1.0.0', 'se.software_engineering', "
                        " '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now()) "
                        "ON CONFLICT (definition_id, version) DO NOTHING"
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(_ensure())


async def _table_names(database_url: str, schema: str) -> set[str]:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:

            def _inspect(sync_connection: sa.Connection) -> set[str]:
                return set(sa.inspect(sync_connection).get_table_names(schema=schema))

            return await connection.run_sync(_inspect)
    finally:
        await engine.dispose()


async def _schema_exists(database_url: str, schema: str) -> bool:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                sa.text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :schema"),
                {"schema": schema},
            )
            return result.first() is not None
    finally:
        await engine.dispose()


def test_migration_up_down_up_round_trip(database_url: str, alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    assert asyncio.run(_table_names(database_url, "workflow")) == _EXPECTED_TABLES
    assert asyncio.run(_table_names(database_url, "governance")) == _EXPECTED_GOVERNANCE_TABLES
    assert asyncio.run(_table_names(database_url, "platform")) == _EXPECTED_PLATFORM_TABLES
    assert asyncio.run(_table_names(database_url, "trace")) == _EXPECTED_TRACE_TABLES
    assert asyncio.run(_table_names(database_url, "catalog")) == _EXPECTED_CATALOG_TABLES
    assert asyncio.run(_table_names(database_url, "evaluation")) == _EXPECTED_EVALUATION_TABLES
    assert asyncio.run(_table_names(database_url, "knowledge")) == _EXPECTED_KNOWLEDGE_TABLES

    # Downgrading all the way to base removes everything every migration
    # created, including all seven schemas themselves (there are now
    # twenty-nine migrations in the chain, so "-1" alone would only undo
    # the most recent one).
    command.downgrade(alembic_config, "base")
    assert asyncio.run(_schema_exists(database_url, "workflow")) is False
    assert asyncio.run(_schema_exists(database_url, "governance")) is False
    assert asyncio.run(_schema_exists(database_url, "platform")) is False
    assert asyncio.run(_schema_exists(database_url, "trace")) is False
    assert asyncio.run(_schema_exists(database_url, "catalog")) is False
    assert asyncio.run(_schema_exists(database_url, "evaluation")) is False
    assert asyncio.run(_schema_exists(database_url, "knowledge")) is False

    # Re-upgrading restores the identical shape.
    command.upgrade(alembic_config, "head")
    assert asyncio.run(_table_names(database_url, "workflow")) == _EXPECTED_TABLES
    assert asyncio.run(_table_names(database_url, "governance")) == _EXPECTED_GOVERNANCE_TABLES
    assert asyncio.run(_table_names(database_url, "platform")) == _EXPECTED_PLATFORM_TABLES
    assert asyncio.run(_table_names(database_url, "trace")) == _EXPECTED_TRACE_TABLES
    assert asyncio.run(_table_names(database_url, "catalog")) == _EXPECTED_CATALOG_TABLES
    assert asyncio.run(_table_names(database_url, "evaluation")) == _EXPECTED_EVALUATION_TABLES
    assert asyncio.run(_table_names(database_url, "knowledge")) == _EXPECTED_KNOWLEDGE_TABLES


def test_workflow_instances_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_instances() -> tuple[set[str], list[str], bool]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(
                    sync_connection: sa.Connection,
                ) -> tuple[set[str], list[str], bool]:
                    insp = sa.inspect(sync_connection)
                    columns = {
                        c["name"] for c in insp.get_columns("workflow_instances", schema="workflow")
                    }
                    pk = insp.get_pk_constraint("workflow_instances", schema="workflow")
                    checks = insp.get_check_constraints("workflow_instances", schema="workflow")
                    has_status_check = any(
                        c["name"] == "ck_workflow_instances_status" for c in checks
                    )
                    return columns, pk["constrained_columns"], has_status_check

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns, has_status_check = asyncio.run(_inspect_instances())

    assert columns == {
        "workflow_id",
        "definition_id",
        "definition_version",
        "status",
        "current_step_id",
        "inputs",
        "outputs",
        "experiment_id",
        "run_manifest_id",
        "principal_id",
        "principal_permissions",
        "last_event_seq",
        "error",
        "total_cost_usd",
        "total_tokens",
        "created_at",
        "updated_at",
        "completed_at",
    }
    assert pk_columns == ["workflow_id"]
    assert has_status_check


def test_workflow_events_enforces_unique_workflow_id_and_seq(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_unique_constraint() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_test_unique', 'def_test', '1.0.0', 'created', "
                        " '{}'::jsonb, 'user_test', 0)"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_events "
                        "(event_id, workflow_id, seq, event_type, schema_version, "
                        " payload, occurred_at) "
                        "VALUES ('evt_1', 'wf_test_unique', 1, 'workflow.started', 1, "
                        " '{}'::jsonb, now())"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO workflow.workflow_events "
                            "(event_id, workflow_id, seq, event_type, schema_version, "
                            " payload, occurred_at) "
                            "VALUES ('evt_2', 'wf_test_unique', 1, 'workflow.duplicate_seq', 1, "
                            " '{}'::jsonb, now())"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_unique_constraint())


def test_workflow_steps_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_steps() -> tuple[set[str], list[str], bool]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(
                    sync_connection: sa.Connection,
                ) -> tuple[set[str], list[str], bool]:
                    insp = sa.inspect(sync_connection)
                    columns = {
                        c["name"] for c in insp.get_columns("workflow_steps", schema="workflow")
                    }
                    pk = insp.get_pk_constraint("workflow_steps", schema="workflow")
                    checks = insp.get_check_constraints("workflow_steps", schema="workflow")
                    has_step_type_check = any(
                        c["name"] == "ck_workflow_steps_step_type" for c in checks
                    )
                    return columns, pk["constrained_columns"], has_step_type_check

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns, has_step_type_check = asyncio.run(_inspect_steps())

    assert columns == {
        "step_id",
        "workflow_id",
        "step_name",
        "step_type",
        "status",
        "attempt",
        "agent_id",
        "tool_id",
        "prompt_id",
        "prompt_version",
        "model_alias",
        "inputs",
        "outputs",
        "error",
        "idempotency_key",
        "usage",
        "started_at",
        "completed_at",
    }
    assert pk_columns == ["step_id"]
    assert has_step_type_check


def test_workflow_steps_enforces_unique_workflow_id_step_name_attempt(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_unique_constraint() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_test_step_unique', 'def_test', '1.0.0', 'created', "
                        " '{}'::jsonb, 'user_test', 0)"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_steps "
                        "(step_id, workflow_id, step_name, step_type, status, attempt, "
                        " inputs, outputs, idempotency_key, usage, started_at, completed_at) "
                        "VALUES ('stp_1', 'wf_test_step_unique', 'analyze_requirements', "
                        " 'agent', 'completed', 1, '{}'::jsonb, '{}'::jsonb, "
                        " 'wf_test_step_unique:analyze_requirements:1', '{}'::jsonb, now(), now())"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO workflow.workflow_steps "
                            "(step_id, workflow_id, step_name, step_type, status, attempt, "
                            " inputs, outputs, idempotency_key, usage, started_at, completed_at) "
                            "VALUES ('stp_2', 'wf_test_step_unique', 'analyze_requirements', "
                            " 'agent', 'completed', 1, '{}'::jsonb, '{}'::jsonb, "
                            " 'wf_test_step_unique:analyze_requirements:1', '{}'::jsonb, now(), "
                            " now())"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_unique_constraint())


def test_workflow_leases_requires_an_existing_workflow_instance(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO workflow.workflow_leases "
                            "(lease_id, workflow_id, worker_id, acquired_at, "
                            " expires_at, heartbeat_at) "
                            "VALUES ('lease_orphan', 'wf_does_not_exist', 'worker_1', "
                            " now(), now(), now())"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_approvals_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_approvals() -> tuple[set[str], list[str], bool]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(
                    sync_connection: sa.Connection,
                ) -> tuple[set[str], list[str], bool]:
                    insp = sa.inspect(sync_connection)
                    columns = {c["name"] for c in insp.get_columns("approvals", schema="workflow")}
                    pk = insp.get_pk_constraint("approvals", schema="workflow")
                    checks = insp.get_check_constraints("approvals", schema="workflow")
                    has_status_check = any(c["name"] == "ck_approvals_status" for c in checks)
                    return columns, pk["constrained_columns"], has_status_check

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns, has_status_check = asyncio.run(_inspect_approvals())

    assert columns == {
        "approval_id",
        "workflow_id",
        "step_id",
        "approval_class",
        "title",
        "description",
        "context_digest",
        "options",
        "status",
        "decided_by",
        "decision_comment",
        "requested_at",
        "expires_at",
        "decided_at",
    }
    assert pk_columns == ["approval_id"]
    assert has_status_check


def test_approvals_status_check_constraint_rejects_an_invalid_value(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_check_constraint() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_test_approval_status', 'def_test', '1.0.0', 'created', "
                        " '{}'::jsonb, 'user_test', 0)"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO workflow.approvals "
                            "(approval_id, workflow_id, step_id, approval_class, title, "
                            " description, context_digest, options, status, requested_at) "
                            "VALUES ('appr_1', 'wf_test_approval_status', 'review_step', "
                            " 'human_review', 'Review output', 'Please review', 'sha256:abc', "
                            " '[]'::jsonb, 'not_a_real_status', now())"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_check_constraint())


def test_approvals_requires_an_existing_workflow_instance(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO workflow.approvals "
                            "(approval_id, workflow_id, step_id, approval_class, title, "
                            " description, context_digest, options, status, requested_at) "
                            "VALUES ('appr_orphan', 'wf_does_not_exist', 'review_step', "
                            " 'human_review', 'Review output', 'Please review', 'sha256:abc', "
                            " '[]'::jsonb, 'pending', now())"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_governance_audit_log_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_audit_log() -> tuple[set[str], list[str], bool]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(
                    sync_connection: sa.Connection,
                ) -> tuple[set[str], list[str], bool]:
                    insp = sa.inspect(sync_connection)
                    columns = {
                        c["name"] for c in insp.get_columns("audit_log", schema="governance")
                    }
                    pk = insp.get_pk_constraint("audit_log", schema="governance")
                    checks = insp.get_check_constraints("audit_log", schema="governance")
                    has_outcome_check = any(c["name"] == "ck_audit_log_outcome" for c in checks)
                    return columns, pk["constrained_columns"], has_outcome_check

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns, has_outcome_check = asyncio.run(_inspect_audit_log())

    assert columns == {
        "audit_id",
        "seq",
        "event_type",
        "principal_id",
        "principal_type",
        "resource_type",
        "resource_id",
        "outcome",
        "detail",
        "trace_id",
        "prev_hash",
        "row_hash",
        "occurred_at",
    }
    assert pk_columns == ["audit_id"]
    assert has_outcome_check


def test_governance_audit_log_outcome_check_constraint_rejects_an_invalid_value(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_check_constraint() -> None:
        engine = build_engine(database_url)
        try:
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO governance.audit_log "
                            "(audit_id, event_type, principal_id, principal_type, outcome, "
                            " detail, row_hash, occurred_at) "
                            "VALUES ('audit_1', 'auth.success', 'user-42', 'user', "
                            " 'not_a_real_outcome', '{}'::jsonb, 'sha256:abc', now())"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_check_constraint())


def test_governance_audit_log_seq_auto_increments_and_is_unique(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_seq() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO governance.audit_log "
                        "(audit_id, event_type, principal_id, principal_type, outcome, "
                        " detail, row_hash, occurred_at) "
                        "VALUES ('audit_seq_1', 'auth.success', 'user-42', 'user', 'success', "
                        " '{}'::jsonb, 'sha256:first', now())"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO governance.audit_log "
                        "(audit_id, event_type, principal_id, principal_type, outcome, "
                        " detail, row_hash, prev_hash, occurred_at) "
                        "VALUES ('audit_seq_2', 'auth.success', 'user-42', 'user', 'success', "
                        " '{}'::jsonb, 'sha256:second', 'sha256:first', now())"
                    )
                )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT audit_id, seq FROM governance.audit_log "
                        "WHERE audit_id IN ('audit_seq_1', 'audit_seq_2') ORDER BY seq"
                    )
                )
                rows = result.mappings().all()

            assert [row["audit_id"] for row in rows] == ["audit_seq_1", "audit_seq_2"]
            assert rows[0]["seq"] < rows[1]["seq"]

            # The UNIQUE constraint on seq rejects a duplicate, hand-assigned value.
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO governance.audit_log "
                            "(audit_id, seq, event_type, principal_id, principal_type, outcome, "
                            " detail, row_hash, occurred_at) "
                            "VALUES ('audit_seq_dupe', :dupe_seq, 'auth.success', 'user-42', "
                            " 'user', 'success', '{}'::jsonb, 'sha256:dupe', now())"
                        ),
                        {"dupe_seq": rows[0]["seq"]},
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_seq())


def test_governance_config_changes_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_config_changes() -> tuple[set[str], list[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(sync_connection: sa.Connection) -> tuple[set[str], list[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {
                        c["name"] for c in insp.get_columns("config_changes", schema="governance")
                    }
                    pk = insp.get_pk_constraint("config_changes", schema="governance")
                    return columns, pk["constrained_columns"]

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns = asyncio.run(_inspect_config_changes())

    assert columns == {
        "change_id",
        "config_key",
        "old_value_digest",
        "new_value_digest",
        "changed_by",
        "reason",
        "changed_at",
    }
    assert pk_columns == ["change_id"]


def test_governance_config_changes_allows_a_null_old_or_new_digest(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_nullable_digests() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                # A config key's first-ever value: no prior value to digest.
                await connection.execute(
                    sa.text(
                        "INSERT INTO governance.config_changes "
                        "(change_id, config_key, new_value_digest, changed_by, reason, "
                        " changed_at) "
                        "VALUES ('change_create', 'llm.default_model', 'sha256:new', "
                        " 'user-42', 'initial configuration', now())"
                    )
                )
                # A key being removed entirely: no new value to digest.
                await connection.execute(
                    sa.text(
                        "INSERT INTO governance.config_changes "
                        "(change_id, config_key, old_value_digest, changed_by, reason, "
                        " changed_at) "
                        "VALUES ('change_delete', 'llm.default_model', 'sha256:old', "
                        " 'user-42', 'deprecated setting removed', now())"
                    )
                )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT change_id, old_value_digest, new_value_digest "
                        "FROM governance.config_changes "
                        "WHERE change_id IN ('change_create', 'change_delete') "
                        "ORDER BY change_id"
                    )
                )
                rows = {row["change_id"]: row for row in result.mappings().all()}

            assert rows["change_create"]["old_value_digest"] is None
            assert rows["change_create"]["new_value_digest"] == "sha256:new"
            assert rows["change_delete"]["old_value_digest"] == "sha256:old"
            assert rows["change_delete"]["new_value_digest"] is None
        finally:
            await engine.dispose()

    asyncio.run(_exercise_nullable_digests())


def test_platform_event_outbox_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_event_outbox() -> tuple[set[str], list[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(sync_connection: sa.Connection) -> tuple[set[str], list[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {
                        c["name"] for c in insp.get_columns("event_outbox", schema="platform")
                    }
                    pk = insp.get_pk_constraint("event_outbox", schema="platform")
                    return columns, pk["constrained_columns"]

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns = asyncio.run(_inspect_event_outbox())

    assert columns == {
        "outbox_id",
        "event_type",
        "schema_version",
        "payload",
        "trace_id",
        "created_at",
        "dispatched_at",
        "attempts",
    }
    assert pk_columns == ["outbox_id"]


def test_platform_event_outbox_attempts_defaults_to_zero_and_dispatched_at_is_nullable(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_defaults() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO platform.event_outbox "
                        "(outbox_id, event_type, schema_version, payload, created_at) "
                        "VALUES ('outbox_1', 'workflow.started', 1, '{}'::jsonb, now())"
                    )
                )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT attempts, dispatched_at FROM platform.event_outbox "
                        "WHERE outbox_id = 'outbox_1'"
                    )
                )
                row = result.mappings().one()

            assert row["attempts"] == 0
            assert row["dispatched_at"] is None
        finally:
            await engine.dispose()

    asyncio.run(_exercise_defaults())


def test_platform_idempotency_keys_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_idempotency_keys() -> tuple[set[str], list[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(sync_connection: sa.Connection) -> tuple[set[str], list[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {
                        c["name"] for c in insp.get_columns("idempotency_keys", schema="platform")
                    }
                    pk = insp.get_pk_constraint("idempotency_keys", schema="platform")
                    return columns, pk["constrained_columns"]

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns = asyncio.run(_inspect_idempotency_keys())

    assert columns == {
        "key",
        "principal_id",
        "request_digest",
        "response",
        "status_code",
        "created_at",
        "expires_at",
    }
    assert pk_columns == ["key"]


def test_trace_artifacts_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_artifacts() -> tuple[set[str], list[str], bool]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(
                    sync_connection: sa.Connection,
                ) -> tuple[set[str], list[str], bool]:
                    insp = sa.inspect(sync_connection)
                    columns = {c["name"] for c in insp.get_columns("artifacts", schema="trace")}
                    pk = insp.get_pk_constraint("artifacts", schema="trace")
                    checks = insp.get_check_constraints("artifacts", schema="trace")
                    has_type_check = any(c["name"] == "ck_artifacts_artifact_type" for c in checks)
                    return columns, pk["constrained_columns"], has_type_check

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns, has_type_check = asyncio.run(_inspect_artifacts())

    assert columns == {
        "artifact_key",
        "artifact_type",
        "external_id",
        "title",
        "location",
        "version",
    }
    assert pk_columns == ["artifact_key"]
    assert has_type_check


def test_trace_links_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_links() -> tuple[set[str], list[str], set[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(
                    sync_connection: sa.Connection,
                ) -> tuple[set[str], list[str], set[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {c["name"] for c in insp.get_columns("links", schema="trace")}
                    pk = insp.get_pk_constraint("links", schema="trace")
                    checks = insp.get_check_constraints("links", schema="trace")
                    check_names = {c["name"] for c in checks if c["name"] is not None}
                    return columns, pk["constrained_columns"], check_names

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns, check_names = asyncio.run(_inspect_links())

    assert columns == {
        "link_id",
        "source_key",
        "relationship",
        "target_key",
        "confidence",
        "created_by",
        "created_by_type",
        "created_at",
        "closed_at",
    }
    assert pk_columns == ["link_id"]
    assert check_names == {
        "ck_links_relationship",
        "ck_links_confidence",
        "ck_links_created_by_type",
    }


async def _insert_artifact(engine: AsyncEngine, artifact_key: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO trace.artifacts "
                "(artifact_key, artifact_type, external_id, title, location, version) "
                "VALUES (:artifact_key, 'requirement', 'REQ-1', 'A requirement', "
                " 'docs/requirements.md', '1.0.0')"
            ),
            {"artifact_key": artifact_key},
        )


def test_trace_links_requires_existing_artifacts(database_url: str, alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            await _insert_artifact(engine, "art_source_only")

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO trace.links "
                            "(link_id, source_key, relationship, target_key, confidence, "
                            " created_by, created_by_type, created_at) "
                            "VALUES ('link_orphan', 'art_source_only', 'implements', "
                            " 'art_does_not_exist', 'confirmed', 'user-42', 'user', now())"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_trace_links_partial_unique_index_allows_reopening_a_closed_link(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_partial_unique_index() -> None:
        engine = build_engine(database_url)
        try:
            await _insert_artifact(engine, "art_reopen_source")
            await _insert_artifact(engine, "art_reopen_target")

            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO trace.links "
                        "(link_id, source_key, relationship, target_key, confidence, "
                        " created_by, created_by_type, created_at) "
                        "VALUES ('link_1', 'art_reopen_source', 'implements', "
                        " 'art_reopen_target', 'confirmed', 'user-42', 'user', now())"
                    )
                )

            # A second *open* link for the identical (source, relationship,
            # target) triple is rejected by the partial unique index.
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO trace.links "
                            "(link_id, source_key, relationship, target_key, confidence, "
                            " created_by, created_by_type, created_at) "
                            "VALUES ('link_2', 'art_reopen_source', 'implements', "
                            " 'art_reopen_target', 'confirmed', 'user-42', 'user', now())"
                        )
                    )

            # Closing the first link frees the triple up again: a new open
            # link for the same triple is now accepted.
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text("UPDATE trace.links SET closed_at = now() WHERE link_id = 'link_1'")
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO trace.links "
                        "(link_id, source_key, relationship, target_key, confidence, "
                        " created_by, created_by_type, created_at) "
                        "VALUES ('link_3', 'art_reopen_source', 'implements', "
                        " 'art_reopen_target', 'confirmed', 'user-42', 'user', now())"
                    )
                )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT link_id, closed_at FROM trace.links "
                        "WHERE link_id IN ('link_1', 'link_3') ORDER BY link_id"
                    )
                )
                rows = {row["link_id"]: row for row in result.mappings().all()}

            assert rows["link_1"]["closed_at"] is not None
            assert rows["link_3"]["closed_at"] is None
        finally:
            await engine.dispose()

    asyncio.run(_exercise_partial_unique_index())


def test_catalog_workflow_definitions_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_workflow_definitions() -> tuple[set[str], list[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(sync_connection: sa.Connection) -> tuple[set[str], list[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {
                        c["name"]
                        for c in insp.get_columns("workflow_definitions", schema="catalog")
                    }
                    pk = insp.get_pk_constraint("workflow_definitions", schema="catalog")
                    return columns, pk["constrained_columns"]

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns = asyncio.run(_inspect_workflow_definitions())

    assert columns == {
        "definition_id",
        "pack_id",
        "version",
        "graph",
        "inputs_schema",
        "outputs_schema",
        "declared_permissions",
        "validated_at",
    }
    assert set(pk_columns) == {"definition_id", "version"}


def test_catalog_workflow_definitions_requires_all_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_not_null_columns() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.workflow_definitions "
                        "(definition_id, pack_id, version, graph, inputs_schema, "
                        " outputs_schema, declared_permissions, validated_at) "
                        "VALUES ('def_1', 'se.software_engineering', '1.0.0', "
                        " '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now())"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO catalog.workflow_definitions "
                            "(definition_id, pack_id, version, graph, inputs_schema, "
                            " outputs_schema, declared_permissions) "
                            "VALUES ('def_missing_validated_at', 'se.software_engineering', "
                            " '1.0.0', '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '[]'::jsonb)"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_not_null_columns())


def test_catalog_workflow_definitions_composite_primary_key(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_composite_primary_key() -> None:
        engine = build_engine(database_url)
        try:
            # The whole point of the composite (definition_id, version)
            # primary key: two versions of the *same* definition_id are
            # both accepted, which a single-column definition_id PK
            # would have rejected outright.
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.workflow_definitions "
                        "(definition_id, pack_id, version, graph, inputs_schema, "
                        " outputs_schema, declared_permissions, validated_at) "
                        "VALUES ('se.product_creation', 'se.software_engineering', "
                        " '1.0.0', '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now())"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.workflow_definitions "
                        "(definition_id, pack_id, version, graph, inputs_schema, "
                        " outputs_schema, declared_permissions, validated_at) "
                        "VALUES ('se.product_creation', 'se.software_engineering', "
                        " '2.0.0', '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now())"
                    )
                )

            # The exact same (definition_id, version) pair a second time
            # is still rejected — uniqueness on the pair, not silently
            # dropped altogether.
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO catalog.workflow_definitions "
                            "(definition_id, pack_id, version, graph, inputs_schema, "
                            " outputs_schema, declared_permissions, validated_at) "
                            "VALUES ('se.product_creation', 'se.software_engineering', "
                            " '2.0.0', '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now())"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_composite_primary_key())


def test_workflow_instances_definition_foreign_key_rejects_an_unregistered_definition(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO workflow.workflow_instances "
                            "(workflow_id, definition_id, definition_version, status, "
                            " inputs, principal_id, last_event_seq) "
                            "VALUES ('wf_unregistered_definition', 'def_never_registered', "
                            " '1.0.0', 'created', '{}'::jsonb, 'user_test', 0)"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_workflow_instances_definition_foreign_key_accepts_a_registered_definition(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_real_definition() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.workflow_definitions "
                        "(definition_id, pack_id, version, graph, inputs_schema, "
                        " outputs_schema, declared_permissions, validated_at) "
                        "VALUES ('def_registered', 'se.software_engineering', '3.0.0', "
                        " '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now())"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_registered_definition', 'def_registered', '3.0.0', "
                        " 'created', '{}'::jsonb, 'user_test', 0)"
                    )
                )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT definition_id, definition_version "
                        "FROM workflow.workflow_instances "
                        "WHERE workflow_id = 'wf_registered_definition'"
                    )
                )
                row = result.mappings().one()

            assert row["definition_id"] == "def_registered"
            assert row["definition_version"] == "3.0.0"
        finally:
            await engine.dispose()

    asyncio.run(_exercise_real_definition())


def test_catalog_prompts_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_prompts() -> tuple[set[str], list[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(sync_connection: sa.Connection) -> tuple[set[str], list[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {c["name"] for c in insp.get_columns("prompts", schema="catalog")}
                    pk = insp.get_pk_constraint("prompts", schema="catalog")
                    return columns, pk["constrained_columns"]

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns = asyncio.run(_inspect_prompts())

    assert columns == {
        "prompt_id",
        "pack_id",
        "version",
        "content",
        "input_schema",
        "content_hash",
    }
    assert set(pk_columns) == {"prompt_id", "version"}


def test_catalog_prompts_composite_primary_key(database_url: str, alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_composite_primary_key() -> None:
        engine = build_engine(database_url)
        try:
            # The whole point of the composite (prompt_id, version)
            # primary key: two versions of the *same* prompt_id are both
            # accepted, which a single-column prompt_id PK would have
            # rejected outright.
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.prompts "
                        "(prompt_id, pack_id, version, content, input_schema, content_hash) "
                        "VALUES ('prompt_composite_pk', 'se.software_engineering', '1.0.0', "
                        " 'You are a helpful assistant.', '{}'::jsonb, 'sha256:abc')"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.prompts "
                        "(prompt_id, pack_id, version, content, input_schema, content_hash) "
                        "VALUES ('prompt_composite_pk', 'se.software_engineering', '2.0.0', "
                        " 'You are a more helpful assistant.', '{}'::jsonb, 'sha256:def')"
                    )
                )

            # The exact same (prompt_id, version) pair a second time is
            # still rejected — uniqueness on the pair, not silently
            # dropped altogether.
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO catalog.prompts "
                            "(prompt_id, pack_id, version, content, input_schema, content_hash) "
                            "VALUES ('prompt_composite_pk', 'se.software_engineering', "
                            " '2.0.0', 'a duplicate row', '{}'::jsonb, 'sha256:ghi')"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_composite_primary_key())


def test_catalog_prompts_requires_all_columns(database_url: str, alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_not_null_columns() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.prompts "
                        "(prompt_id, pack_id, version, content, input_schema, content_hash) "
                        "VALUES ('prompt_1', 'se.software_engineering', '1.0.0', "
                        " 'You are a helpful assistant.', '{}'::jsonb, 'sha256:abc')"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO catalog.prompts "
                            "(prompt_id, pack_id, version, content, input_schema) "
                            "VALUES ('prompt_missing_hash', 'se.software_engineering', "
                            " '1.0.0', 'You are a helpful assistant.', '{}'::jsonb)"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_not_null_columns())


def test_catalog_tools_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_tools() -> tuple[set[str], list[str], bool]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(
                    sync_connection: sa.Connection,
                ) -> tuple[set[str], list[str], bool]:
                    insp = sa.inspect(sync_connection)
                    columns = {c["name"] for c in insp.get_columns("tools", schema="catalog")}
                    pk = insp.get_pk_constraint("tools", schema="catalog")
                    checks = insp.get_check_constraints("tools", schema="catalog")
                    has_trust_tier_check = any(c["name"] == "ck_tools_trust_tier" for c in checks)
                    return columns, pk["constrained_columns"], has_trust_tier_check

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns, has_trust_tier_check = asyncio.run(_inspect_tools())

    assert columns == {
        "tool_id",
        "pack_id",
        "version",
        "entrypoint",
        "trust_tier",
        "input_schema",
        "output_schema",
        "required_permissions",
    }
    assert pk_columns == ["tool_id"]
    assert has_trust_tier_check


def test_catalog_tools_trust_tier_check_constraint_rejects_an_invalid_value(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_check_constraint() -> None:
        engine = build_engine(database_url)
        try:
            # Both documented values are accepted.
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.tools "
                        "(tool_id, pack_id, version, entrypoint, trust_tier, input_schema, "
                        " output_schema, required_permissions) "
                        "VALUES ('tool_sandboxed', 'se.software_engineering', '1.0.0', "
                        " 'pack.tools:Tool', 'tier1_sandboxed', '{}'::jsonb, '{}'::jsonb, "
                        " '[]'::jsonb)"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.tools "
                        "(tool_id, pack_id, version, entrypoint, trust_tier, input_schema, "
                        " output_schema, required_permissions) "
                        "VALUES ('tool_trusted', 'se.software_engineering', '1.0.0', "
                        " 'pack.tools:Tool', 'tier2_trusted', '{}'::jsonb, '{}'::jsonb, "
                        " '[]'::jsonb)"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO catalog.tools "
                            "(tool_id, pack_id, version, entrypoint, trust_tier, input_schema, "
                            " output_schema, required_permissions) "
                            "VALUES ('tool_invalid', 'se.software_engineering', '1.0.0', "
                            " 'pack.tools:Tool', 'not_a_real_tier', '{}'::jsonb, '{}'::jsonb, "
                            " '[]'::jsonb)"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_check_constraint())


def test_catalog_agents_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_agents() -> tuple[set[str], list[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(sync_connection: sa.Connection) -> tuple[set[str], list[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {c["name"] for c in insp.get_columns("agents", schema="catalog")}
                    pk = insp.get_pk_constraint("agents", schema="catalog")
                    return columns, pk["constrained_columns"]

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns = asyncio.run(_inspect_agents())

    assert columns == {
        "agent_id",
        "pack_id",
        "version",
        "entrypoint",
        "input_schema",
        "output_schema",
        "required_permissions",
        "required_tools",
    }
    assert pk_columns == ["agent_id"]


def test_catalog_agents_requires_all_columns(database_url: str, alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_not_null_columns() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.agents "
                        "(agent_id, pack_id, version, entrypoint, input_schema, output_schema, "
                        " required_permissions, required_tools) "
                        "VALUES ('se.software_engineering/requirements-analyst', "
                        " 'se.software_engineering', '1.0.0', 'pack.agents:Agent', "
                        " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb)"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO catalog.agents "
                            "(agent_id, pack_id, version, entrypoint, input_schema, "
                            " output_schema, required_permissions) "
                            "VALUES ('se.software_engineering/missing-tools', "
                            " 'se.software_engineering', '1.0.0', 'pack.agents:Agent', "
                            " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb)"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_not_null_columns())


def test_catalog_packs_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_packs() -> tuple[set[str], list[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(sync_connection: sa.Connection) -> tuple[set[str], list[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {c["name"] for c in insp.get_columns("packs", schema="catalog")}
                    pk = insp.get_pk_constraint("packs", schema="catalog")
                    return columns, pk["constrained_columns"]

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns = asyncio.run(_inspect_packs())

    assert columns == {
        "pack_id",
        "version",
        "state",
        "manifest",
        "sdk_version",
        "min_kernel_version",
        "installed_at",
        "activated_at",
        "health",
    }
    assert pk_columns == ["pack_id"]


def test_catalog_packs_state_check_constraint_rejects_an_invalid_value(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_check_constraint() -> None:
        engine = build_engine(database_url)
        try:
            # A sample of documented values is accepted.
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.packs "
                        "(pack_id, version, state, manifest, sdk_version, min_kernel_version) "
                        "VALUES ('se.software_engineering', '1.0.0', 'discovered', "
                        " '{}'::jsonb, '1.0.0', '1.0.0')"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.packs "
                        "(pack_id, version, state, manifest, sdk_version, min_kernel_version) "
                        "VALUES ('se.project_intelligence', '1.0.0', 'activated', "
                        " '{}'::jsonb, '1.0.0', '1.0.0')"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO catalog.packs "
                            "(pack_id, version, state, manifest, sdk_version, "
                            " min_kernel_version) "
                            "VALUES ('se.invalid_state', '1.0.0', 'not_a_real_state', "
                            " '{}'::jsonb, '1.0.0', '1.0.0')"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_check_constraint())


def test_catalog_packs_requires_all_columns(database_url: str, alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_not_null_columns() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.packs "
                        "(pack_id, version, state, manifest, sdk_version, min_kernel_version) "
                        "VALUES ('se.software_engineering_complete', '1.0.0', 'discovered', "
                        " '{}'::jsonb, '1.0.0', '1.0.0')"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO catalog.packs "
                            "(pack_id, version, state, manifest, min_kernel_version) "
                            "VALUES ('se.missing_sdk_version', '1.0.0', 'discovered', "
                            " '{}'::jsonb, '1.0.0')"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_not_null_columns())


def test_catalog_packs_installed_activated_and_health_accept_null(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_nullable_columns() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.packs "
                        "(pack_id, version, state, manifest, sdk_version, min_kernel_version) "
                        "VALUES ('se.freshly_discovered', '1.0.0', 'discovered', "
                        " '{}'::jsonb, '1.0.0', '1.0.0')"
                    )
                )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT installed_at, activated_at, health FROM catalog.packs "
                        "WHERE pack_id = 'se.freshly_discovered'"
                    )
                )
                row = result.mappings().one()

            assert row["installed_at"] is None
            assert row["activated_at"] is None
            assert row["health"] is None
        finally:
            await engine.dispose()

    asyncio.run(_exercise_nullable_columns())


def test_catalog_pack_state_transitions_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_pack_state_transitions() -> tuple[set[str], list[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(sync_connection: sa.Connection) -> tuple[set[str], list[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {
                        c["name"]
                        for c in insp.get_columns("pack_state_transitions", schema="catalog")
                    }
                    pk = insp.get_pk_constraint("pack_state_transitions", schema="catalog")
                    return columns, pk["constrained_columns"]

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns = asyncio.run(_inspect_pack_state_transitions())

    assert columns == {
        "transition_id",
        "pack_id",
        "from_state",
        "to_state",
        "reason",
        "actor",
        "occurred_at",
    }
    assert pk_columns == ["transition_id"]


def test_catalog_pack_state_transitions_requires_an_existing_pack(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO catalog.pack_state_transitions "
                            "(transition_id, pack_id, from_state, to_state, reason, "
                            " actor, occurred_at) "
                            "VALUES ('transition_orphan', 'se.does_not_exist', "
                            " 'discovered', 'validated', 'manifest passed validation', "
                            " 'manifest_loader', now())"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_catalog_pack_state_transitions_state_check_constraints_reject_invalid_values(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_check_constraints() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.packs "
                        "(pack_id, version, state, manifest, sdk_version, min_kernel_version) "
                        "VALUES ('se.pack_for_transitions', '1.0.0', 'validated', "
                        " '{}'::jsonb, '1.0.0', '1.0.0')"
                    )
                )
                # Both documented states are accepted for from_state/to_state.
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.pack_state_transitions "
                        "(transition_id, pack_id, from_state, to_state, reason, "
                        " actor, occurred_at) "
                        "VALUES ('transition_valid', 'se.pack_for_transitions', "
                        " 'discovered', 'validated', 'manifest passed validation', "
                        " 'manifest_loader', now())"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO catalog.pack_state_transitions "
                            "(transition_id, pack_id, from_state, to_state, reason, "
                            " actor, occurred_at) "
                            "VALUES ('transition_bad_from_state', "
                            " 'se.pack_for_transitions', 'not_a_real_state', 'validated', "
                            " 'manifest passed validation', 'manifest_loader', now())"
                        )
                    )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO catalog.pack_state_transitions "
                            "(transition_id, pack_id, from_state, to_state, reason, "
                            " actor, occurred_at) "
                            "VALUES ('transition_bad_to_state', "
                            " 'se.pack_for_transitions', 'discovered', 'not_a_real_state', "
                            " 'manifest passed validation', 'manifest_loader', now())"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_check_constraints())


def test_catalog_pack_state_transitions_requires_all_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_not_null_columns() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.packs "
                        "(pack_id, version, state, manifest, sdk_version, min_kernel_version) "
                        "VALUES ('se.pack_for_complete_transition', '1.0.0', 'validated', "
                        " '{}'::jsonb, '1.0.0', '1.0.0')"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.pack_state_transitions "
                        "(transition_id, pack_id, from_state, to_state, reason, "
                        " actor, occurred_at) "
                        "VALUES ('transition_complete', "
                        " 'se.pack_for_complete_transition', 'discovered', 'validated', "
                        " 'manifest passed validation', 'manifest_loader', now())"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO catalog.pack_state_transitions "
                            "(transition_id, pack_id, from_state, to_state, reason, "
                            " actor) "
                            "VALUES ('transition_missing_occurred_at', "
                            " 'se.pack_for_complete_transition', 'discovered', 'validated', "
                            " 'manifest passed validation', 'manifest_loader')"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_not_null_columns())


def test_evaluation_run_manifests_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_run_manifests() -> tuple[set[str], list[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(sync_connection: sa.Connection) -> tuple[set[str], list[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {
                        c["name"] for c in insp.get_columns("run_manifests", schema="evaluation")
                    }
                    pk = insp.get_pk_constraint("run_manifests", schema="evaluation")
                    return columns, pk["constrained_columns"]

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns = asyncio.run(_inspect_run_manifests())

    assert columns == {"run_manifest_id", "workflow_id", "manifest", "manifest_hash"}
    assert pk_columns == ["run_manifest_id"]


def test_evaluation_run_manifests_requires_an_existing_workflow_instance(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO evaluation.run_manifests "
                            "(run_manifest_id, workflow_id, manifest, manifest_hash) "
                            "VALUES ('manifest_orphan', 'wf_does_not_exist', "
                            " '{}'::jsonb, 'sha256:abc')"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_evaluation_run_manifests_accepts_an_existing_workflow_instance(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_real_workflow_id() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_test_run_manifest', 'def_test', '1.0.0', 'created', "
                        " '{}'::jsonb, 'user_test', 0)"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO evaluation.run_manifests "
                        "(run_manifest_id, workflow_id, manifest, manifest_hash) "
                        "VALUES ('manifest_real', 'wf_test_run_manifest', "
                        " '{}'::jsonb, 'sha256:abc')"
                    )
                )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT workflow_id FROM evaluation.run_manifests "
                        "WHERE run_manifest_id = 'manifest_real'"
                    )
                )
                row = result.mappings().one()

            assert row["workflow_id"] == "wf_test_run_manifest"
        finally:
            await engine.dispose()

    asyncio.run(_exercise_real_workflow_id())


def test_workflow_instances_run_manifest_id_foreign_key_rejects_unknown_manifest(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO workflow.workflow_instances "
                            "(workflow_id, definition_id, definition_version, status, "
                            " inputs, principal_id, last_event_seq, run_manifest_id) "
                            "VALUES ('wf_bad_manifest_ref', 'def_test', '1.0.0', 'created', "
                            " '{}'::jsonb, 'user_test', 0, 'manifest_does_not_exist')"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_workflow_instances_run_manifest_id_foreign_key_accepts_a_real_manifest(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_real_manifest() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                # Insert the instance first with no manifest yet (the
                # manifest's own FK requires an existing workflow_id),
                # then the manifest, then point the instance at it —
                # the same insert-then-update pattern any real writer of
                # this mutual relationship would need, since each side's
                # foreign key requires the other row to exist first.
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_with_manifest', 'def_test', '1.0.0', 'created', "
                        " '{}'::jsonb, 'user_test', 0)"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO evaluation.run_manifests "
                        "(run_manifest_id, workflow_id, manifest, manifest_hash) "
                        "VALUES ('manifest_for_wf_with_manifest', 'wf_with_manifest', "
                        " '{}'::jsonb, 'sha256:abc')"
                    )
                )
                await connection.execute(
                    sa.text(
                        "UPDATE workflow.workflow_instances "
                        "SET run_manifest_id = 'manifest_for_wf_with_manifest' "
                        "WHERE workflow_id = 'wf_with_manifest'"
                    )
                )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT run_manifest_id FROM workflow.workflow_instances "
                        "WHERE workflow_id = 'wf_with_manifest'"
                    )
                )
                row = result.mappings().one()

            assert row["run_manifest_id"] == "manifest_for_wf_with_manifest"
        finally:
            await engine.dispose()

    asyncio.run(_exercise_real_manifest())


def test_evaluation_experiment_runs_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_experiment_runs() -> tuple[set[str], list[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(sync_connection: sa.Connection) -> tuple[set[str], list[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {
                        c["name"] for c in insp.get_columns("experiment_runs", schema="evaluation")
                    }
                    pk = insp.get_pk_constraint("experiment_runs", schema="evaluation")
                    return columns, pk["constrained_columns"]

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns = asyncio.run(_inspect_experiment_runs())

    assert columns == {
        "run_id",
        "experiment_id",
        "workflow_id",
        "variant_key",
        "model_alias",
        "resolved_model_id",
        "replicate_index",
        "served_from_cache",
        "status",
    }
    assert pk_columns == ["run_id"]


def test_evaluation_experiment_runs_requires_an_existing_workflow_instance(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            # A real evaluation.experiments row is inserted first so the
            # only foreign key this insert can violate is workflow_id's —
            # isolating exactly the constraint this test is about, now
            # that experiment_id also carries a real foreign key (see
            # test_experiment_runs_experiment_id_foreign_key_* below).
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO evaluation.experiments "
                        "(experiment_id, name, description, definition_id, "
                        " definition_version, variables, pinned_conditions, "
                        " runs_per_variant, status, created_by) "
                        "VALUES ('exp_test', 'Test experiment', 'desc', 'def_test', "
                        " '1.0.0', '{}'::jsonb, '{}'::jsonb, 1, 'draft', 'user_test')"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO evaluation.experiment_runs "
                            "(run_id, experiment_id, workflow_id, variant_key, model_alias, "
                            " resolved_model_id, replicate_index, served_from_cache, status) "
                            "VALUES ('run_orphan', 'exp_test', 'wf_does_not_exist', "
                            " 'control', 'fast', 'gpt-x', 0, false, 'pending')"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_evaluation_experiment_runs_requires_all_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_not_null_columns() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO evaluation.experiments "
                        "(experiment_id, name, description, definition_id, "
                        " definition_version, variables, pinned_conditions, "
                        " runs_per_variant, status, created_by) "
                        "VALUES ('exp_for_experiment_run', 'Test experiment', 'desc', "
                        " 'def_test', '1.0.0', '{}'::jsonb, '{}'::jsonb, 1, 'draft', "
                        " 'user_test')"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_for_experiment_run', 'def_test', '1.0.0', 'created', "
                        " '{}'::jsonb, 'user_test', 0)"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO evaluation.experiment_runs "
                        "(run_id, experiment_id, workflow_id, variant_key, model_alias, "
                        " resolved_model_id, replicate_index, served_from_cache, status) "
                        "VALUES ('run_complete', 'exp_for_experiment_run', "
                        " 'wf_for_experiment_run', 'control', 'fast', 'gpt-x', 0, false, "
                        " 'pending')"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO evaluation.experiment_runs "
                            "(run_id, experiment_id, workflow_id, variant_key, model_alias, "
                            " resolved_model_id, replicate_index, status) "
                            "VALUES ('run_missing_served_from_cache', 'exp_for_experiment_run', "
                            " 'wf_for_experiment_run', 'control', 'fast', 'gpt-x', 0, 'pending')"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_not_null_columns())


def test_evaluation_experiments_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_experiments() -> tuple[set[str], list[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(sync_connection: sa.Connection) -> tuple[set[str], list[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {
                        c["name"] for c in insp.get_columns("experiments", schema="evaluation")
                    }
                    pk = insp.get_pk_constraint("experiments", schema="evaluation")
                    return columns, pk["constrained_columns"]

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns = asyncio.run(_inspect_experiments())

    assert columns == {
        "experiment_id",
        "name",
        "description",
        "definition_id",
        "definition_version",
        "variables",
        "pinned_conditions",
        "runs_per_variant",
        "status",
        "created_by",
    }
    assert pk_columns == ["experiment_id"]


def test_evaluation_experiments_requires_all_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_not_null_columns() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO evaluation.experiments "
                        "(experiment_id, name, description, definition_id, "
                        " definition_version, variables, pinned_conditions, "
                        " runs_per_variant, status, created_by) "
                        "VALUES ('exp_complete', 'Complete experiment', 'desc', 'def_test', "
                        " '1.0.0', '{}'::jsonb, '{}'::jsonb, 3, 'draft', 'user_test')"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO evaluation.experiments "
                            "(experiment_id, name, description, definition_id, "
                            " definition_version, variables, pinned_conditions, status, "
                            " created_by) "
                            "VALUES ('exp_missing_runs_per_variant', 'Bad experiment', 'desc', "
                            " 'def_test', '1.0.0', '{}'::jsonb, '{}'::jsonb, 'draft', "
                            " 'user_test')"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_not_null_columns())


def test_experiments_definition_foreign_key_rejects_an_unregistered_definition(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO evaluation.experiments "
                            "(experiment_id, name, description, definition_id, "
                            " definition_version, variables, pinned_conditions, "
                            " runs_per_variant, status, created_by) "
                            "VALUES ('exp_unregistered_definition', 'Bad experiment', 'desc', "
                            " 'def_never_registered', '1.0.0', '{}'::jsonb, '{}'::jsonb, 1, "
                            " 'draft', 'user_test')"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_experiments_definition_foreign_key_accepts_a_registered_definition(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO evaluation.experiments "
                        "(experiment_id, name, description, definition_id, "
                        " definition_version, variables, pinned_conditions, "
                        " runs_per_variant, status, created_by) "
                        "VALUES ('exp_registered_definition', 'Good experiment', 'desc', "
                        " 'def_test', '1.0.0', '{}'::jsonb, '{}'::jsonb, 1, 'draft', "
                        " 'user_test')"
                    )
                )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT definition_id, definition_version FROM evaluation.experiments "
                        "WHERE experiment_id = 'exp_registered_definition'"
                    )
                )
                row = result.mappings().one()

            assert row["definition_id"] == "def_test"
            assert row["definition_version"] == "1.0.0"
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_experiment_runs_experiment_id_foreign_key_rejects_unknown_experiment(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_for_bad_experiment_ref', 'def_test', '1.0.0', 'created', "
                        " '{}'::jsonb, 'user_test', 0)"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO evaluation.experiment_runs "
                            "(run_id, experiment_id, workflow_id, variant_key, model_alias, "
                            " resolved_model_id, replicate_index, served_from_cache, status) "
                            "VALUES ('run_bad_experiment_ref', 'exp_does_not_exist', "
                            " 'wf_for_bad_experiment_ref', 'control', 'fast', 'gpt-x', 0, "
                            " false, 'pending')"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_experiment_runs_experiment_id_foreign_key_accepts_a_real_experiment(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_real_experiment() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO evaluation.experiments "
                        "(experiment_id, name, description, definition_id, "
                        " definition_version, variables, pinned_conditions, "
                        " runs_per_variant, status, created_by) "
                        "VALUES ('exp_real', 'Real experiment', 'desc', 'def_test', "
                        " '1.0.0', '{}'::jsonb, '{}'::jsonb, 2, 'running', 'user_test')"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_for_real_experiment', 'def_test', '1.0.0', 'created', "
                        " '{}'::jsonb, 'user_test', 0)"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO evaluation.experiment_runs "
                        "(run_id, experiment_id, workflow_id, variant_key, model_alias, "
                        " resolved_model_id, replicate_index, served_from_cache, status) "
                        "VALUES ('run_real', 'exp_real', 'wf_for_real_experiment', "
                        " 'control', 'fast', 'gpt-x', 0, false, 'pending')"
                    )
                )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT experiment_id FROM evaluation.experiment_runs "
                        "WHERE run_id = 'run_real'"
                    )
                )
                row = result.mappings().one()

            assert row["experiment_id"] == "exp_real"
        finally:
            await engine.dispose()

    asyncio.run(_exercise_real_experiment())


def test_evaluation_gate_results_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_gate_results() -> tuple[set[str], list[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(sync_connection: sa.Connection) -> tuple[set[str], list[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {
                        c["name"] for c in insp.get_columns("gate_results", schema="evaluation")
                    }
                    pk = insp.get_pk_constraint("gate_results", schema="evaluation")
                    return columns, pk["constrained_columns"]

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns = asyncio.run(_inspect_gate_results())

    assert columns == {
        "result_id",
        "workflow_id",
        "step_id",
        "gate_id",
        "gate_version",
        "status",
        "severity",
        "metrics",
        "messages",
        "duration_ms",
    }
    assert pk_columns == ["result_id"]


def test_evaluation_gate_results_requires_an_existing_workflow_instance(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO evaluation.gate_results "
                            "(result_id, workflow_id, step_id, gate_id, gate_version, "
                            " status, severity, metrics, messages, duration_ms) "
                            "VALUES ('result_orphan', 'wf_does_not_exist', 'step_1', "
                            " 'se.lint', '1.0.0', 'failed', 'error', '{}'::jsonb, "
                            " '[]'::jsonb, 120)"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_evaluation_gate_results_requires_all_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_not_null_columns() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_for_gate_result', 'def_test', '1.0.0', 'created', "
                        " '{}'::jsonb, 'user_test', 0)"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO evaluation.gate_results "
                        "(result_id, workflow_id, step_id, gate_id, gate_version, "
                        " status, severity, metrics, messages, duration_ms) "
                        "VALUES ('result_complete', 'wf_for_gate_result', 'step_1', "
                        " 'se.lint', '1.0.0', 'passed', 'info', '{}'::jsonb, '[]'::jsonb, 42)"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO evaluation.gate_results "
                            "(result_id, workflow_id, step_id, gate_id, gate_version, "
                            " status, severity, metrics, messages) "
                            "VALUES ('result_missing_duration', 'wf_for_gate_result', "
                            " 'step_1', 'se.lint', '1.0.0', 'passed', 'info', '{}'::jsonb, "
                            " '[]'::jsonb)"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_not_null_columns())


def test_evaluation_metrics_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_metrics() -> tuple[set[str], list[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(sync_connection: sa.Connection) -> tuple[set[str], list[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {c["name"] for c in insp.get_columns("metrics", schema="evaluation")}
                    pk = insp.get_pk_constraint("metrics", schema="evaluation")
                    return columns, pk["constrained_columns"]

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns = asyncio.run(_inspect_metrics())

    assert columns == {
        "metric_id",
        "workflow_id",
        "run_id",
        "metric_name",
        "metric_value",
        "unit",
        "source_component",
        "recorded_at",
    }
    assert pk_columns == ["metric_id"]


def test_evaluation_metrics_requires_an_existing_workflow_instance(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            # 'run_1' does not exist as an evaluation.experiment_runs row
            # either, but this test is specifically about the workflow_id
            # foreign key — the insert fails regardless of which
            # constraint is checked first.
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO evaluation.metrics "
                            "(metric_id, workflow_id, run_id, metric_name, metric_value, "
                            " unit, source_component, recorded_at) "
                            "VALUES ('metric_orphan', 'wf_does_not_exist', 'run_1', "
                            " 'latency', 123.456789, 'ms', 'llm_gateway', now())"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


async def _insert_real_experiment_run(
    engine: AsyncEngine, *, run_id: str, experiment_id: str, workflow_id: str
) -> None:
    """Seeds a real evaluation.experiments row and a real
    evaluation.experiment_runs row referencing it — the minimal chain
    metrics.run_id's own foreign key (0026_metrics_run_id_fk) requires.
    Callers must already have inserted a workflow.workflow_instances row
    for `workflow_id` (experiment_runs.workflow_id carries its own
    foreign key)."""
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO evaluation.experiments "
                "(experiment_id, name, description, definition_id, definition_version, "
                " variables, pinned_conditions, runs_per_variant, status, created_by) "
                "VALUES (:experiment_id, 'Test experiment', 'desc', 'def_test', '1.0.0', "
                " '{}'::jsonb, '{}'::jsonb, 1, 'draft', 'user_test')"
            ),
            {"experiment_id": experiment_id},
        )
        await connection.execute(
            sa.text(
                "INSERT INTO evaluation.experiment_runs "
                "(run_id, experiment_id, workflow_id, variant_key, model_alias, "
                " resolved_model_id, replicate_index, served_from_cache, status) "
                "VALUES (:run_id, :experiment_id, :workflow_id, 'control', 'fast', "
                " 'gpt-x', 0, false, 'pending')"
            ),
            {"run_id": run_id, "experiment_id": experiment_id, "workflow_id": workflow_id},
        )


def test_evaluation_metrics_requires_all_columns(database_url: str, alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_not_null_columns() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_for_metric', 'def_test', '1.0.0', 'created', "
                        " '{}'::jsonb, 'user_test', 0)"
                    )
                )
            await _insert_real_experiment_run(
                engine,
                run_id="run_for_metric_complete",
                experiment_id="exp_for_metric_complete",
                workflow_id="wf_for_metric",
            )
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO evaluation.metrics "
                        "(metric_id, workflow_id, run_id, metric_name, metric_value, "
                        " unit, source_component, recorded_at) "
                        "VALUES ('metric_complete', 'wf_for_metric', "
                        " 'run_for_metric_complete', 'latency', 42.5, 'ms', "
                        " 'llm_gateway', now())"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO evaluation.metrics "
                            "(metric_id, workflow_id, run_id, metric_name, metric_value, "
                            " unit, source_component) "
                            "VALUES ('metric_missing_recorded_at', 'wf_for_metric', "
                            " 'run_for_metric_complete', 'latency', 42.5, 'ms', 'llm_gateway')"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_not_null_columns())


def test_evaluation_metrics_metric_value_stores_numeric_20_6_precision(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_precision() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_for_metric_precision', 'def_test', '1.0.0', 'created', "
                        " '{}'::jsonb, 'user_test', 0)"
                    )
                )
            await _insert_real_experiment_run(
                engine,
                run_id="run_for_metric_precision",
                experiment_id="exp_for_metric_precision",
                workflow_id="wf_for_metric_precision",
            )
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO evaluation.metrics "
                        "(metric_id, workflow_id, run_id, metric_name, metric_value, "
                        " unit, source_component, recorded_at) "
                        "VALUES ('metric_precise', 'wf_for_metric_precision', "
                        " 'run_for_metric_precision', 'cost', 12345678901234.123456, "
                        " 'usd', 'llm_gateway', now())"
                    )
                )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT metric_value FROM evaluation.metrics "
                        "WHERE metric_id = 'metric_precise'"
                    )
                )
                row = result.mappings().one()

            assert row["metric_value"] == Decimal("12345678901234.123456")
        finally:
            await engine.dispose()

    asyncio.run(_exercise_precision())


def test_metrics_run_id_foreign_key_rejects_an_unknown_run(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_for_metric_bad_run', 'def_test', '1.0.0', 'created', "
                        " '{}'::jsonb, 'user_test', 0)"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO evaluation.metrics "
                            "(metric_id, workflow_id, run_id, metric_name, metric_value, "
                            " unit, source_component, recorded_at) "
                            "VALUES ('metric_bad_run', 'wf_for_metric_bad_run', "
                            " 'run_does_not_exist', 'latency', 1.0, 'ms', "
                            " 'llm_gateway', now())"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_metrics_run_id_foreign_key_accepts_a_real_run(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_for_metric_real_run', 'def_test', '1.0.0', 'created', "
                        " '{}'::jsonb, 'user_test', 0)"
                    )
                )
            await _insert_real_experiment_run(
                engine,
                run_id="run_for_metric_real",
                experiment_id="exp_for_metric_real",
                workflow_id="wf_for_metric_real_run",
            )
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO evaluation.metrics "
                        "(metric_id, workflow_id, run_id, metric_name, metric_value, "
                        " unit, source_component, recorded_at) "
                        "VALUES ('metric_real_run', 'wf_for_metric_real_run', "
                        " 'run_for_metric_real', 'latency', 1.0, 'ms', "
                        " 'llm_gateway', now())"
                    )
                )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT run_id FROM evaluation.metrics WHERE metric_id = 'metric_real_run'"
                    )
                )
                row = result.mappings().one()

            assert row["run_id"] == "run_for_metric_real"
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_evaluation_llm_calls_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect_llm_calls() -> tuple[set[str], list[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(sync_connection: sa.Connection) -> tuple[set[str], list[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {
                        c["name"] for c in insp.get_columns("llm_calls", schema="evaluation")
                    }
                    pk = insp.get_pk_constraint("llm_calls", schema="evaluation")
                    return columns, pk["constrained_columns"]

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns = asyncio.run(_inspect_llm_calls())

    assert columns == {
        "call_id",
        "workflow_id",
        "step_id",
        "agent_id",
        "prompt_id",
        "prompt_version",
        "model_alias",
        "provider",
        "model_id",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "cost_usd",
        "latency_ms",
        "stop_reason",
        "retries",
        "fallback_used",
        "degradations",
    }
    assert pk_columns == ["call_id"]


async def _insert_real_agent_and_prompt(engine: AsyncEngine, agent_id: str, prompt_id: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO catalog.agents "
                "(agent_id, pack_id, version, entrypoint, input_schema, output_schema, "
                " required_permissions, required_tools) "
                "VALUES (:agent_id, 'se.software_engineering', '1.0.0', 'pack.agents:Agent', "
                " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb)"
            ),
            {"agent_id": agent_id},
        )
        await connection.execute(
            sa.text(
                "INSERT INTO catalog.prompts "
                "(prompt_id, pack_id, version, content, input_schema, content_hash) "
                "VALUES (:prompt_id, 'se.software_engineering', '1.0.0', "
                " 'You are a helpful assistant.', '{}'::jsonb, 'sha256:abc')"
            ),
            {"prompt_id": prompt_id},
        )


def test_evaluation_llm_calls_requires_an_existing_workflow_instance(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            await _insert_real_agent_and_prompt(
                engine, "se.software_engineering/llm-orphan-agent", "prompt_llm_orphan"
            )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO evaluation.llm_calls "
                            "(call_id, workflow_id, step_id, agent_id, prompt_id, "
                            " prompt_version, model_alias, provider, model_id, "
                            " input_tokens, output_tokens, cache_read_tokens, "
                            " cache_write_tokens, cost_usd, latency_ms, stop_reason, "
                            " retries, fallback_used, degradations) "
                            "VALUES ('call_orphan_workflow', 'wf_does_not_exist', 'step_1', "
                            " 'se.software_engineering/llm-orphan-agent', "
                            " 'prompt_llm_orphan', '1.0.0', 'fast', 'anthropic', "
                            " 'claude-fast', 100, 50, 0, 0, 0.01, 250, 'end_turn', 0, "
                            " false, '[]'::jsonb)"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_evaluation_llm_calls_requires_an_existing_agent(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_for_llm_call_bad_agent', 'def_test', '1.0.0', "
                        " 'created', '{}'::jsonb, 'user_test', 0)"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.prompts "
                        "(prompt_id, pack_id, version, content, input_schema, content_hash) "
                        "VALUES ('prompt_for_bad_agent', 'se.software_engineering', "
                        " '1.0.0', 'You are a helpful assistant.', '{}'::jsonb, "
                        " 'sha256:abc')"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO evaluation.llm_calls "
                            "(call_id, workflow_id, step_id, agent_id, prompt_id, "
                            " prompt_version, model_alias, provider, model_id, "
                            " input_tokens, output_tokens, cache_read_tokens, "
                            " cache_write_tokens, cost_usd, latency_ms, stop_reason, "
                            " retries, fallback_used, degradations) "
                            "VALUES ('call_orphan_agent', 'wf_for_llm_call_bad_agent', "
                            " 'step_1', 'se.software_engineering/does-not-exist', "
                            " 'prompt_for_bad_agent', '1.0.0', 'fast', 'anthropic', "
                            " 'claude-fast', 100, 50, 0, 0, 0.01, 250, 'end_turn', 0, "
                            " false, '[]'::jsonb)"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_evaluation_llm_calls_requires_an_existing_prompt(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_for_llm_call_bad_prompt', 'def_test', '1.0.0', "
                        " 'created', '{}'::jsonb, 'user_test', 0)"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.agents "
                        "(agent_id, pack_id, version, entrypoint, input_schema, output_schema, "
                        " required_permissions, required_tools) "
                        "VALUES ('se.software_engineering/llm-bad-prompt-agent', "
                        " 'se.software_engineering', '1.0.0', 'pack.agents:Agent', "
                        " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb)"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO evaluation.llm_calls "
                            "(call_id, workflow_id, step_id, agent_id, prompt_id, "
                            " prompt_version, model_alias, provider, model_id, "
                            " input_tokens, output_tokens, cache_read_tokens, "
                            " cache_write_tokens, cost_usd, latency_ms, stop_reason, "
                            " retries, fallback_used, degradations) "
                            "VALUES ('call_orphan_prompt', 'wf_for_llm_call_bad_prompt', "
                            " 'step_1', 'se.software_engineering/llm-bad-prompt-agent', "
                            " 'prompt_does_not_exist', '1.0.0', 'fast', 'anthropic', "
                            " 'claude-fast', 100, 50, 0, 0, 0.01, 250, 'end_turn', 0, "
                            " false, '[]'::jsonb)"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_evaluation_llm_calls_requires_a_matching_prompt_version(
    database_url: str, alembic_config: Config
) -> None:
    """The composite (prompt_id, prompt_version) -> catalog.prompts
    (prompt_id, version) foreign key (migration 0024_catalog_prompts_pk)
    checks the *pair*, not just that prompt_id exists somewhere: a real
    prompt_id with a version that does not match any actual row is
    rejected, which the table's original single-column foreign key on
    prompt_id alone could not have caught.
    """

    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            await _insert_real_agent_and_prompt(
                engine,
                "se.software_engineering/llm-version-mismatch-agent",
                "prompt_llm_version_mismatch",
            )
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_for_llm_call_version_mismatch', 'def_test', '1.0.0', "
                        " 'created', '{}'::jsonb, 'user_test', 0)"
                    )
                )

            # prompt_llm_version_mismatch exists, but only at version
            # 1.0.0 (seeded by _insert_real_agent_and_prompt) — 2.0.0 is
            # a real prompt_id with a version that was never registered.
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO evaluation.llm_calls "
                            "(call_id, workflow_id, step_id, agent_id, prompt_id, "
                            " prompt_version, model_alias, provider, model_id, "
                            " input_tokens, output_tokens, cache_read_tokens, "
                            " cache_write_tokens, cost_usd, latency_ms, stop_reason, "
                            " retries, fallback_used, degradations) "
                            "VALUES ('call_version_mismatch', "
                            " 'wf_for_llm_call_version_mismatch', 'step_1', "
                            " 'se.software_engineering/llm-version-mismatch-agent', "
                            " 'prompt_llm_version_mismatch', '2.0.0', 'fast', 'anthropic', "
                            " 'claude-fast', 100, 50, 0, 0, 0.01, 250, 'end_turn', 0, "
                            " false, '[]'::jsonb)"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_evaluation_llm_calls_requires_all_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_not_null_columns() -> None:
        engine = build_engine(database_url)
        try:
            await _insert_real_agent_and_prompt(
                engine,
                "se.software_engineering/llm-complete-agent",
                "prompt_llm_complete",
            )
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_for_llm_call_complete', 'def_test', '1.0.0', "
                        " 'created', '{}'::jsonb, 'user_test', 0)"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO evaluation.llm_calls "
                        "(call_id, workflow_id, step_id, agent_id, prompt_id, "
                        " prompt_version, model_alias, provider, model_id, "
                        " input_tokens, output_tokens, cache_read_tokens, "
                        " cache_write_tokens, cost_usd, latency_ms, stop_reason, "
                        " retries, fallback_used, degradations) "
                        "VALUES ('call_complete', 'wf_for_llm_call_complete', 'step_1', "
                        " 'se.software_engineering/llm-complete-agent', "
                        " 'prompt_llm_complete', '1.0.0', 'fast', 'anthropic', "
                        " 'claude-fast', 100, 50, 0, 0, 0.01, 250, 'end_turn', 0, "
                        " false, '[]'::jsonb)"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO evaluation.llm_calls "
                            "(call_id, workflow_id, step_id, agent_id, prompt_id, "
                            " prompt_version, model_alias, provider, model_id, "
                            " input_tokens, output_tokens, cache_read_tokens, "
                            " cache_write_tokens, cost_usd, latency_ms, stop_reason, "
                            " retries, fallback_used) "
                            "VALUES ('call_missing_degradations', "
                            " 'wf_for_llm_call_complete', 'step_1', "
                            " 'se.software_engineering/llm-complete-agent', "
                            " 'prompt_llm_complete', '1.0.0', 'fast', 'anthropic', "
                            " 'claude-fast', 100, 50, 0, 0, 0.01, 250, 'end_turn', 0, "
                            " false)"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_not_null_columns())


def test_evaluation_llm_calls_accepts_a_real_workflow_agent_and_prompt(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_real_references() -> None:
        engine = build_engine(database_url)
        try:
            await _insert_real_agent_and_prompt(
                engine, "se.software_engineering/llm-real-agent", "prompt_llm_real"
            )
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_for_llm_call_real', 'def_test', '1.0.0', 'created', "
                        " '{}'::jsonb, 'user_test', 0)"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO evaluation.llm_calls "
                        "(call_id, workflow_id, step_id, agent_id, prompt_id, "
                        " prompt_version, model_alias, provider, model_id, "
                        " input_tokens, output_tokens, cache_read_tokens, "
                        " cache_write_tokens, cost_usd, latency_ms, stop_reason, "
                        " retries, fallback_used, degradations) "
                        "VALUES ('call_real', 'wf_for_llm_call_real', 'step_1', "
                        " 'se.software_engineering/llm-real-agent', 'prompt_llm_real', "
                        " '1.0.0', 'fast', 'anthropic', 'claude-fast', 100, 50, 0, 0, "
                        " 0.01, 250, 'end_turn', 0, false, '[]'::jsonb)"
                    )
                )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT agent_id, prompt_id FROM evaluation.llm_calls "
                        "WHERE call_id = 'call_real'"
                    )
                )
                row = result.mappings().one()

            assert row["agent_id"] == "se.software_engineering/llm-real-agent"
            assert row["prompt_id"] == "prompt_llm_real"
        finally:
            await engine.dispose()

    asyncio.run(_exercise_real_references())


# --- knowledge schema (Retrieval's first real increment) -------------------


def test_pgvector_extension_is_enabled(database_url: str, alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    async def _check_extension() -> bool:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                )
                return result.first() is not None
        finally:
            await engine.dispose()

    assert asyncio.run(_check_extension()) is True


def test_knowledge_documents_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect() -> tuple[set[str], list[str], bool]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(
                    sync_connection: sa.Connection,
                ) -> tuple[set[str], list[str], bool]:
                    insp = sa.inspect(sync_connection)
                    columns = {c["name"] for c in insp.get_columns("documents", schema="knowledge")}
                    pk = insp.get_pk_constraint("documents", schema="knowledge")
                    checks = insp.get_check_constraints("documents", schema="knowledge")
                    has_trust_check = any(c["name"] == "ck_documents_trust" for c in checks)
                    return columns, pk["constrained_columns"], has_trust_check

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns, has_trust_check = asyncio.run(_inspect())

    assert columns == {
        "document_id",
        "source_uri",
        "content_hash",
        "media_type",
        "project_id",
        "trust",
        "ingested_at",
        "archived_at",
    }
    assert pk_columns == ["document_id"]
    assert has_trust_check


def test_knowledge_documents_trust_check_constraint_rejects_an_invalid_value(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_check_constraint() -> None:
        engine = build_engine(database_url)
        try:
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO knowledge.documents "
                            "(document_id, source_uri, content_hash, media_type, trust, "
                            " ingested_at) "
                            "VALUES ('doc_bad_trust', 'docs/readme.md', 'sha256:abc', "
                            " 'text/markdown', 'maybe', now())"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_check_constraint())


async def _insert_document(engine: AsyncEngine, document_id: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO knowledge.documents "
                "(document_id, source_uri, content_hash, media_type, trust, ingested_at) "
                "VALUES (:document_id, 'docs/readme.md', 'sha256:abc', 'text/markdown', "
                " 'trusted', now())"
            ),
            {"document_id": document_id},
        )


def test_knowledge_chunks_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect() -> tuple[set[str], list[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(sync_connection: sa.Connection) -> tuple[set[str], list[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {c["name"] for c in insp.get_columns("chunks", schema="knowledge")}
                    pk = insp.get_pk_constraint("chunks", schema="knowledge")
                    return columns, pk["constrained_columns"]

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns = asyncio.run(_inspect())

    assert columns == {
        "chunk_id",
        "document_id",
        "ordinal",
        "content",
        "token_count",
        "chunk_strategy_version",
        "content_tsv",
        "metadata",
    }
    assert pk_columns == ["chunk_id"]


def test_knowledge_chunks_requires_an_existing_document(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO knowledge.chunks "
                            "(chunk_id, document_id, ordinal, content, token_count, "
                            " chunk_strategy_version) "
                            "VALUES ('chunk_orphan', 'doc_does_not_exist', 0, 'hello', 1, 'v1')"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_knowledge_chunks_content_tsv_is_generated_from_content(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_generated_column() -> str:
        engine = build_engine(database_url)
        try:
            await _insert_document(engine, "doc_for_tsv")
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO knowledge.chunks "
                        "(chunk_id, document_id, ordinal, content, token_count, "
                        " chunk_strategy_version) "
                        "VALUES ('chunk_tsv', 'doc_for_tsv', 0, "
                        " 'AI_OS Kernel architecture', 3, 'v1')"
                    )
                )
            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT content_tsv::text FROM knowledge.chunks "
                        "WHERE chunk_id = 'chunk_tsv'"
                    )
                )
                return str(result.scalar_one())
        finally:
            await engine.dispose()

    content_tsv = asyncio.run(_exercise_generated_column())

    # A real, populated tsvector, not null and not empty — proves the
    # GENERATED ALWAYS AS column genuinely computed from `content`,
    # not merely declared.
    assert content_tsv
    assert "architectur" in content_tsv  # to_tsvector stems "architecture"


def test_knowledge_chunks_unique_constraint_rejects_duplicate_ordinal(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_unique_constraint() -> None:
        engine = build_engine(database_url)
        try:
            await _insert_document(engine, "doc_for_ordinal")
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO knowledge.chunks "
                        "(chunk_id, document_id, ordinal, content, token_count, "
                        " chunk_strategy_version) "
                        "VALUES ('chunk_first', 'doc_for_ordinal', 0, 'first', 1, 'v1')"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO knowledge.chunks "
                            "(chunk_id, document_id, ordinal, content, token_count, "
                            " chunk_strategy_version) "
                            "VALUES ('chunk_duplicate', 'doc_for_ordinal', 0, 'dup', 1, 'v1')"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_unique_constraint())


async def _insert_chunk(engine: AsyncEngine, document_id: str, chunk_id: str) -> None:
    await _insert_document(engine, document_id)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO knowledge.chunks "
                "(chunk_id, document_id, ordinal, content, token_count, "
                " chunk_strategy_version) "
                "VALUES (:chunk_id, :document_id, 0, 'hello', 1, 'v1')"
            ),
            {"chunk_id": chunk_id, "document_id": document_id},
        )


def test_knowledge_embeddings_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect() -> tuple[set[str], list[str]]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(sync_connection: sa.Connection) -> tuple[set[str], list[str]]:
                    insp = sa.inspect(sync_connection)
                    columns = {
                        c["name"] for c in insp.get_columns("embeddings", schema="knowledge")
                    }
                    pk = insp.get_pk_constraint("embeddings", schema="knowledge")
                    return columns, pk["constrained_columns"]

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns = asyncio.run(_inspect())

    assert columns == {
        "embedding_id",
        "chunk_id",
        "embedding",
        "embedding_model_id",
        "embedding_model_version",
        "dimensions",
        "index_generation",
    }
    assert pk_columns == ["embedding_id"]


def test_knowledge_embeddings_requires_an_existing_chunk(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO knowledge.embeddings "
                            "(embedding_id, chunk_id, embedding, embedding_model_id, "
                            " embedding_model_version, dimensions, index_generation) "
                            "VALUES ('emb_orphan', 'chunk_does_not_exist', '[1,2,3]', "
                            " 'test-model', '1.0.0', 3, 1)"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_knowledge_embeddings_accepts_vectors_of_different_dimensions(
    database_url: str, alembic_config: Config
) -> None:
    # The whole point of the unconstrained `vector` column (no fixed
    # dimension) — see knowledge_schema.py's own docstring: rows from
    # different embedding models, with genuinely different real vector
    # sizes, must be able to coexist.
    command.upgrade(alembic_config, "head")

    async def _exercise_varying_dimensions() -> tuple[str, str]:
        engine = build_engine(database_url)
        try:
            await _insert_chunk(engine, "doc_for_small_vec", "chunk_small_vec")
            await _insert_chunk(engine, "doc_for_large_vec", "chunk_large_vec")

            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO knowledge.embeddings "
                        "(embedding_id, chunk_id, embedding, embedding_model_id, "
                        " embedding_model_version, dimensions, index_generation) "
                        "VALUES ('emb_small', 'chunk_small_vec', '[1,2,3]', "
                        " 'model-a', '1.0.0', 3, 1)"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO knowledge.embeddings "
                        "(embedding_id, chunk_id, embedding, embedding_model_id, "
                        " embedding_model_version, dimensions, index_generation) "
                        "VALUES ('emb_large', 'chunk_large_vec', "
                        " '[1,2,3,4,5,6,7,8]', 'model-b', '2.0.0', 8, 1)"
                    )
                )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT embedding_id, embedding::text FROM knowledge.embeddings "
                        "WHERE embedding_id IN ('emb_small', 'emb_large') "
                        "ORDER BY embedding_id"
                    )
                )
                rows = result.all()
                return rows[1][1], rows[0][1]
        finally:
            await engine.dispose()

    small_vector, large_vector = asyncio.run(_exercise_varying_dimensions())

    assert small_vector == "[1,2,3]"
    assert large_vector == "[1,2,3,4,5,6,7,8]"


def test_knowledge_memory_items_matches_the_documented_columns(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _inspect() -> tuple[set[str], list[str], bool]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:

                def _sync_inspect(
                    sync_connection: sa.Connection,
                ) -> tuple[set[str], list[str], bool]:
                    insp = sa.inspect(sync_connection)
                    columns = {
                        c["name"] for c in insp.get_columns("memory_items", schema="knowledge")
                    }
                    pk = insp.get_pk_constraint("memory_items", schema="knowledge")
                    checks = insp.get_check_constraints("memory_items", schema="knowledge")
                    has_type_check = any(c["name"] == "ck_memory_items_memory_type" for c in checks)
                    return columns, pk["constrained_columns"], has_type_check

                return await connection.run_sync(_sync_inspect)
        finally:
            await engine.dispose()

    columns, pk_columns, has_type_check = asyncio.run(_inspect())

    assert columns == {
        "memory_id",
        "memory_type",
        "content",
        "source_workflow_id",
        "quality_signal",
        "promoted_at",
        "expires_at",
        "provenance",
    }
    assert pk_columns == ["memory_id"]
    assert has_type_check


def test_knowledge_memory_items_memory_type_check_constraint_rejects_an_invalid_value(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_check_constraint() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_for_bad_memory_type', 'def_test', '1.0.0', 'created', "
                        " '{}'::jsonb, 'user_test', 0)"
                    )
                )

            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO knowledge.memory_items "
                            "(memory_id, memory_type, content, source_workflow_id) "
                            "VALUES ('mem_bad_type', 'not_a_real_type', 'lesson learned', "
                            " 'wf_for_bad_memory_type')"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_check_constraint())


def test_knowledge_memory_items_requires_an_existing_workflow_instance(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_foreign_key() -> None:
        engine = build_engine(database_url)
        try:
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO knowledge.memory_items "
                            "(memory_id, memory_type, content, source_workflow_id) "
                            "VALUES ('mem_orphan', 'workflow', 'lesson learned', "
                            " 'wf_does_not_exist')"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_exercise_foreign_key())


def test_knowledge_memory_items_accepts_a_real_workflow_and_nullable_fields(
    database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, "head")

    async def _exercise_real_reference() -> tuple[str, None, None, None]:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_instances "
                        "(workflow_id, definition_id, definition_version, status, "
                        " inputs, principal_id, last_event_seq) "
                        "VALUES ('wf_for_real_memory', 'def_test', '1.0.0', 'created', "
                        " '{}'::jsonb, 'user_test', 0)"
                    )
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO knowledge.memory_items "
                        "(memory_id, memory_type, content, source_workflow_id) "
                        "VALUES ('mem_real', 'workflow', 'the build failed twice', "
                        " 'wf_for_real_memory')"
                    )
                )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT memory_type, quality_signal, promoted_at, expires_at "
                        "FROM knowledge.memory_items WHERE memory_id = 'mem_real'"
                    )
                )
                row = result.mappings().one()
                return (
                    row["memory_type"],
                    row["quality_signal"],
                    row["promoted_at"],
                    row["expires_at"],
                )
        finally:
            await engine.dispose()

    memory_type, quality_signal, promoted_at, expires_at = asyncio.run(_exercise_real_reference())

    assert memory_type == "workflow"
    assert quality_signal is None
    assert promoted_at is None
    assert expires_at is None
