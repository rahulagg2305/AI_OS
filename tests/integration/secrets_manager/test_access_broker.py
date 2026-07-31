"""AccessBroker against a real Postgres container (ADR-0015 — no
mocking the database) and the real, already-proven `EnvSecretProvider`
and `SqlAuditLogWriter`. Proves: an authorized access succeeds and is
recorded as a real, hash-chained `governance.audit_log` row; an
unauthorized access is refused *and* is itself recorded as a real,
security-relevant denied event — never a silent no-op.
``P01-S02-M19-T04``.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from ai_os_kernel.observability.audit import AuditOutcome, SqlAuditLogWriter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.secrets_manager.access_broker import AccessBroker
from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.secrets_manager.errors import AccessDeniedError, SecretResolutionError
from ai_os_kernel.security_manager.models import Principal, PrincipalType, SecurityContext
from ai_os_kernel.security_manager.permissions import SECRET_ACCESS
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


def _admin_context() -> SecurityContext:
    return SecurityContext(
        principal=Principal(
            principal_id="admin-1", principal_type=PrincipalType.USER, roles=frozenset({"admin"})
        ),
        permissions=frozenset({SECRET_ACCESS}),
    )


def _viewer_context() -> SecurityContext:
    return SecurityContext(
        principal=Principal(
            principal_id="viewer-1",
            principal_type=PrincipalType.USER,
            roles=frozenset({"viewer"}),
        ),
        permissions=frozenset(),
    )


def test_an_authorized_access_succeeds_and_is_audited(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            provider = EnvSecretProvider(env={"AIOS_SECRET_LLM_API_KEY": "sk-real-value"})
            audit_log = SqlAuditLogWriter(engine)
            broker = AccessBroker(provider=provider, audit_log=audit_log)

            value = await broker.resolve("secret://env/llm-api-key", context=_admin_context())

            assert value.reveal() == "sk-real-value"

            rows = await audit_log.list_all()
            record = next(r for r in rows if r.event_type == "secret.access.allowed")
            assert record.principal_id == "admin-1"
            assert record.principal_type == "user"
            assert record.outcome == AuditOutcome.ALLOWED
            assert record.resource_type == "secret"
            assert record.resource_id == "secret://env/llm-api-key"
            # The one property that matters most: the real value is
            # never anywhere in the audit row.
            assert "sk-real-value" not in str(record.detail)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_an_unauthorized_access_is_refused_and_also_audited(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            provider = EnvSecretProvider(env={"AIOS_SECRET_LLM_API_KEY": "sk-real-value"})
            audit_log = SqlAuditLogWriter(engine)
            broker = AccessBroker(provider=provider, audit_log=audit_log)

            with pytest.raises(AccessDeniedError):
                await broker.resolve("secret://env/llm-api-key", context=_viewer_context())

            rows = await audit_log.list_all()
            record = next(r for r in rows if r.event_type == "secret.access.denied")
            assert record.principal_id == "viewer-1"
            assert record.outcome == AuditOutcome.DENIED
            assert record.resource_type == "secret"
            assert record.resource_id == "secret://env/llm-api-key"
            assert record.detail == {"permission": SECRET_ACCESS}
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_denied_attempt_never_reaches_the_real_provider(database_url: str) -> None:
    """A stronger property than "the caller gets an error": the
    provider is never even consulted for an unauthorized principal, so
    a denied access can never accidentally reveal a value anywhere."""

    class _ExplodingProvider:
        async def resolve(self, reference: str) -> None:  # pragma: no cover - must not run
            raise AssertionError("the provider must never be called for a denied access")

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            audit_log = SqlAuditLogWriter(engine)
            broker = AccessBroker(provider=_ExplodingProvider(), audit_log=audit_log)  # type: ignore[arg-type]

            with pytest.raises(AccessDeniedError):
                await broker.resolve("secret://env/llm-api-key", context=_viewer_context())
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_resolution_failure_for_an_authorized_principal_is_audited_as_failure(
    database_url: str,
) -> None:
    """The other real outcome AuditOutcome already models: an
    authorized principal asking for a secret that does not exist is a
    failure, not a denial — a different, already-distinguished event."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            provider = EnvSecretProvider(env={})  # nothing set
            audit_log = SqlAuditLogWriter(engine)
            broker = AccessBroker(provider=provider, audit_log=audit_log)

            with pytest.raises(SecretResolutionError):
                await broker.resolve("secret://env/missing-key", context=_admin_context())

            rows = await audit_log.list_all()
            record = next(r for r in rows if r.event_type == "secret.access.failed")
            assert record.principal_id == "admin-1"
            assert record.outcome == AuditOutcome.FAILURE
        finally:
            await engine.dispose()

    asyncio.run(_run())
