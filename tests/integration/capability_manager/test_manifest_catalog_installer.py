"""Real, before/after proof that
:meth:`~ai_os_kernel.capability_manager.repository.SqlPackLifecycleRepository.register`'s
new ``pack_root=`` path genuinely derives and writes real
``catalog.agents``/``catalog.prompts``/``catalog.tools`` rows from a
pack's own manifest — replacing the raw-SQL hand-seeding this step
removes from every integration test that used to duplicate it.

Registers the real, on-disk ``capability_packs/software-engineering``
pack (not a synthetic fixture) and reads the resulting rows back
directly from Postgres, comparing them against the real manifest's own
declared values — not against a hand-copied literal, so a future
manifest edit that this installer stops tracking correctly would show
up here as a real, structural mismatch, not a stale hardcoded
expectation.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
import yaml
from alembic import command
from alembic.config import Config
from pydantic import BaseModel

from ai_os_kernel.capability_manager.errors import PackRegistrationError
from ai_os_kernel.capability_manager.manifest_catalog_installer import (
    derive_agent_rows,
    derive_prompt_rows,
    derive_tool_rows,
)
from ai_os_kernel.capability_manager.repository import SqlPackLifecycleRepository
from ai_os_kernel.persistence.catalog_schema import agents, prompts, tools, workflow_definitions
from ai_os_kernel.persistence.engine import build_engine
from ai_os_pack_software_engineering.agents.api_designer import ApiDesignerAgentOutput
from ai_os_pack_software_engineering.agents.architecture import ArchitectureProposalOutput
from ai_os_pack_software_engineering.agents.build import BuildAgentOutput
from ai_os_pack_software_engineering.agents.code_review import CodeReviewerAgentOutput
from ai_os_pack_software_engineering.agents.database import DatabaseAgentOutput
from ai_os_pack_software_engineering.agents.documentation import DocumentationAgentOutput
from ai_os_pack_software_engineering.agents.git_push import GitPushAgentOutput
from ai_os_pack_software_engineering.agents.lint import LintAgentOutput
from ai_os_pack_software_engineering.agents.release import ReleaseAgentOutput
from ai_os_pack_software_engineering.agents.requirements_analyst import (
    RequirementsAnalysisOutput,
)
from ai_os_pack_software_engineering.agents.security_analysis import SecurityAnalysisOutput
from ai_os_pack_software_engineering.agents.verification import TestAgentOutput
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
PACK_ROOT = REPO_ROOT / "capability_packs" / "software-engineering"
PACK_ID = "software-engineering"
PACK_VERSION = "0.1.0"

# The real manifest's own declared permissions, read directly here (not
# copied from any test fixture) so this test's own expectations are
# grounded in the same source of truth the installer itself reads —
# confirms the installer derives each agent's *own* real permissions,
# not the pack's aggregate (the discovered bug this installer fixes;
# see manifest_catalog_installer.py's own docstring).
_EXPECTED_PERMISSIONS = {
    "requirements-analyst": ["llm:invoke"],
    "architecture": ["llm:invoke"],
    "build": ["llm:invoke", "sandbox:execute"],
    "lint": ["sandbox:execute"],
    "qa-test": ["sandbox:execute"],
    "documentation": ["llm:invoke", "sandbox:execute"],
    "database": ["llm:invoke", "sandbox:execute"],
    "api-designer": ["llm:invoke", "sandbox:execute"],
    "security-analysis": ["sandbox:execute"],
    "release": ["llm:invoke", "sandbox:execute"],
    "code-review": ["llm:invoke", "sandbox:execute"],
    "git-push": ["sandbox:execute", "git:write"],
}
_EXPECTED_OUTPUT_MODELS: dict[str, type[BaseModel]] = {
    "requirements-analyst": RequirementsAnalysisOutput,
    "architecture": ArchitectureProposalOutput,
    "build": BuildAgentOutput,
    "lint": LintAgentOutput,
    "qa-test": TestAgentOutput,
    "documentation": DocumentationAgentOutput,
    "database": DatabaseAgentOutput,
    "api-designer": ApiDesignerAgentOutput,
    "security-analysis": SecurityAnalysisOutput,
    "release": ReleaseAgentOutput,
    "code-review": CodeReviewerAgentOutput,
    "git-push": GitPushAgentOutput,
}


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


def _load_real_manifest() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(
        (PACK_ROOT / "manifest.yaml").read_text(encoding="utf-8")
    )
    return loaded


def test_registering_the_real_pack_derives_real_agent_prompt_and_tool_rows(
    database_url: str,
) -> None:
    async def _run() -> None:
        manifest = _load_real_manifest()
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
                reason="manifest catalog installer proof",
                pack_root=PACK_ROOT,
            )

            async with engine.connect() as connection:
                agent_rows = (
                    (await connection.execute(sa.select(agents).where(agents.c.pack_id == PACK_ID)))
                    .mappings()
                    .all()
                )
                prompt_rows = (
                    (
                        await connection.execute(
                            sa.select(prompts).where(prompts.c.pack_id == PACK_ID)
                        )
                    )
                    .mappings()
                    .all()
                )
                tool_rows = (
                    (await connection.execute(sa.select(tools).where(tools.c.pack_id == PACK_ID)))
                    .mappings()
                    .all()
                )
                workflow_definition_rows = (
                    (
                        await connection.execute(
                            sa.select(workflow_definitions).where(
                                workflow_definitions.c.pack_id == PACK_ID
                            )
                        )
                    )
                    .mappings()
                    .all()
                )
        finally:
            await engine.dispose()

        # --- agents: real row for each of the 12 real, declared agents ---
        assert len(agent_rows) == 12
        by_agent_id = {row["agent_id"]: row for row in agent_rows}
        for manifest_agent in manifest["agents"]:
            slug = manifest_agent["id"]
            row = by_agent_id[f"{PACK_ID}/{slug}"]
            assert row["pack_id"] == PACK_ID
            # Each agent's own declared version, not the pack's aggregate
            # (numerically equal here, but derived independently).
            assert row["version"] == manifest_agent["version"]
            assert row["entrypoint"] == manifest_agent["entrypoint"]
            # The real, discovered bug this installer fixes: each
            # agent's own exact permission set, not a uniform
            # over-grant. Compared as sets since the manifest doesn't
            # guarantee list order.
            assert set(row["required_permissions"]) == set(_EXPECTED_PERMISSIONS[slug])
            assert row["required_tools"] == []
            # The real, resolved output model's own JSON schema —
            # proves the installer actually resolved the dotted import
            # path, not a placeholder `{}`.
            assert row["output_schema"] == _EXPECTED_OUTPUT_MODELS[slug].model_json_schema()

        # --- prompts: real row for each of the 8 real, shipped prompts ---
        assert len(prompt_rows) == 8
        by_prompt_id = {(row["prompt_id"], row["version"]): row for row in prompt_rows}
        for manifest_prompt in manifest["prompts"]:
            row = by_prompt_id[(manifest_prompt["id"], manifest_prompt["version"])]
            assert row["pack_id"] == PACK_ID
            real_content = (PACK_ROOT / manifest_prompt["location"]).read_text(encoding="utf-8")
            assert row["content"] == real_content
            assert row["content_hash"] == (
                f"sha256:{hashlib.sha256(real_content.encode('utf-8')).hexdigest()}"
            )

        # --- tools: the real pack declares none — genuinely zero rows,
        # not silently skipped ---
        assert tool_rows == []

        # --- workflow_definitions (P03-S05-M14-T10): the real pack
        # declares one, se.delivery_pipeline, with a real, non-empty
        # permission ceiling — the workflow term of ADR-0023's
        # monotonic-narrowing chain, genuinely sourced from this same
        # manifest, not left at register()'s own [] default. ---
        assert len(workflow_definition_rows) == 1
        by_definition_id = {
            (row["definition_id"], row["version"]): row for row in workflow_definition_rows
        }
        for manifest_workflow in manifest["workflows"]:
            row = by_definition_id[(manifest_workflow["id"], manifest_workflow["version"])]
            assert row["pack_id"] == PACK_ID
            assert set(row["declared_permissions"]) == set(manifest_workflow["permissions"])
            # inputs_schema/outputs_schema come from the workflow
            # *definition file*'s own inline inputs/outputs (loaded via
            # WorkflowDefinitionLoader) — a different source from the
            # manifest's own inputsSchema/outputsSchema (a Pydantic
            # import path, resolved only by derive_agent_rows-style
            # installers); declared_permissions above is the one field
            # this row genuinely takes from the manifest.
            definition_path = PACK_ROOT / manifest_workflow["definition"]
            real_definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
            assert row["inputs_schema"] == real_definition["inputs"]
            assert row["outputs_schema"] == real_definition["outputs"]

    asyncio.run(_run())


def test_a_synthetic_tool_declaration_is_derived_correctly_even_though_unexercised_today() -> None:
    """The real pack declares zero tools, so the row-by-row proof above
    can never exercise :func:`derive_tool_rows` — proven separately here
    against a synthetic manifest fragment, the same "build it real,
    prove it against synthetic input since no real data exists yet"
    shape `ai_os_sdk.testing.pack_contract_suite`'s own check 5 already
    established for an analogous currently-unexercised case."""
    manifest = {
        "tools": [
            {
                "id": "example.tool",
                "version": "0.1.0",
                "entrypoint": "ai_os_kernel.workflow_engine.tool:EchoTool",
                "trustTier": "tier1_sandboxed",
                "inputSchema": (
                    "ai_os_pack_software_engineering.agents.build:BuildInstructionInput"
                ),
                "outputSchema": "ai_os_pack_software_engineering.agents.build:BuildAgentOutput",
                "permissions": ["sandbox:execute"],
            }
        ]
    }

    rows = derive_tool_rows(manifest, pack_id="example-pack")

    assert rows == [
        {
            "tool_id": "example.tool",
            "pack_id": "example-pack",
            "version": "0.1.0",
            "entrypoint": "ai_os_kernel.workflow_engine.tool:EchoTool",
            "trust_tier": "tier1_sandboxed",
            "input_schema": _resolve_expected_schema(
                "ai_os_pack_software_engineering.agents.build:BuildInstructionInput"
            ),
            "output_schema": BuildAgentOutput.model_json_schema(),
            "required_permissions": ["sandbox:execute"],
        }
    ]


def _resolve_expected_schema(dotted: str) -> dict[str, Any]:
    module_name, _, attribute_name = dotted.partition(":")
    model = getattr(importlib.import_module(module_name), attribute_name)
    schema: dict[str, Any] = model.model_json_schema()
    return schema


def test_derive_agent_rows_raises_a_clear_error_for_an_unresolvable_input_schema() -> None:
    """A bad manifest reference fails closed with a clear error — never
    a raw `ImportError`/`AttributeError`, and never a silently-empty
    schema."""
    manifest = {
        "agents": [
            {
                "id": "broken",
                "version": "0.1.0",
                "entrypoint": "ai_os_kernel.workflow_engine.agent:EchoAgent",
                "inputSchema": "ai_os_pack_software_engineering.agents.build:NoSuchModel",
                "outputSchema": "ai_os_pack_software_engineering.agents.build:BuildAgentOutput",
                "permissions": [],
            }
        ]
    }

    with pytest.raises(PackRegistrationError, match="NoSuchModel"):
        derive_agent_rows(manifest, pack_id="example-pack")


def test_derive_prompt_rows_raises_a_clear_error_for_a_missing_location_file(
    tmp_path: Path,
) -> None:
    manifest = {
        "prompts": [
            {
                "id": "example.prompt",
                "version": "0.1.0",
                "location": "prompts/does_not_exist.md",
                "inputSchema": (
                    "ai_os_pack_software_engineering.agents.build:BuildInstructionInput"
                ),
            }
        ]
    }

    with pytest.raises(PackRegistrationError, match="does_not_exist.md"):
        derive_prompt_rows(manifest, pack_id="example-pack", pack_root=tmp_path)
