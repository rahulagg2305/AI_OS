"""A real, zero-argument-constructible test entrypoint proving the
:class:`~ai_os_sdk.contracts.PackContextReceiver` injection mechanism
(``platform_sdk_v1_scope.md`` step 6b).

Named with a leading underscore and imported by module path (not
``test_*.py``) so pytest never tries to collect it as a test module in
its own right — it exists to be loaded by
:class:`~ai_os_kernel.workflow_engine.entrypoint_loader.EntrypointLoader`
via ``tests.unit.kernel.sdk_adapters.
_pack_context_injection_fixtures:EchoCapabilityTestEntrypoint``, the
exact real mechanism a manifest's own ``agents[].entrypoint`` string
would name.

**Deliberately not migrating any real agent (steps 9-14) — this is the
"test entrypoint" step 6b's own approved scope calls for.** It mirrors
the *shape* every real Software Engineering pack agent already uses
(zero-arg ``__init__``, lazy real work no earlier than the first genuine
call), but proves the *generalized, SDK-level* mechanism replacing each
agent's own hand-rolled Kernel-reaching composition: it never builds
anything itself, and never imports ``ai_os_kernel`` at all — it only
stores and later calls whatever object it is handed. ``context: Any``
in :meth:`bind_pack_context`'s signature is not a compromise made for
this file; it is the real, final signature
``ai_os_sdk.contracts.entrypoint_context.PackContextReceiver`` declares,
copied verbatim.
"""

from __future__ import annotations

from typing import Any


class PackContextNotBoundError(RuntimeError):
    """Raised when ``execute()`` is called before ``bind_pack_context()``
    — the one ordering constraint :class:`~ai_os_sdk.contracts.PackContextReceiver`'s
    own docstring leaves to each entrypoint to enforce."""


class EchoCapabilityTestEntrypoint:
    """Zero-argument-constructible
    (:class:`~ai_os_kernel.workflow_engine.entrypoint_loader.EntrypointLoader`
    calls ``cls()`` exactly as it does for every real agent). Implements
    :class:`~ai_os_sdk.contracts.PackContextReceiver` by storing whatever
    context it is given, then dispatches ``execute()`` to whichever real
    capability ``inputs["capability"]`` names — ``"llm"``, ``"prompts"``,
    or ``"tools"`` — genuinely calling the injected ``PackContext``'s own
    real adapter, never a mock.
    """

    output_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"result": {}},
        "required": ["result"],
        "additionalProperties": False,
    }

    def __init__(self) -> None:
        self._context: Any | None = None

    def bind_pack_context(self, context: Any) -> None:
        self._context = context

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if self._context is None:
            raise PackContextNotBoundError(
                "execute() called before bind_pack_context() -- a real "
                "PackContext must be injected before first real use"
            )

        capability = inputs["capability"]
        if capability == "llm":
            response = await self._context.llm.complete(inputs["request"])
            return {"result": response.content}
        if capability == "prompts":
            rendered = await self._context.prompts.render(
                inputs["prompt_id"], inputs["variables"], version=inputs["version"]
            )
            return {"result": rendered.content}
        if capability == "tools":
            result = await self._context.tools.invoke(inputs["tool_id"], inputs["tool_inputs"])
            return {"result": result.stdout}
        raise ValueError(f"unknown capability {capability!r}")
