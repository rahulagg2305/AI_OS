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

from pathlib import Path

import pytest

from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.manifest_loader.loader import ManifestLoader
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context

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
