"""The ``PromptRegistry`` Protocol (``platform_sdk.md`` §5.2).

**This call style is a deliberate exception to this reconciliation's
general "prefer the working Kernel shape" bias** — the one interface
where the *documented* shape was kept in favour of the Kernel's own.
See §5.2's dated *v1.0.0 Reconciliation Decision* block
(``platform_sdk_v1_scope.md`` step 2a) for the full reasoning; in
short: the real ``PromptEngine.render`` takes a ``PromptRenderRequest``
envelope, which suits an internal seam passing requests between
components, but this is a *pack-facing* API whose caller writes one
line to render one prompt. A Protocol should be shaped for its caller,
not for the convenience of whatever implements it (ADR-0004).

**No Kernel object satisfies this Protocol today, and none is expected
to until step 6a.** This is a from-scratch definition of the SDK's own
call convention, not a narrowing of an existing shape — so, unlike
``Agent``/``Tool``/``LLMGateway``, there is no ``isinstance`` proof
against real code in this step. What *is* proven (see
``tests/unit/platform_sdk/test_prompt_registry_adapter_conversion.py``)
is that converting between this signature and the real
``PromptRenderRequest``/``PromptRenderResponse`` is a lossless,
three-line mapping — the adapter step 6a will actually ship is not
inventing a translation that does not exist yet, only writing it down
as production code.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ai_os_sdk.models.prompt import RenderedPrompt


@runtime_checkable
class PromptRegistry(Protocol):
    """The only route to a pack's versioned prompt assets.

    ``@runtime_checkable`` for the same reason, and with the same
    limitation, as every other Protocol in this package: the
    ``isinstance`` check proves member presence only, never signatures.
    """

    async def render(
        self, prompt_id: str, variables: dict[str, Any], *, version: str
    ) -> RenderedPrompt:
        """Render one prompt.

        ``version`` is a required keyword argument, not defaulted —
        nothing in this platform resolves a prompt version on a
        caller's behalf (that is the deferred Version Manager / Prompt
        Resolver's job), so accepting an omitted version here would
        mean either failing anyway or inventing a choice. A caller
        always names the exact version it wants.
        """
        ...
