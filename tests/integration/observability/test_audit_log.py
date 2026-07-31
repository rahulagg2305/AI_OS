"""SqlAuditLogWriter against a real Postgres container (ADR-0015 — no
mocking the database). Proves: real appends genuinely chain (each
row's real prev_hash is the prior row's real row_hash), the chain
verifies over real persisted rows, and a genuine tamper — mutating one
already-written row's column value directly, the same way an attacker
editing a database would — is detected and reported, not silently
passed. ``P01-S05-M04-T05``.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from ai_os_kernel.observability.audit import AuditOutcome, SqlAuditLogWriter, verify_chain
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.governance_schema import audit_log
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


def test_a_real_append_writes_a_chained_row_and_the_chain_verifies(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlAuditLogWriter(engine)

            await writer.record(
                event_type="auth.success",
                principal_id="user-1",
                principal_type="user",
                outcome=AuditOutcome.SUCCESS,
                detail={"method": "bearer"},
            )
            await writer.record(
                event_type="pack.activated",
                principal_id="user-1",
                principal_type="user",
                outcome=AuditOutcome.ALLOWED,
                detail={"pack_id": "software-engineering"},
                resource_type="pack",
                resource_id="software-engineering",
            )
            await writer.record(
                event_type="authz.denied",
                principal_id="user-2",
                principal_type="service_account",
                outcome=AuditOutcome.DENIED,
                detail={"permission": "workflow:start"},
            )

            rows = await writer.list_all()
            assert len(rows) == 3
            # The real chain: each row's real prev_hash is the prior
            # row's real row_hash, not a guess.
            assert rows[0].prev_hash is None  # first row ever
            assert rows[1].prev_hash == rows[0].row_hash
            assert rows[2].prev_hash == rows[1].row_hash
            # Every row_hash is a real, distinct SHA-256 hex digest.
            assert len({r.row_hash for r in rows}) == 3
            assert all(len(r.row_hash) == 64 for r in rows)

            result = verify_chain(rows)
            assert result.valid is True
            assert result.broken_at_seq is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_genuinely_tampered_row_is_detected_and_reported(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlAuditLogWriter(engine)
            for i in range(3):
                await writer.record(
                    event_type="secret.accessed",
                    principal_id="svc-1",
                    principal_type="service_account",
                    outcome=AuditOutcome.SUCCESS,
                    detail={"reference": f"secret://env/key-{i}"},
                )

            rows_before = await writer.list_all()
            assert verify_chain(rows_before).valid is True
            tampered = rows_before[1]

            # A real tamper: directly UPDATE one already-written row's
            # own detail column, exactly the way an attacker editing the
            # database (not going through this writer) would — leaving
            # row_hash/prev_hash untouched, since the attacker has no
            # reason to know how they were computed.
            async with engine.begin() as connection:
                await connection.execute(
                    sa.update(audit_log)
                    .where(audit_log.c.audit_id == tampered.audit_id)
                    .values(detail={"reference": "secret://env/EXFILTRATED"})
                )

            rows_after = await writer.list_all()
            result = verify_chain(rows_after)

            assert result.valid is False
            assert result.broken_at_seq == tampered.seq
            assert result.reason is not None
            assert "row_hash does not match" in result.reason
            assert tampered.audit_id in result.reason
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_tampered_prev_hash_pointer_is_also_detected(database_url: str) -> None:
    """The other half of the real property: even if row N's own content
    and row_hash are both self-consistent, forging its prev_hash to
    point somewhere else breaks the link to what actually preceded it."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlAuditLogWriter(engine)
            for i in range(2):
                await writer.record(
                    event_type="config.changed",
                    principal_id="admin-1",
                    principal_type="user",
                    outcome=AuditOutcome.SUCCESS,
                    detail={"key": f"k{i}"},
                )

            rows = await writer.list_all()
            second = rows[1]

            async with engine.begin() as connection:
                await connection.execute(
                    sa.update(audit_log)
                    .where(audit_log.c.audit_id == second.audit_id)
                    .values(prev_hash="0" * 64)
                )

            result = verify_chain(await writer.list_all())

            assert result.valid is False
            assert result.broken_at_seq == second.seq
            assert result.reason is not None
            assert "prev_hash does not match" in result.reason
        finally:
            await engine.dispose()

    asyncio.run(_run())
