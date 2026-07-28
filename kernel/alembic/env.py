"""Alembic environment, async (ADR-0011: SQLAlchemy 2.0, asyncpg driver).

The connection URL is read from ``AIOS_DATABASE_URL`` at run time — the
same env-var-only rule as everywhere else the URL is used
(:mod:`ai_os_kernel.persistence.settings`). ``alembic.ini`` deliberately
carries no URL.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import AsyncEngine, async_engine_from_config

from ai_os_kernel.persistence.catalog_schema import metadata as catalog_metadata
from ai_os_kernel.persistence.cross_schema_foreign_keys import (
    register_workflow_run_manifest_foreign_key,
)
from ai_os_kernel.persistence.evaluation_schema import metadata as evaluation_metadata
from ai_os_kernel.persistence.governance_schema import metadata as governance_metadata
from ai_os_kernel.persistence.knowledge_schema import metadata as knowledge_metadata
from ai_os_kernel.persistence.platform_schema import metadata as platform_metadata
from ai_os_kernel.persistence.schema import metadata as workflow_metadata
from ai_os_kernel.persistence.settings import DatabaseSettings
from ai_os_kernel.persistence.trace_schema import metadata as trace_metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Cross-schema foreign keys can only be attached once every schema module
# they touch has been imported (see cross_schema_foreign_keys.py's own
# docstring for why this can't be done inline inside schema.py itself).
# All six schema modules above are already fully imported by this point.
register_workflow_run_manifest_foreign_key()

# One target_metadata per bounded context/schema (workflow, governance,
# platform, trace, catalog, evaluation, knowledge, ...), each still a
# single MetaData; Alembic accepts a sequence of them here for
# autogenerate diffing across all of them at once.
target_metadata = [
    workflow_metadata,
    governance_metadata,
    platform_metadata,
    trace_metadata,
    catalog_metadata,
    evaluation_metadata,
    knowledge_metadata,
]


def _database_url() -> str:
    return DatabaseSettings().database_url


def run_migrations_offline() -> None:
    """Generate SQL without a live database connection (``--sql`` mode)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    connectable: AsyncEngine = async_engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
