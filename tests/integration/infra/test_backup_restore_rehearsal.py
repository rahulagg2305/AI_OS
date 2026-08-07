"""Real backup/restore rehearsal (``P07-S01-M40-T03``) —
`deployment_architecture.md`'s own disclosed gap: "no backup/restore
tooling and no rehearsed restore drill." Proves a real `pg_dump`
backup of a real, hash-chained `governance.audit_log` genuinely
restores into a completely separate, genuinely empty database — not
merely that a dump file was produced — including a real
:func:`~ai_os_kernel.observability.audit.verify_chain` pass against
the restored rows.

Real Postgres via testcontainers (ADR-0015), two independent
containers: a genuinely populated ``source`` and a genuinely empty
``target``. ``pg_dump``/``pg_restore`` are real, external client
binaries — opt-in, skipped cleanly if absent from `PATH`, the
identical shape `test_ai_os_helm_chart.py` already establishes for
`helm`/`kind`.

Scoped to `pg_dump`/`pg_restore` — the portable baseline every
Postgres deployment supports and the exact tooling this ticket's own
Input/Output ("a backup" -> "a verified restore") names. Continuous
archiving/PITR (`deployment_architecture.md`'s own "Managed continuous
archiving + PITR" row) is a separate, cloud-managed-service-specific
capability, genuinely unbuilt and out of this ticket's scope — no
cloud provider has been decided anywhere in this repo, and inventing
one would be the same "no hardcoded values" violation
`P07-S01-M40-T02`'s own NetworkPolicy already disclosed for Postgres/
Redis destinations.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.integration._postgres_fixture import postgres_container

from ai_os_kernel.observability.audit import (
    AuditLogRecord,
    AuditOutcome,
    SqlAuditLogWriter,
    verify_chain,
)
from ai_os_kernel.persistence.engine import build_engine

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
BACKUP_SCRIPT = REPO_ROOT / "infra" / "scripts" / "backup.sh"
RESTORE_SCRIPT = REPO_ROOT / "infra" / "scripts" / "restore.sh"
_SUBPROCESS_TIMEOUT_SECONDS = 120.0
_REHEARSAL_PRINCIPAL = "backup-rehearsal-principal"


def _run_script(
    sh_binary: str,
    script: Path,
    database_url: str,
    argv: list[str],
    *,
    tolerate_transaction_timeout_warning: bool = False,
) -> str:
    """Every real invocation of `backup.sh`/`restore.sh` in this file —
    a fixed-shape argv (script path + literal flags), never raw shell
    input, mirroring `test_ai_os_helm_chart.py`'s own `_run` docstring.

    ``tolerate_transaction_timeout_warning`` is a narrow, disclosed,
    *test-harness-only* relaxation — never applied to `restore.sh`
    itself, which stays exactly what a real operator would run. A
    `pg_restore` client newer than the server it restores into (this
    development machine's real, installed PG18 client against every
    real container here's PG16 server — a genuine, disclosed version
    skew, not a hypothetical) emits exactly one harmless, well-known
    warning: the dump's own session-reset preamble sets
    `transaction_timeout`, a GUC PG16 does not recognise. `pg_restore`
    itself already treats this as non-fatal (`errors ignored on
    restore: 1`, real data restored regardless) — this only avoids
    treating that one specific, already-tolerated warning as a hard
    test failure; any other stderr content still raises.
    """
    env = {**os.environ, "AIOS_DATABASE_URL": database_url}
    result = subprocess.run(  # noqa: S603 — argv is fixed-shape, no shell
        [sh_binary, str(script), *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_SUBPROCESS_TIMEOUT_SECONDS,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        is_only_the_known_transaction_timeout_warning = (
            tolerate_transaction_timeout_warning
            and 'unrecognized configuration parameter "transaction_timeout"' in result.stderr
            and "errors ignored on restore: 1" in result.stderr
        )
        if not is_only_the_known_transaction_timeout_warning:
            raise RuntimeError(
                f"{script.name} exited {result.returncode}:\nstdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
    return result.stdout


@pytest.fixture(scope="module")
def sh_binary() -> str:
    binary = shutil.which("sh")
    if binary is None:
        pytest.skip("sh is not on PATH — this rehearsal's own opt-in real-tool suite")
    return binary


@pytest.fixture(scope="module")
def pg_dump_binary() -> str:
    binary = shutil.which("pg_dump")
    if binary is None:
        pytest.skip("pg_dump is not on PATH — this rehearsal's own opt-in real-tool suite")
    return binary


@pytest.fixture(scope="module")
def pg_restore_binary() -> str:
    binary = shutil.which("pg_restore")
    if binary is None:
        pytest.skip("pg_restore is not on PATH — this rehearsal's own opt-in real-tool suite")
    return binary


def test_a_real_restore_recreates_the_schema_and_the_hash_chain_verifies(
    sh_binary: str,
    pg_dump_binary: str,
    pg_restore_binary: str,
    tmp_path: Path,
) -> None:
    """A plain, synchronous test — ``alembic.command.upgrade`` runs its
    own migrations via an internal ``asyncio.run()`` (`kernel/alembic/env.py`),
    which cannot nest inside an already-running event loop; every other
    real Alembic-driven integration test in this tree keeps its own
    top-level test function synchronous for the identical reason,
    wrapping only the ``SqlAuditLogWriter`` calls in a small
    ``async def _run(): ...; asyncio.run(_run())``."""

    async def _seed_and_verify_source(engine: AsyncEngine) -> list[AuditLogRecord]:
        writer = SqlAuditLogWriter(engine)
        for i in range(5):
            await writer.record(
                event_type=f"test.backup_rehearsal.{i}",
                principal_id=_REHEARSAL_PRINCIPAL,
                principal_type="user",
                outcome=AuditOutcome.SUCCESS,
                detail={"sequence": i},
            )
        seeded = await writer.list_all()
        assert len(seeded) == 5
        assert verify_chain(seeded).valid
        return seeded

    async def _read_back(engine: AsyncEngine) -> list[AuditLogRecord]:
        return await SqlAuditLogWriter(engine).list_all()

    with postgres_container() as source, postgres_container() as target:
        # Two distinct URL forms for the identical container, on
        # purpose: build_engine/SQLAlchemy needs the `+asyncpg` driver
        # suffix, but pg_dump/pg_restore (real libpq clients) do not
        # recognize that dialect string at all — passed the default
        # `postgresql+asyncpg://...` form, libpq silently misparses it
        # and pg_dump hangs waiting on a password prompt that never
        # arrives (a real bug found while writing this test, not a
        # hypothetical). `driver=None` is the plain, libpq-compatible
        # `postgresql://...` form these two real client binaries need.
        source_url = source.get_connection_url()
        target_url = target.get_connection_url()
        source_libpq_url = source.get_connection_url(driver=None)
        target_libpq_url = target.get_connection_url(driver=None)

        # The source alone is migrated and seeded — the target starts
        # genuinely empty (no Alembic run against it at all), so a
        # successful restore proves the backup is self-contained: real
        # schema *and* real data, not data layered onto an
        # already-prepared target. AIOS_DATABASE_URL is set/restored
        # around this one call, the identical pattern every other real
        # Alembic-driven integration test in this tree already uses.
        previous_database_url = os.environ.get("AIOS_DATABASE_URL")
        os.environ["AIOS_DATABASE_URL"] = source_url
        try:
            command.upgrade(Config(str(ALEMBIC_INI)), "head")
        finally:
            if previous_database_url is None:
                os.environ.pop("AIOS_DATABASE_URL", None)
            else:
                os.environ["AIOS_DATABASE_URL"] = previous_database_url

        source_engine = build_engine(source_url)
        try:
            seeded = asyncio.run(_seed_and_verify_source(source_engine))
        finally:
            asyncio.run(source_engine.dispose())

        dump_path = tmp_path / "aios.dump"
        _run_script(sh_binary, BACKUP_SCRIPT, source_libpq_url, [str(dump_path)])
        assert dump_path.exists()
        assert dump_path.stat().st_size > 0

        _run_script(
            sh_binary,
            RESTORE_SCRIPT,
            target_libpq_url,
            [str(dump_path)],
            tolerate_transaction_timeout_warning=True,
        )

        target_engine = build_engine(target_url)
        try:
            restored = asyncio.run(_read_back(target_engine))
            assert len(restored) == 5
            assert {r.audit_id for r in restored} == {r.audit_id for r in seeded}

            result = verify_chain(restored)
            assert result.valid, result.reason
        finally:
            asyncio.run(target_engine.dispose())
