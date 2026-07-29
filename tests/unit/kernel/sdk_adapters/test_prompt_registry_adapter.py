"""``PromptRegistryAdapter`` — real, against a real
:class:`~ai_os_kernel.prompt_engine.renderer.InMemoryPromptEngine`
(``platform_sdk_v1_scope.md`` step 6a).
"""

from __future__ import annotations

import pytest

from ai_os_kernel.prompt_engine.errors import PromptNotFoundError
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sdk_adapters.prompt_registry_adapter import PromptRegistryAdapter
from ai_os_sdk.contracts import PromptRegistry as SdkPromptRegistry

_PROMPT_ID = "requirements.analyze"
_VERSION = "0.1.0"
_TEMPLATE = "Analyze the following requirement: {{requirement}}"


def _real_adapter() -> PromptRegistryAdapter:
    engine = InMemoryPromptEngine(templates={(_PROMPT_ID, _VERSION): _TEMPLATE})
    return PromptRegistryAdapter(engine)


class TestPromptRegistryAdapterSatisfiesTheProtocol:
    def test_the_adapter_itself_is_an_sdk_prompt_registry(self) -> None:
        assert isinstance(_real_adapter(), SdkPromptRegistry)


class TestRenderAgainstARealPromptEngine:
    async def test_a_real_render_round_trips_through_both_conversions(self) -> None:
        adapter = _real_adapter()

        rendered = await adapter.render(
            _PROMPT_ID, {"requirement": "add rate limiting"}, version=_VERSION
        )

        assert rendered.prompt_id == _PROMPT_ID
        assert rendered.version == _VERSION
        assert rendered.content == "Analyze the following requirement: add rate limiting"

    async def test_the_documented_one_line_call_style_works_end_to_end(self) -> None:
        """The exact call the step 5 decision block cites as the reason
        this Protocol shape was kept over the Kernel's own envelope."""
        adapter = _real_adapter()

        rendered = await adapter.render(
            "requirements.analyze", {"requirement": "x"}, version="0.1.0"
        )

        assert "x" in rendered.content

    async def test_an_unregistered_prompt_raises_the_real_kernel_error(self) -> None:
        """The adapter does not swallow or reshape the real engine's own
        error -- a caller sees exactly what InMemoryPromptEngine raises."""
        adapter = _real_adapter()

        with pytest.raises(PromptNotFoundError):
            await adapter.render("nonexistent.prompt", {}, version="9.9.9")

    async def test_version_must_be_supplied_as_a_keyword(self) -> None:
        """version=None is not accepted anywhere in this call -- it must
        be named and real, per the step 2a decision to narrow it to
        required."""
        adapter = _real_adapter()

        with pytest.raises(TypeError):
            await adapter.render(_PROMPT_ID, {}, _VERSION)  # type: ignore[misc]
