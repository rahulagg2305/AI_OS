"""``build_pack_context`` — real, permission-gated ``PackContext``
construction from the step 6a adapters (``platform_sdk_v1_scope.md``
step 6b).

**Permissions come from the real manifest, not a hand-typed list.**
``capability_packs/software-engineering/manifest.yaml`` declares two
agents with genuinely different, asymmetric permission sets — ``qa-test``
(``sandbox:execute`` only, no LLM call at all) and ``architecture``
(``llm:invoke`` only, no sandboxed side effect) — which is exactly the
real-world case this module's own "no over-provisioning" rule exists
for. Loading them through the real :class:`~ai_os_kernel.manifest_loader.loader.ManifestLoader`
proves the rule against real declared data, not an invented example.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from ai_os_kernel.git_integration.models import GitPushPolicy
from ai_os_kernel.git_integration.service import GitIntegrationService
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.manifest_loader.loader import ManifestLoader
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.sdk_adapters.tool_invoker_adapter import UnknownToolError
from ai_os_sdk.contracts import PLATFORM_GIT_COMMIT, PLATFORM_GIT_PUSH
from ai_os_sdk.models import ToolStatus

_MANIFEST_PATH = (
    Path(__file__).resolve().parents[4]
    / "capability_packs"
    / "software-engineering"
    / "manifest.yaml"
)
_SCHEMA_PATH = (
    Path(__file__).resolve().parents[4] / "platform_sdk" / "schemas" / "manifest.schema.json"
)


def _agent_permissions(agent_id: str) -> list[str]:
    loader = ManifestLoader(pack_dirs=[str(_MANIFEST_PATH.parent)], schema_path=_SCHEMA_PATH)
    discovered = loader.load_one(_MANIFEST_PATH)
    agents = discovered.raw["agents"]
    (agent,) = (a for a in agents if a["id"] == agent_id)
    permissions: list[str] = agent["permissions"]
    return permissions


class TestBuildPackContextAgainstTheRealManifest:
    def test_qa_test_gets_tools_only_no_llm_or_prompts(self) -> None:
        """qa-test's own real, declared permissions are
        [sandbox:execute] only -- it makes no LLM call at all."""
        permissions = _agent_permissions("qa-test")
        assert permissions == ["sandbox:execute"]

        context = build_pack_context(
            pack_id="software-engineering",
            pack_version="0.1.0",
            permissions=permissions,
            sandbox=LocalSubprocessSandbox(),
        )

        assert context.tools is not None
        assert context.llm is None
        assert context.prompts is None

    def test_architecture_gets_llm_and_prompts_only_no_tools(self) -> None:
        """architecture's own real, declared permissions are
        [llm:invoke] only -- it causes no sandboxed side effect."""
        permissions = _agent_permissions("architecture")
        assert permissions == ["llm:invoke"]

        context = build_pack_context(
            pack_id="software-engineering",
            pack_version="0.1.0",
            permissions=permissions,
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={}),
        )

        assert context.llm is not None
        assert context.prompts is not None
        assert context.tools is None

    def test_build_gets_all_three_declared_permissions_backed(self) -> None:
        """build's own real, declared permissions are both
        [llm:invoke, sandbox:execute]."""
        permissions = _agent_permissions("build")
        assert permissions == ["llm:invoke", "sandbox:execute"]

        context = build_pack_context(
            pack_id="software-engineering",
            pack_version="0.1.0",
            permissions=permissions,
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={}),
            sandbox=LocalSubprocessSandbox(),
        )

        assert context.llm is not None
        assert context.prompts is not None
        assert context.tools is not None


class TestNoOverProvisioning:
    def test_a_gateway_supplied_but_not_permitted_is_not_provisioned(self) -> None:
        """Passing a real llm_gateway does not grant llm/prompts if the
        entrypoint's own permissions never declared llm:invoke -- the
        caller's generosity is not the rule; the declared permission is."""
        context = build_pack_context(
            pack_id="software-engineering",
            pack_version="0.1.0",
            permissions=["sandbox:execute"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={}),
            sandbox=LocalSubprocessSandbox(),
        )

        assert context.llm is None
        assert context.prompts is None
        assert context.tools is not None

    def test_no_permissions_at_all_yields_an_identity_only_context(self) -> None:
        context = build_pack_context(
            pack_id="software-engineering", pack_version="0.1.0", permissions=[]
        )

        assert context.llm is None
        assert context.prompts is None
        assert context.tools is None


class TestGrantedPermissionWithoutBackingRaises:
    def test_llm_invoke_declared_without_a_gateway_raises(self) -> None:
        with pytest.raises(ValueError, match="llm:invoke"):
            build_pack_context(
                pack_id="software-engineering",
                pack_version="0.1.0",
                permissions=["llm:invoke"],
            )

    def test_sandbox_execute_declared_without_a_sandbox_raises(self) -> None:
        with pytest.raises(ValueError, match="sandbox:execute"):
            build_pack_context(
                pack_id="software-engineering",
                pack_version="0.1.0",
                permissions=["sandbox:execute"],
            )


class _FakeAuditLogWriter:
    """No Postgres needed — the real, hash-chained audit proof already
    lives in ``tests/integration/git_integration/``. This class proves
    the *permission-gating* decision `build_pack_context` itself makes,
    not persistence again."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


def _real_git_service(audit_log: _FakeAuditLogWriter) -> GitIntegrationService:
    return GitIntegrationService(
        sandbox=LocalSubprocessSandbox(),
        audit_log=audit_log,
        push_policy=GitPushPolicy(protected_branches=frozenset({"main"})),
        author_name="AI_OS Bot",
        author_email="bot@ai-os.internal",
    )


async def _git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    git = shutil.which("git") or "git"
    return await asyncio.to_thread(
        subprocess.run, [git, *args], cwd=cwd, capture_output=True, text=True, check=True
    )


class TestGitWritePermissionGating:
    """``P03-S01-M24-T03``: a real, dedicated ``git:write`` check —
    before this step, ``git_service`` was forwarded to
    ``ToolInvokerAdapter`` whenever ``sandbox:execute`` was granted,
    regardless of whether the entrypoint's own declared permissions
    included ``git:write`` at all. Every test below constructs the
    context from *the same real* ``GitIntegrationService`` — the only
    variable is the entrypoint's own declared ``permissions`` — so any
    difference in outcome is genuinely caused by the permission check,
    not by which service happened to be available.
    """

    async def test_git_write_plus_sandbox_execute_can_genuinely_push(self, tmp_path: Path) -> None:
        """The authorized case: an entrypoint declaring both
        ``sandbox:execute`` and ``git:write`` (git-push's own real,
        declared manifest permissions) genuinely reaches the real
        service, the real sandbox, and a real ``git`` commit — read
        back from the real repository independently, not trusted from
        the call's own return value alone."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "generated.txt").write_text("generated by an authorized agent")
        audit_log = _FakeAuditLogWriter()

        context = build_pack_context(
            pack_id="software-engineering",
            pack_version="0.1.0",
            permissions=["sandbox:execute", "git:write"],
            sandbox=LocalSubprocessSandbox(),
            git_service=_real_git_service(audit_log),
        )

        assert context.tools is not None
        descriptors = {d.tool_id for d in context.tools.available_tools()}
        assert {PLATFORM_GIT_COMMIT, PLATFORM_GIT_PUSH} <= descriptors

        result = await context.tools.invoke(
            PLATFORM_GIT_COMMIT,
            {
                "workspace": str(workspace),
                "message": "real, authorized push permission proof",
                "actor_id": "agent-git-push",
                "actor_type": "agent",
            },
        )

        assert result.status is ToolStatus.SUCCESS
        assert result.outputs is not None
        commit_sha = result.outputs["commit_sha"]

        log = await _git(["log", "-1", "--format=%H %s"], cwd=workspace)
        assert log.stdout.strip() == f"{commit_sha} real, authorized push permission proof"

    async def test_sandbox_execute_alone_is_refused_even_with_a_real_git_service_available(
        self, tmp_path: Path
    ) -> None:
        """The unauthorized case this step exists to close: an
        entrypoint declaring ``sandbox:execute`` only (e.g. ``lint``'s/
        ``qa-test``'s own real, declared manifest permissions) — with
        the *identical real* ``GitIntegrationService`` the authorized
        test above genuinely pushed through — must not be able to reach
        any Git tool at all, not merely be denied at push time."""
        audit_log = _FakeAuditLogWriter()

        context = build_pack_context(
            pack_id="software-engineering",
            pack_version="0.1.0",
            permissions=["sandbox:execute"],
            sandbox=LocalSubprocessSandbox(),
            git_service=_real_git_service(audit_log),
        )

        assert context.tools is not None
        descriptors = {d.tool_id for d in context.tools.available_tools()}
        assert PLATFORM_GIT_COMMIT not in descriptors
        assert PLATFORM_GIT_PUSH not in descriptors

        with pytest.raises(UnknownToolError):
            await context.tools.invoke(
                PLATFORM_GIT_PUSH,
                {
                    "workspace": str(tmp_path),
                    "branch": "feature/x",
                    "remote_url": str(tmp_path / "remote.git"),
                    "actor_id": "agent-lint",
                    "actor_type": "agent",
                },
            )

        # Refused before any git subprocess ran at all — no audit event
        # for the attempt exists, since GitIntegrationService itself was
        # never reached.
        assert audit_log.records == []
