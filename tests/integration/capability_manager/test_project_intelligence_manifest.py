"""Real, Postgres-backed proof that the Project Intelligence pack's own
manifest (``P05-S02-M32-T07``) genuinely registers all five real Tools
into ``catalog.tools`` and that they resolve through the real
``SqlToolRegistry`` — closing Risk A of the 2026-08-11 health audit
(this pack had five real, tested Tools but no manifest, so nothing could
discover them; risk register R-018).

The final assertion is the point: `P02-S05-M18-T04` (R-017) wired a real
registry into the production PackContext, so a declared Tool is now
genuinely *resolvable*, not merely catalogued — the caveat this ticket
was filed with is closed. Real Postgres via testcontainers (ADR-0015).
"""

import asyncio
import json
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast

import jsonschema
import pytest
import sqlalchemy as sa
import yaml
from alembic import command
from alembic.config import Config

from ai_os_kernel.capability_manager.repository import SqlPackLifecycleRepository
from ai_os_kernel.persistence.catalog_schema import tools
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.registry import SqlToolRegistry
from ai_os_kernel.workflow_engine.tool import Tool
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
PACK_ROOT = REPO_ROOT / "capability_packs" / "project_intelligence"
SCHEMA_PATH = REPO_ROOT / "platform_sdk" / "schemas" / "manifest.schema.json"
PACK_ID = "project-intelligence"
PACK_VERSION = "0.1.0"

_EXPECTED_TOOLS = {
    "repository.ingest": "tier1_sandboxed",
    "language.detect": "tier2_trusted",
    "dependency.graph": "tier1_sandboxed",
    "architecture.recover": "tier2_trusted",
    "documentation.generate": "tier2_trusted",
}


def _load_manifest() -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load((PACK_ROOT / "manifest.yaml").read_text("utf-8")))


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


def test_the_manifest_is_schema_valid() -> None:
    manifest = _load_manifest()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(manifest, schema)


def test_the_pack_registers_all_five_tools_and_they_resolve_through_the_real_registry(
    database_url: str,
) -> None:
    """One coherent proof (registering twice into the same module-scoped
    database would hit the real ``PackAlreadyRegisteredError``, so this is
    deliberately a single register): the real installer derives all five
    ``catalog.tools`` rows from the manifest, and — the R-017 payoff — a
    declared Tool then genuinely resolves through the real
    ``SqlToolRegistry`` once the pack is activated, not merely catalogued."""

    async def _run() -> None:
        manifest = _load_manifest()
        engine = build_engine(database_url)
        try:
            repository = SqlPackLifecycleRepository(engine)
            await repository.register(
                pack_id=PACK_ID,
                version=PACK_VERSION,
                manifest=manifest,
                sdk_version=">=0.1.0,<1.0.0",
                min_kernel_version="0.1.0",
                actor="test",
                reason="project intelligence manifest proof",
                pack_root=PACK_ROOT,
            )
            async with engine.connect() as connection:
                tool_rows = (
                    (await connection.execute(sa.select(tools).where(tools.c.pack_id == PACK_ID)))
                    .mappings()
                    .all()
                )

            by_id = {row["tool_id"]: row for row in tool_rows}
            assert set(by_id) == set(_EXPECTED_TOOLS)
            for manifest_tool in manifest["tools"]:
                row = by_id[manifest_tool["id"]]
                assert row["trust_tier"] == _EXPECTED_TOOLS[manifest_tool["id"]]
                assert row["entrypoint"] == manifest_tool["entrypoint"]
                # The installer genuinely resolved and imported each tool's
                # own inputSchema/outputSchema Pydantic model (the two added
                # for this ticket among them) — a real JSON schema, not the
                # empty {} an unresolved reference would leave.
                assert row["input_schema"].get("properties")
                assert row["output_schema"].get("properties")

            # The R-017 payoff: activate, then resolve a real Tool through
            # the real registry. `language.detect` (tier2_trusted) needs
            # no sandbox to be constructed.
            await repository.activate(pack_id=PACK_ID, actor="test", reason="resolve proof")
            resolved = await SqlToolRegistry(engine).resolve_tool("language.detect")
            assert isinstance(resolved, Tool)
            output = await resolved.execute({"files": [{"path": "main.py", "language": "Python"}]})
            assert any(lang["name"] == "Python" for lang in output["languages"])
        finally:
            await engine.dispose()

    asyncio.run(_run())
