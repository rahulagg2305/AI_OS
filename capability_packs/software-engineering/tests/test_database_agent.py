"""Deterministic tests for the Database Agent — no live LLM call
(ADR-0004: a deterministic Protocol implementation is a legitimate
substitute), but a genuine, non-mocked sandbox: every write in this
file happens through a real ``LocalSubprocessSandbox``/real OS
subprocess, so a passing test means a real file genuinely exists on
disk afterward.

Mirrors ``test_build_agent.py``'s own real substitute exactly:
construct the agent with zero arguments (aside from
``working_directory``), then bind it a real ``PackContext`` via
``build_pack_context``/``bind_pack_context`` — the identical pattern
every SDK-native agent in this pack already establishes.

The real, FR-036-specific proof this file adds beyond ``build.py``'s
own shape: :func:`test_a_generated_migration_genuinely_applies_and_reverses_against_real_postgres`
takes this agent's own real output (``upSql``/``downSql``, from a
deterministic Echo completion) and runs both against a real Postgres
container — not a syntactic check, a genuine round-trip proof that the
DOWN half actually reverses the UP half. See
``docs/19_roadmap/tickets/P08/P08-S01-M29-T02.md`` for the design-fork
record (plain SQL up/down pair, chosen over an Alembic-integrated or
schema-diff-compiled artifact).
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from tests.integration._postgres_fixture import postgres_container

from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.database import (
    DatabaseAgentEntrypoint,
    DatabaseAgentOutput,
    DatabaseMigrationInput,
    DatabaseMigrationInstructionError,
    _parse_migration_instruction,
    _resolve_safe_relative_path,
    _split_up_down,
)
from ai_os_sdk.contracts import Agent as SdkAgent
from ai_os_sdk.contracts import PackContextReceiver

_AGENT_ID = "database"
_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_PROMPT_ID = "database.write_migration"
_PROMPT_VERSION = "0.1.0"


def _agent_with_prompt(
    template: str, *, working_directory: Path | None = None
) -> DatabaseAgentEntrypoint:
    """The real, zero-arg-constructed (aside from ``working_directory``)
    entrypoint, bound to a real ``PackContext`` — identical construction
    sequence to ``test_build_agent.py``'s own ``_agent_with_prompt``."""
    agent = DatabaseAgentEntrypoint(working_directory=working_directory)
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke", "sandbox:execute"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={(_PROMPT_ID, _PROMPT_VERSION): template}),
            sandbox=LocalSubprocessSandbox(),
        )
    )
    return agent


def _step() -> WorkflowStep:
    return WorkflowStep(
        id="write_migration",
        type=StepType.AGENT,
        agent_id=_AGENT_ID,
        prompt_id=_PROMPT_ID,
        prompt_version=_PROMPT_VERSION,
        model_alias="coding-strong",
    )


_MIGRATION_TEMPLATE = (
    "FILE_PATH: migrations/add_widgets_table.sql\n"
    "FILE_CONTENT_BEGIN\n"
    "-- UP\n"
    "CREATE TABLE widgets (\n"
    "  id INTEGER PRIMARY KEY,\n"
    "  name TEXT NOT NULL\n"
    ");\n"
    "\n"
    "-- DOWN\n"
    "DROP TABLE widgets;\n"
    "FILE_CONTENT_END"
)


def test_database_agent_entrypoint_constructs_with_zero_arguments() -> None:
    """The exact call EntrypointLoader/SqlAgentRegistry make in
    production — must succeed instantly, with no I/O."""
    agent = DatabaseAgentEntrypoint()

    assert agent.output_schema["required"] == [
        "workingDirectory",
        "filePath",
        "written",
        "exitCode",
        "stdout",
        "stderr",
        "instruction",
        "upSql",
        "downSql",
    ]


def test_the_entrypoint_satisfies_both_sdk_protocols() -> None:
    agent = DatabaseAgentEntrypoint()

    assert isinstance(agent, SdkAgent)
    assert isinstance(agent, PackContextReceiver)


@pytest.mark.asyncio
async def test_execute_before_bind_pack_context_raises_a_clear_error() -> None:
    agent = DatabaseAgentEntrypoint()

    with pytest.raises(DatabaseMigrationInstructionError, match="bind_pack_context"):
        await agent.execute(
            {
                "promptId": _PROMPT_ID,
                "promptVersion": _PROMPT_VERSION,
                "modelAlias": "coding-strong",
            }
        )


@pytest.mark.asyncio
async def test_database_agent_genuinely_writes_a_real_reversible_migration_through_the_sandbox(
    tmp_path: Path,
) -> None:
    """A WorkflowStep of type agent, dispatched through the real
    AgentStepExecutor, genuinely results in a real migration file
    existing in the sandbox working directory, with its UP/DOWN halves
    correctly split out."""
    agent = _agent_with_prompt(_MIGRATION_TEMPLATE, working_directory=tmp_path)
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)

    outputs = await executor.execute(_step())

    DatabaseAgentOutput.model_validate(outputs)
    assert outputs["written"] is True
    assert outputs["exitCode"] == 0
    written_file = tmp_path / "migrations" / "add_widgets_table.sql"
    assert written_file.is_file()
    assert "CREATE TABLE widgets" in outputs["upSql"]
    assert outputs["downSql"] == "DROP TABLE widgets;"
    assert "-- UP" not in outputs["upSql"]
    assert "-- DOWN" not in outputs["downSql"]


@pytest.mark.asyncio
async def test_database_agent_rejects_a_completion_with_no_down_section(tmp_path: Path) -> None:
    """FR-036's own "is reversible" criterion enforced as a real
    precondition: a completion with UP but no DOWN is refused before
    any sandbox call, not silently written as an irreversible file."""
    template = (
        "FILE_PATH: migrations/one_way.sql\n"
        "FILE_CONTENT_BEGIN\n"
        "-- UP\n"
        "CREATE TABLE widgets (id INTEGER PRIMARY KEY);\n"
        "FILE_CONTENT_END"
    )
    agent = _agent_with_prompt(template, working_directory=tmp_path)
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)

    with pytest.raises(DatabaseMigrationInstructionError, match="parseable '-- UP'/'-- DOWN'"):
        await executor.execute(_step())

    assert await asyncio.to_thread(lambda: list(tmp_path.rglob("*"))) == []


@pytest.mark.asyncio
async def test_database_agent_rejects_a_malformed_completion(tmp_path: Path) -> None:
    agent = _agent_with_prompt(
        "this completion follows no documented format at all", working_directory=tmp_path
    )
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)

    with pytest.raises(DatabaseMigrationInstructionError, match="did not follow the documented"):
        await executor.execute(_step())


@pytest.mark.asyncio
async def test_missing_required_invocation_fields_raise_a_clear_error() -> None:
    agent = _agent_with_prompt("unused")

    with pytest.raises(DatabaseMigrationInstructionError, match="promptId"):
        await agent.execute({"modelAlias": "coding-strong"})


def test_parse_migration_instruction_extracts_path_and_content() -> None:
    completion = "FILE_PATH: a/b.sql\nFILE_CONTENT_BEGIN\n-- UP\nx\n\n-- DOWN\ny\nFILE_CONTENT_END"

    path, content = _parse_migration_instruction(completion)

    assert path == "a/b.sql"
    assert "-- UP" in content
    assert "-- DOWN" in content


def test_split_up_down_extracts_both_halves() -> None:
    up_sql, down_sql = _split_up_down("-- UP\nCREATE TABLE t (id INT);\n\n-- DOWN\nDROP TABLE t;")

    assert up_sql == "CREATE TABLE t (id INT);"
    assert down_sql == "DROP TABLE t;"


def test_split_up_down_raises_a_clear_error_when_no_down_section_exists() -> None:
    with pytest.raises(DatabaseMigrationInstructionError, match="parseable"):
        _split_up_down("-- UP\nCREATE TABLE t (id INT);")


@pytest.mark.parametrize("malicious_path", ["../../outside.sql", "/etc/passwd"])
def test_resolve_safe_relative_path_rejects_paths_that_escape_the_working_directory(
    tmp_path: Path, malicious_path: str
) -> None:
    with pytest.raises(DatabaseMigrationInstructionError, match="resolves outside"):
        _resolve_safe_relative_path(tmp_path, malicious_path)


def test_database_migration_input_documents_the_agent_contract() -> None:
    DatabaseMigrationInput(design="Add a widgets table with an id and a name.")


@pytest.fixture(scope="module")
def database_url() -> Generator[str, None, None]:
    with postgres_container() as postgres:
        yield postgres.get_connection_url()


@pytest.mark.asyncio
async def test_a_generated_migration_genuinely_applies_and_reverses_against_real_postgres(
    tmp_path: Path, database_url: str
) -> None:
    """FR-036's own acceptance criterion, proven directly: "Migration
    applies cleanly and is reversible" — not a syntax check, a real
    round-trip against a real Postgres container. Runs this agent's own
    real ``upSql``/``downSql`` output (from a deterministic Echo
    completion, exactly as the agent would produce in production) and
    confirms the table genuinely exists after UP and genuinely does not
    after DOWN."""
    from ai_os_kernel.persistence.engine import build_engine

    agent = _agent_with_prompt(_MIGRATION_TEMPLATE, working_directory=tmp_path)
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)

    outputs = await executor.execute(_step())

    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(sa.text(outputs["upSql"]))
        async with engine.connect() as connection:
            exists_after_up = await connection.scalar(
                sa.text("SELECT to_regclass('public.widgets') IS NOT NULL")
            )
        assert exists_after_up is True

        async with engine.begin() as connection:
            await connection.execute(sa.text(outputs["downSql"]))
        async with engine.connect() as connection:
            exists_after_down = await connection.scalar(
                sa.text("SELECT to_regclass('public.widgets') IS NOT NULL")
            )
        assert exists_after_down is False
    finally:
        await engine.dispose()
