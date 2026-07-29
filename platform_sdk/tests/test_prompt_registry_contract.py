"""Step 5 of ``platform_sdk_v1_scope.md``: the ``PromptRegistry``
Protocol itself (``platform_sdk.md`` §5.2, documented keyword call
style, ``version`` required).

**No real Kernel class satisfies this Protocol** — unlike ``Agent``,
``Tool``, and ``LLMGateway``, this is a from-scratch SDK call
convention, not a narrowing of an existing shape (see this Protocol's
own module docstring). There is therefore no cross-boundary
``isinstance`` proof for this step. What *is* proven — that the
real Kernel shapes convert losslessly to and from this one — lives in
``tests/unit/platform_sdk/test_prompt_registry_adapter_conversion.py``,
since that proof necessarily imports ``ai_os_kernel`` and belongs in
the root suite, not here.
"""

from typing import Any

import pytest

from ai_os_sdk.contracts import PromptRegistry
from ai_os_sdk.models import RenderedPrompt


class _MinimalRegistry:
    """Exactly the one member the Protocol requires."""

    async def render(
        self, prompt_id: str, variables: dict[str, Any], *, version: str
    ) -> RenderedPrompt:
        return RenderedPrompt(prompt_id=prompt_id, version=version, content="rendered")


class TestPromptRegistryProtocol:
    def test_a_conforming_object_satisfies_it(self) -> None:
        assert isinstance(_MinimalRegistry(), PromptRegistry)

    def test_an_object_missing_render_does_not(self) -> None:
        class NoRender:
            pass

        assert not isinstance(NoRender(), PromptRegistry)

    def test_isinstance_proves_presence_only_never_signatures(self) -> None:
        """The same limitation recorded for every other Protocol in this
        package: a runtime_checkable Protocol checks member presence,
        never signatures. This object's render() takes no arguments at
        all and isn't even async, yet it passes.
        """

        class WrongShapeEntirely:
            def render(self) -> str:
                return "not even async"

        assert isinstance(WrongShapeEntirely(), PromptRegistry)

    async def test_render_accepts_the_documented_keyword_call_style(self) -> None:
        """The exact call the decision block cites as the reason this
        shape was kept: one line, no envelope object."""
        registry = _MinimalRegistry()
        result = await registry.render(
            "requirements.analyze", {"requirement": "x"}, version="0.1.0"
        )
        assert result.prompt_id == "requirements.analyze"
        assert result.version == "0.1.0"

    async def test_version_is_keyword_only(self) -> None:
        """version=None is not accepted anywhere in this signature —
        it must be named and it must be a real value, per the step 2a
        decision to narrow it to required."""
        registry = _MinimalRegistry()
        with pytest.raises(TypeError):
            await registry.render("requirements.analyze", {}, "0.1.0")  # type: ignore[misc]
