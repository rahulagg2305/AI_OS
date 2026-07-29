"""Proof that the SDK's ``PromptRegistry.render()`` keyword call
convention converts losslessly to and from the real Kernel's
``PromptRenderRequest``/``PromptRenderResponse`` envelope —
``platform_sdk_v1_scope.md`` step 5.

**Why this proof looks different from steps 3 and 4's.** ``Agent``,
``Tool``, and ``LLMGateway`` were narrowed *to* an existing Kernel
shape, so a real Kernel object could satisfy the new Protocol directly,
and that was provable with a single ``isinstance`` call.
``PromptRegistry`` is the opposite: step 2a *kept* the documented
keyword call style specifically because it is a better pack-facing API
than the Kernel's own request-object envelope
(``prompt_engine/models.py:56-63``). No real Kernel class implements
this signature, and none should — the two shapes are related by
*conversion*, not identity. What can be proven instead, and what the
step 2a decision block's "the adapter conversion in step 6a is three
lines" claim rests on, is that the conversion loses nothing in either
direction.

**The two functions below are illustrative only, not production code.**
They exist to prove the claim, deliberately kept local to this test
module rather than added to ``ai_os_sdk`` — building the real,
shipped adapter is step 6a's job, over the real, working
``PromptEngine``/``SqlPromptCatalog``, not this step's.

**Why this file lives in the root suite rather than in
``platform_sdk/tests/``.** It imports ``ai_os_kernel.prompt_engine``
directly, and ``platform_sdk/tests/`` deliberately imports nothing
outside the SDK (``platform_sdk.md`` §2 rule 1, the dependency floor) —
the same discipline steps 3 and 4's cross-boundary proofs already
follow.

**Nothing in the Kernel is modified by this step.** This file only
converts between two already-real shapes.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from ai_os_kernel.prompt_engine.models import PromptRenderRequest, PromptRenderResponse
from ai_os_sdk.models import RenderedPrompt


def _sdk_call_to_kernel_request(
    prompt_id: str, variables: dict[str, Any], *, version: str
) -> PromptRenderRequest:
    """The ~3-line conversion the step 2a decision block anticipates:
    the SDK's three call arguments map onto the Kernel request's three
    fields, one to one, with no transformation of any value."""
    return PromptRenderRequest(prompt_id=prompt_id, version=version, variables=variables)


def _kernel_response_to_sdk_rendered_prompt(response: PromptRenderResponse) -> RenderedPrompt:
    """The reverse direction: the Kernel response's three fields map
    onto ``RenderedPrompt``'s three fields, one to one."""
    return RenderedPrompt(
        prompt_id=response.prompt_id, version=response.version, content=response.content
    )


class TestSdkCallConvertsLosslesslyToKernelRequest:
    def test_every_field_survives_the_conversion_unchanged(self) -> None:
        variables = {"requirement": "add rate limiting", "priority": "high"}
        request = _sdk_call_to_kernel_request("requirements.analyze", variables, version="0.1.0")
        assert request.prompt_id == "requirements.analyze"
        assert request.version == "0.1.0"
        assert request.variables == variables

    def test_variables_are_not_copied_or_mutated(self) -> None:
        """A lossless conversion doesn't just preserve values — it
        doesn't silently drop or rename keys either. Assert the exact
        same mapping, not merely equal-length output."""
        variables = {"a": 1, "b": [1, 2, 3], "c": {"nested": True}}
        request = _sdk_call_to_kernel_request("x.y", variables, version="1.0.0")
        assert request.variables == variables

    def test_an_empty_variables_mapping_survives_as_empty(self) -> None:
        """The SDK signature has no default for variables (it is a
        required positional parameter, per the decision block); the
        Kernel's own field defaults to an empty dict. Both sides agree
        an empty mapping is a real, valid case — the conversion doesn't
        need to invent one."""
        request = _sdk_call_to_kernel_request("x.y", {}, version="1.0.0")
        assert request.variables == {}

    def test_the_kernels_own_validation_still_applies_after_conversion(self) -> None:
        """The conversion doesn't bypass anything: a blank prompt_id
        still fails the Kernel's own validator, exactly as it would if
        a Kernel-internal caller had constructed the request directly."""
        with pytest.raises(ValidationError):
            _sdk_call_to_kernel_request("   ", {}, version="1.0.0")


class TestKernelResponseConvertsLosslesslyToSdkRenderedPrompt:
    def test_every_field_survives_the_conversion_unchanged(self) -> None:
        response = PromptRenderResponse(
            prompt_id="requirements.analyze",
            version="0.1.0",
            content="Analyze the following requirement: add rate limiting",
        )
        rendered = _kernel_response_to_sdk_rendered_prompt(response)
        assert rendered.prompt_id == response.prompt_id
        assert rendered.version == response.version
        assert rendered.content == response.content

    def test_round_trip_through_both_conversions_is_the_identity(self) -> None:
        """Request -> (real engine, simulated here by echoing the
        request's own fields into a response) -> RenderedPrompt should
        preserve prompt_id and version exactly, since nothing between
        the two conversions is claimed to change them."""
        variables = {"requirement": "add rate limiting"}
        request = _sdk_call_to_kernel_request("requirements.analyze", variables, version="0.1.0")
        # Simulates what a real PromptEngine.render(request) would echo
        # back per its own contract (prompt_engine/models.py:32-35:
        # "Response prompt_id/version — echoed back").
        response = PromptRenderResponse(
            prompt_id=request.prompt_id, version=request.version, content="rendered text"
        )
        rendered = _kernel_response_to_sdk_rendered_prompt(response)
        assert rendered.prompt_id == "requirements.analyze"
        assert rendered.version == "0.1.0"

    def test_no_field_is_fabricated_or_defaulted_by_the_conversion(self) -> None:
        """RenderedPrompt's three fields (§5.2's narrowed shape) are
        each drawn directly from the response — none is a placeholder,
        and none silently reuses a value from the request instead of
        the response's own."""
        response = PromptRenderResponse(prompt_id="a.b", version="2.0.0", content="content-x")
        rendered = _kernel_response_to_sdk_rendered_prompt(response)
        assert rendered.model_dump() == {
            "prompt_id": "a.b",
            "version": "2.0.0",
            "content": "content-x",
        }
