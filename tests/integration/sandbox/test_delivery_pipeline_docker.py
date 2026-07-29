"""The real, hardened proof this step exists for: the same four-step
Software Engineering delivery pipeline `test_delivery_pipeline.py`
already proves end to end through `LocalSubprocessSandbox`, run again
here through real `DockerSandbox` instances — and, unlike
`tests/integration/sandbox/test_docker_sandbox_live.py`'s own isolated
guarantee tests (which run a hand-picked command directly against one
`DockerSandbox`), this test's own network-isolation and filesystem-
containment proof happens *inside a file the pipeline itself generated
and ran*, as part of one real, continuous Architecture -> Build -> Test
-> Documentation run — not as a separate, self-contained check.

**Why this is a materially stronger proof than "DockerSandbox's own
guarantees hold in isolation."** Every other real proof of network
isolation/filesystem containment in this codebase constructs a
`DockerSandbox` directly and hands it a command this test file itself
wrote. Here, the Build Agent's own (Echo-backed, deterministic)
completion supplies the probe script's content — the identical code
path a real, live LLM completion would take — and the Test Agent's own
`SandboxedCommandTool` genuinely executes it, through the pipeline's
own real `WorkflowStepOutputResolver` hand-off, with no shortcut. The
probe script's own two checks (an external socket connect, a write
outside its own working directory) both attempt something a hostile or
merely careless piece of generated code might genuinely try — and both
must genuinely fail, observed from *inside* the running pipeline's own
persisted Test-step output, not asserted by this test file constructing
its own container.

**Needs a real Postgres *and* a real Docker daemon.** Both this test's
own `database_url` fixture (via `postgres_container()`, ADR-0015's
established clean-skip pattern) and every sandboxed step in this run
need Docker; `postgres_container()`'s own skip already covers "Docker is
unreachable" for both needs at once — no second, redundant Docker check
is added here.

**All four agents this pipeline chains — qa-test (step 9), architecture
(step 11), build (step 12), and now documentation (step 13) — are
migrated onto the Platform SDK. This pipeline is now fully migrated.**
This file's own `InMemoryAgentRegistry` construction was updated to
match, mirroring `test_delivery_pipeline.py`'s own identical fix:
`_test_agent_with_sandbox`/`_architecture_agent_with_prompt`/
`_build_agent_with_prompt`/`_documentation_agent_with_prompt` construct
each zero-arg (aside from build's own `working_directory`) and
`bind_pack_context()` it instead of passing a `sandbox=`/`service_factory=`
constructor override that no longer exists. Build's and Documentation's
own writes now happen through `context.tools.invoke`
(`platform.sandbox.run_command`) against a real `DockerSandbox`, not a
directly constructed `SandboxedCommandTool` — this test is this pack's
most important real proof of that path, since the generated probe
script's own network/filesystem-escape attempts must still genuinely
fail when written and run this way. **Step 12a (inserted, 2026-07-29)**
removed `BuildAgentEntrypoint`'s own `python_command` constructor
parameter entirely — `ToolInvokerAdapter` now resolves the real
interpreter command (`python3`, correct for this real `DockerSandbox`)
itself for both Build and Documentation, neither of which passes one.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from tests.integration._delivery_pipeline import build_pipeline_trigger
from tests.integration._postgres_fixture import postgres_container

from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sandbox.docker_executor import DockerSandbox
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_pack_software_engineering.agents.architecture import ArchitectureAgentEntrypoint
from ai_os_pack_software_engineering.agents.build import BuildAgentEntrypoint
from ai_os_pack_software_engineering.agents.documentation import DocumentationAgentEntrypoint
from ai_os_pack_software_engineering.agents.verification import TestAgentEntrypoint

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"

_AGENT_IDS = {
    "architecture": "software-engineering/architecture",
    "build": "software-engineering/build",
    "test": "software-engineering/qa-test",
    "documentation": "software-engineering/documentation",
}


def _test_agent_with_sandbox(sandbox: DockerSandbox) -> TestAgentEntrypoint:
    """qa-test is migrated onto the Platform SDK (step 9) — no more
    ``sandbox=`` constructor override. Construct zero-arg, exactly as
    ``EntrypointLoader`` does, then bind the real ``PackContext`` a real
    caller would inject, granting exactly ``sandbox:execute``."""
    agent = TestAgentEntrypoint()
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["sandbox:execute"],
            sandbox=sandbox,
        )
    )
    return agent


def _architecture_agent_with_prompt(template: str, prompt_id: str) -> ArchitectureAgentEntrypoint:
    """architecture is migrated onto the Platform SDK (step 11) — no
    more ``service_factory`` constructor override. Construct zero-arg,
    exactly as ``EntrypointLoader`` does, then bind the real
    ``PackContext`` a real caller would inject, granting exactly
    ``llm:invoke`` — mirrors `test_delivery_pipeline.py`'s own identical
    helper."""
    agent = ArchitectureAgentEntrypoint()
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={(prompt_id, "0.1.0"): template}),
        )
    )
    return agent


def _build_agent_with_prompt(
    template: str, prompt_id: str, *, working_directory: Path
) -> BuildAgentEntrypoint:
    """build is migrated onto the Platform SDK (step 12) — no more
    ``service_factory``/``sandbox`` constructor overrides. Construct
    zero-arg (aside from ``working_directory``), then bind the real
    ``PackContext`` a real caller would inject, granting both
    ``llm:invoke`` and ``sandbox:execute`` over a real ``DockerSandbox``
    — mirrors `test_delivery_pipeline.py`'s own identical helper. No
    ``python_command`` to supply any more (step 12a) — ``ToolInvokerAdapter``
    resolves the real, portable interpreter invocation itself, from the
    same ``DockerSandbox`` instance passed to ``build_pack_context``
    below, automatically."""
    agent = BuildAgentEntrypoint(working_directory=working_directory)
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke", "sandbox:execute"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={(prompt_id, "0.1.0"): template}),
            sandbox=DockerSandbox(),
        )
    )
    return agent


def _documentation_agent_with_prompt(template: str, prompt_id: str) -> DocumentationAgentEntrypoint:
    """documentation is migrated onto the Platform SDK (step 13) — the
    fifth and final migration. Construct zero-arg (this agent needs no
    ``working_directory`` override — it always reuses the caller-supplied
    one), then bind the real ``PackContext`` a real caller would inject,
    granting both ``llm:invoke`` and ``sandbox:execute`` over a real
    ``DockerSandbox`` — mirrors `test_delivery_pipeline.py`'s own
    identical helper. No ``python_command`` to supply (step 12a) —
    ``ToolInvokerAdapter`` resolves the real, portable interpreter
    invocation itself, from the same ``DockerSandbox`` instance passed
    to ``build_pack_context`` below, automatically."""
    agent = DocumentationAgentEntrypoint()
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke", "sandbox:execute"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={(prompt_id, "0.1.0"): template}),
            sandbox=DockerSandbox(),
        )
    )
    return agent


# The generated file the pipeline itself writes and runs — real code
# taking the real, deterministic Build completion path, not a command
# this test file hands directly to a sandbox. Both checks attempt
# something ADR-0016 Tier 1 must genuinely refuse: reaching the network,
# and writing outside the one mounted working directory.
_PROBE_SCRIPT = (
    "import socket\n"
    "\n"
    "network_blocked = False\n"
    "try:\n"
    '    socket.create_connection(("8.8.8.8", 53), timeout=3)\n'
    "except OSError:\n"
    "    network_blocked = True\n"
    "\n"
    "filesystem_contained = False\n"
    "try:\n"
    '    with open("/etc/should-not-be-writable-by-generated-code", "w") as handle:\n'
    '        handle.write("escape attempt")\n'
    "except OSError:\n"
    "    filesystem_contained = True\n"
    "\n"
    'print(f"NETWORK_BLOCKED={network_blocked}")\n'
    'print(f"FILESYSTEM_CONTAINED={filesystem_contained}")\n'
)


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


@pytest.mark.asyncio
async def test_the_real_pipeline_through_docker_sandbox_genuinely_contains_generated_code(
    tmp_path: Path, database_url: str
) -> None:
    """The real end-to-end proof this step exists for: the same
    Architecture -> Build -> Test -> Documentation hand-off
    `test_delivery_pipeline.py` proves through `LocalSubprocessSandbox`,
    run here through real `DockerSandbox` instances, with the Test
    step's own real, persisted output showing that a network-escape
    attempt and a filesystem-escape attempt — both made by code the
    pipeline itself generated and ran — genuinely failed."""

    build_template = (
        "Upstream design: {{context}}\n\n"
        "FILE_PATH: probe.py\n"
        "FILE_CONTENT_BEGIN\n"
        f"{_PROBE_SCRIPT}"
        "FILE_CONTENT_END"
    )

    documentation_template = (
        "# {{filePath}}\n\n"
        "Instruction: {{instruction}}\n"
        "Passed: {{passed}} (exit {{exitCode}})\n"
        "Output: {{output}}"
    )

    registry = InMemoryAgentRegistry(
        {
            _AGENT_IDS["architecture"]: _architecture_agent_with_prompt(
                "DESIGN: a single Python script that probes its own sandbox.\n"
                "Context was: {{context}}",
                "architecture.propose_design",
            ),
            _AGENT_IDS["build"]: _build_agent_with_prompt(
                build_template, "build.write_file", working_directory=tmp_path
            ),
            _AGENT_IDS["test"]: _test_agent_with_sandbox(DockerSandbox()),
            _AGENT_IDS["documentation"]: _documentation_agent_with_prompt(
                documentation_template, "documentation.record_artifact"
            ),
        }
    )

    engine = build_engine(database_url)
    try:
        # Matches the explicit `sandbox=DockerSandbox()` given to every
        # agent above — passed explicitly rather than relying on this
        # happening to also be the ambient AIOS_SANDBOX_BACKEND default;
        # see `_delivery_pipeline.py`'s own docstring for the bug this avoids.
        trigger = build_pipeline_trigger(
            engine, registry, python_command=DockerSandbox().python_command
        )

        result = await trigger(
            {"requirement": "write a script that checks its own sandbox isolation"},
            "test-principal",
        )

        assert result.outcome == WorkflowRunOutcome.COMPLETED, result.error
        assert result.last_instance is not None

        # Filesystem containment, the "one writable path" direction:
        # a real container wrote this file, and it is genuinely visible
        # on the host afterward, through the real bind mount.
        written_file = tmp_path / "probe.py"
        assert written_file.is_file()

        steps = await SqlWorkflowInstanceRepository(engine).list_steps(
            result.last_instance.workflow_id
        )
        test_outputs = next(s.outputs for s in steps if s.step_name == "test")
        assert test_outputs is not None
        assert test_outputs["passed"] is True, test_outputs["output"]

        # The real proof: code the pipeline itself generated and ran,
        # through a real DockerSandbox, genuinely could not reach the
        # network and genuinely could not write outside its one mounted
        # working directory — observed from the Test step's own real,
        # persisted output, not asserted by this test constructing its
        # own container.
        assert "NETWORK_BLOCKED=True" in test_outputs["output"]
        assert "FILESYSTEM_CONTAINED=True" in test_outputs["output"]

        doc_file = tmp_path / "probe.py.md"
        assert doc_file.is_file()
        assert "Passed: true" in doc_file.read_text(encoding="utf-8")
    finally:
        await engine.dispose()
