"""Concrete, non-Protocol helper implementations built on top of this
SDK's own Protocols — the boilerplate a pack would otherwise have to
write itself against :mod:`ai_os_sdk.contracts`.

**This subpackage's purpose is not settled by ``platform_sdk.md``.**
That document's §3 package-layout tree does not list ``sdk/`` at all —
only ``contracts/``, ``models/``, ``errors/``, ``testing/``,
``utilities/``, and ``prompts/`` have a stated purpose. The reasoning
and proposed content below come from
``docs/03_architecture/platform/platform_sdk_v1_scope.md`` §5, flagged
there as a proposal requiring explicit confirmation, not a decision
made unilaterally — approving that scope document was that
confirmation.

Proposed content, added by step 7:

- ``prompted_agent.py`` — a concrete ``Agent`` base built on
  ``LLMGateway`` + ``PromptRegistry``, mirroring the real, already-
  proven shape of ``ai_os_kernel.workflow_engine.prompted_agent.
  PromptedAgent`` (4 of the 5 real Software Engineering pack agents
  already depend on that Kernel-internal equivalent).

If a future step's own review concludes ``sdk/`` should hold something
else, that is a documentation change to ``platform_sdk_v1_scope.md``
first, then a code change here — not a silent divergence between the
two.
"""

from __future__ import annotations
