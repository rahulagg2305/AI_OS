"""Wraps a real :class:`~ai_os_kernel.prompt_engine.renderer.PromptEngine`
to satisfy :class:`ai_os_sdk.contracts.PromptRegistry`
(``platform_sdk_v1_scope.md`` step 6a).

**Implements, as real production code, exactly the conversion step 5's
tests proved lossless** — ``tests/unit/platform_sdk/
test_prompt_registry_adapter_conversion.py``'s two test-local functions
are the design this class now ships for real. This is the one adapter
in this package whose Protocol is a from-scratch pack-facing call
style rather than a narrowing of the wrapped object's own shape (§5.2's
decision block), so unlike the other two adapters here, every call
genuinely converts between two differently-shaped envelopes rather than
translating field names 1:1.
"""

from __future__ import annotations

from typing import Any

from ai_os_kernel.prompt_engine.models import PromptRenderRequest
from ai_os_kernel.prompt_engine.renderer import PromptEngine
from ai_os_sdk.models.prompt import RenderedPrompt


class PromptRegistryAdapter:
    """Satisfies :class:`ai_os_sdk.contracts.PromptRegistry` by
    delegating to a real, injected :class:`PromptEngine`.

    Accepts any real implementation — ``InMemoryPromptEngine`` (tests,
    and any caller with no catalog-backed prompt) or
    ``SqlPromptCatalog`` (``catalog.prompts``-backed) — since both
    satisfy the identical, real ``PromptEngine`` Protocol.
    """

    def __init__(self, engine: PromptEngine) -> None:
        self._engine = engine

    async def render(
        self, prompt_id: str, variables: dict[str, Any], *, version: str
    ) -> RenderedPrompt:
        request = PromptRenderRequest(prompt_id=prompt_id, version=version, variables=variables)
        response = await self._engine.render(request)
        return RenderedPrompt(
            prompt_id=response.prompt_id, version=response.version, content=response.content
        )
