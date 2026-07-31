"""RuntimeOverrideStore.apply against a real Postgres container (ADR-0015
— no mocking the database). Proves layer 5's defining requirement (§4:
"Runtime overrides — audited"): applying an override writes a real,
verifiable ``governance.config_changes`` row through the already-proven
``SqlConfigChangeWriter``, not merely an in-memory change.
``P01-S02-M01-T04``.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from ai_os_kernel.configuration_manager.audit import SqlConfigChangeWriter, verify_config_change
from ai_os_kernel.configuration_manager.runtime_overrides import RuntimeOverrideStore
from ai_os_kernel.persistence.engine import build_engine
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


def test_applying_a_runtime_override_writes_a_real_verifiable_audit_row(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlConfigChangeWriter(engine)
            store = RuntimeOverrideStore()

            await store.apply(
                writer,
                config_key="log_level",
                new_value="DEBUG",
                changed_by="oncall-1",
                reason="live-debugging an incident",
            )

            assert store.snapshot() == {"log_level": "DEBUG"}

            rows = await writer.list_all()
            record = next(r for r in rows if r.config_key == "log_level")
            assert record.changed_by == "oncall-1"
            assert record.reason == "live-debugging an incident"
            assert record.old_value_digest is None  # first-ever value for this key

            result = verify_config_change(record, old_value=None, new_value="DEBUG")
            assert result.valid is True
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_second_override_of_the_same_key_records_the_real_prior_value(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlConfigChangeWriter(engine)
            store = RuntimeOverrideStore()

            await store.apply(
                writer, config_key="port", new_value=9000, changed_by="u1", reason="first"
            )
            await store.apply(
                writer, config_key="port", new_value=9100, changed_by="u2", reason="second"
            )

            rows = [r for r in await writer.list_all() if r.config_key == "port"]
            assert len(rows) == 2
            second = max(rows, key=lambda r: r.changed_at)

            result = verify_config_change(second, old_value=9000, new_value=9100)
            assert result.valid is True
            assert store.snapshot()["port"] == 9100
        finally:
            await engine.dispose()

    asyncio.run(_run())
