"""SqlConfigChangeWriter against a real Postgres container (ADR-0015 —
no mocking the database). Proves: a real config change is recorded
correctly and verifies against its own real old/new values, and a
digest tampered with directly in the database — the same technique used
to prove ``governance.audit_log`` tamper detection — is caught by
:func:`verify_config_change`, not silently passed. ``P01-S02-M01-T08``.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from ai_os_kernel.configuration_manager.audit import SqlConfigChangeWriter, verify_config_change
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.governance_schema import config_changes
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


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


def test_a_normal_config_change_is_recorded_and_verifies(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlConfigChangeWriter(engine)

            await writer.record(
                config_key="llm_gateway.default_model",
                old_value="claude-opus-4-6",
                new_value="claude-opus-5",
                changed_by="user-1",
                reason="quarterly model upgrade",
            )

            rows = await writer.list_all()
            assert len(rows) == 1
            record = rows[0]
            assert record.config_key == "llm_gateway.default_model"
            assert record.changed_by == "user-1"
            assert record.reason == "quarterly model upgrade"
            # The real property the schema exists for: digests, never
            # the raw values, are what's persisted.
            assert record.old_value_digest is not None
            assert record.new_value_digest is not None
            assert record.old_value_digest != "claude-opus-4-6"
            assert len(record.old_value_digest) == 64

            result = verify_config_change(
                record, old_value="claude-opus-4-6", new_value="claude-opus-5"
            )
            assert result.valid is True
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_first_ever_value_has_no_old_value_digest(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlConfigChangeWriter(engine)

            await writer.record(
                config_key="new.feature_flag",
                old_value=None,
                new_value=True,
                changed_by="user-2",
                reason="introduce new_feature_flag",
            )

            rows = await writer.list_all()
            record = next(r for r in rows if r.config_key == "new.feature_flag")
            assert record.old_value_digest is None
            assert record.new_value_digest is not None

            result = verify_config_change(record, old_value=None, new_value=True)
            assert result.valid is True
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_tampered_digest_is_detected_and_reported(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlConfigChangeWriter(engine)
            await writer.record(
                config_key="secrets.api_key_ref",
                old_value="secret://env/OLD_KEY",
                new_value="secret://env/NEW_KEY",
                changed_by="admin-1",
                reason="key rotation",
            )

            rows_before = await writer.list_all()
            record = next(r for r in rows_before if r.config_key == "secrets.api_key_ref")
            assert (
                verify_config_change(
                    record,
                    old_value="secret://env/OLD_KEY",
                    new_value="secret://env/NEW_KEY",
                ).valid
                is True
            )

            # A real tamper: directly UPDATE the persisted digest, the
            # same technique used to prove governance.audit_log tamper
            # detection — exactly what an attacker editing the database
            # (not going through this writer) would do.
            async with engine.begin() as connection:
                await connection.execute(
                    sa.update(config_changes)
                    .where(config_changes.c.change_id == record.change_id)
                    .values(new_value_digest="0" * 64)
                )

            rows_after = await writer.list_all()
            tampered = next(r for r in rows_after if r.change_id == record.change_id)
            result = verify_config_change(
                tampered,
                old_value="secret://env/OLD_KEY",
                new_value="secret://env/NEW_KEY",
            )

            assert result.valid is False
            assert result.reason is not None
            assert "new_value_digest does not match" in result.reason
            assert record.change_id in result.reason
        finally:
            await engine.dispose()

    asyncio.run(_run())
