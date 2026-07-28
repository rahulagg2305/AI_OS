"""SqlPromptCatalog against a real Postgres container (ADR-0015 — no
mocking the database). Proves: it renders a real ``catalog.prompts``
row's content with variables substituted, an unknown ``(prompt_id,
version)`` pair raises ``PromptNotFoundError``, a missing required
variable raises ``PromptVariableMissingError``, and two distinct rows
render independently by their full ``(prompt_id, version)`` key.

Does **not** test two versions of the *same* ``prompt_id`` — see
``test_two_distinct_prompt_ids_render_independently``'s own docstring
for a discovered schema inconsistency this uncovered: ``catalog.prompts``
still has ``prompt_id`` alone as its primary key, so that scenario
cannot be stored yet.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.prompt_engine.catalog import SqlPromptCatalog
from ai_os_kernel.prompt_engine.errors import PromptNotFoundError, PromptVariableMissingError
from ai_os_kernel.prompt_engine.models import PromptRenderRequest
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


async def _seed_prompt(database_url: str, *, prompt_id: str, version: str, content: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.prompts "
                    "(prompt_id, pack_id, version, content, input_schema, content_hash) "
                    "VALUES (:prompt_id, 'se.software_engineering', :version, :content, "
                    " '{}'::jsonb, 'sha256:test')"
                ),
                {"prompt_id": prompt_id, "version": version, "content": content},
            )
    finally:
        await engine.dispose()


def test_renders_a_real_catalog_row_with_variables_substituted(database_url: str) -> None:
    async def _run() -> None:
        await _seed_prompt(
            database_url,
            prompt_id="prompt_catalog_greeting",
            version="1.0.0",
            content="Hello, {{name}}! Welcome to {{place}}.",
        )
        engine = build_engine(database_url)
        try:
            catalog = SqlPromptCatalog(engine)

            response = await catalog.render(
                PromptRenderRequest(
                    prompt_id="prompt_catalog_greeting",
                    version="1.0.0",
                    variables={"name": "Ada", "place": "AI_OS"},
                )
            )

            assert response.content == "Hello, Ada! Welcome to AI_OS."
            assert response.prompt_id == "prompt_catalog_greeting"
            assert response.version == "1.0.0"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_unknown_prompt_id_or_version_raises_prompt_not_found(database_url: str) -> None:
    async def _run() -> None:
        await _seed_prompt(
            database_url,
            prompt_id="prompt_catalog_known",
            version="1.0.0",
            content="static content",
        )
        engine = build_engine(database_url)
        try:
            catalog = SqlPromptCatalog(engine)

            with pytest.raises(PromptNotFoundError, match="prompt_catalog_missing"):
                await catalog.render(
                    PromptRenderRequest(prompt_id="prompt_catalog_missing", version="1.0.0")
                )

            with pytest.raises(PromptNotFoundError, match="version='2.0.0'"):
                await catalog.render(
                    PromptRenderRequest(prompt_id="prompt_catalog_known", version="2.0.0")
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_missing_required_variable_raises_and_names_it(database_url: str) -> None:
    async def _run() -> None:
        await _seed_prompt(
            database_url,
            prompt_id="prompt_catalog_needs_vars",
            version="1.0.0",
            content="Hello, {{name}}!",
        )
        engine = build_engine(database_url)
        try:
            catalog = SqlPromptCatalog(engine)

            with pytest.raises(PromptVariableMissingError, match="name"):
                await catalog.render(
                    PromptRenderRequest(prompt_id="prompt_catalog_needs_vars", version="1.0.0")
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_two_distinct_prompt_ids_render_independently(database_url: str) -> None:
    """Not "two versions of the same prompt_id": ``catalog.prompts`` has
    ``prompt_id`` alone as its primary key today (data_model.md §5,
    ``catalog_schema.py``), the same single-column-PK shape
    ``catalog.workflow_definitions`` had before it was migrated to a
    composite ``(definition_id, version)`` key — so two rows sharing one
    ``prompt_id`` cannot coexist yet regardless of ``version``. That gap
    is a discovered inconsistency, reported separately, not fixed by
    this reader-only step (a PK migration is a distinct, higher-risk
    change needing its own approval, mirroring the
    ``workflow_definitions`` precedent). This test instead proves the
    reader correctly distinguishes two independent rows by their full
    ``(prompt_id, version)`` key.
    """

    async def _run() -> None:
        await _seed_prompt(
            database_url,
            prompt_id="prompt_catalog_versions_a",
            version="1.0.0",
            content="version one",
        )
        await _seed_prompt(
            database_url,
            prompt_id="prompt_catalog_versions_b",
            version="2.0.0",
            content="version two",
        )
        engine = build_engine(database_url)
        try:
            catalog = SqlPromptCatalog(engine)

            first = await catalog.render(
                PromptRenderRequest(prompt_id="prompt_catalog_versions_a", version="1.0.0")
            )
            second = await catalog.render(
                PromptRenderRequest(prompt_id="prompt_catalog_versions_b", version="2.0.0")
            )

            assert first.content == "version one"
            assert second.content == "version two"
        finally:
            await engine.dispose()

    asyncio.run(_run())
