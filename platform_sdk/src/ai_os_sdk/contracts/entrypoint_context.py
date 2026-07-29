"""The injection mechanism a zero-argument-constructible entrypoint uses
to receive its real ``PackContext`` (``platform_sdk_v1_scope.md`` step
6b).

**Deliberately not ``capability_pack.py``.** That module — ``§7``'s full
``CapabilityPack``/``PackContext``/``PackRegistration``/``HealthReport``
entry-point contract — is step 7's own explicitly scoped job
(``ai_os_sdk.contracts``'s own package docstring already names it: "step
7"). This module answers a narrower, distinct question that step 6b is
scoped to answer instead: given that
:class:`~ai_os_kernel.workflow_engine.entrypoint_loader.EntrypointLoader`
can only ever construct an entrypoint with zero arguments (``cls()``,
unchanged by this step, and not modified here), how does a real,
already-constructed context ever reach that instance at all?

**The generalized shape of a pattern this codebase already used five
times.** Every real Software Engineering pack agent that needs a real,
non-trivial dependency (``ArchitectureAgentEntrypoint``,
``BuildAgentEntrypoint``, ``DocumentationAgentEntrypoint``,
``RequirementsAnalystAgentEntrypoint``, ``TestAgentEntrypoint``) is
zero-argument-constructible and lazily builds what it actually needs on
first real use, because ``__init__`` cannot be ``async`` and
``EntrypointLoader`` cannot pass it anything. Each one currently does
this by reaching into Kernel internals directly and building its own
composition from scratch — five separate, hand-rolled copies of the same
shape. This Protocol is that shape's one real, reusable SDK mechanism:
an entrypoint declares it can receive a context, whatever constructs and
owns that entrypoint instance calls :meth:`PackContextReceiver.
bind_pack_context` exactly once with the real, already-built context
(built for that entrypoint's own declared permissions — see
``ai_os_kernel.sdk_adapters.pack_context`` for the real, permission-gated
builder step 6b adds), before the first call to ``execute``/``invoke``/
``activate``. The entrypoint itself decides what "before first real use"
means for its own lazy-build lock, exactly as
``ArchitectureAgentEntrypoint._ensure_agent`` already does today — this
Protocol only standardizes *how the context arrives*, not the entrypoint's
own internal caching.

**Why ``context: Any``, not ``context: PackContext``.** The real,
richly-typed ``PackContext`` (``platform_sdk.md`` §6, carrying ``llm``/
``prompts``/``tools``/... as real SDK Protocol instances) does not exist
as an SDK type yet — landing it in ``ai_os_sdk`` is step 7's own job.
Step 6b's own real, additive ``PackContext`` lives on the Kernel side for
now (``ai_os_kernel.capability_manager.pack_contract.PackContext``,
extended additively, not redesigned, exactly as that module's own
docstring already anticipated), which the SDK — the dependency floor,
depending on nothing else (``platform_sdk.md`` §2 rule 1) — cannot import
without inverting the dependency direction. Typing this Protocol's one
parameter as ``Any`` keeps the mechanism genuinely usable today without
that import, and needs no change when step 7 gives ``PackContext`` a
real home in ``ai_os_sdk`` — only the type used *at the call site*
narrows then, not this Protocol's own signature.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PackContextReceiver(Protocol):
    """A zero-argument-constructible entrypoint that can receive its
    real context after construction, once, before its first genuine
    use.

    ``@runtime_checkable`` so a caller that just resolved an entrypoint
    via ``EntrypointLoader`` can check for this capability with a plain
    ``isinstance`` before calling it — an entrypoint that does not
    implement this (the trivial ``EchoAgent``/``EchoTool`` stand-ins, for
    example) simply never receives one, and must not need one.
    """

    def bind_pack_context(self, context: Any) -> None:
        """Called exactly once, with the real context this entrypoint's
        own declared permissions were granted, before the first call to
        whatever this entrypoint's own real Protocol requires
        (``execute``/``invoke``/``activate``). Calling this more than
        once, or calling the entrypoint's real method before this has
        been called at all, are both implementation-defined per
        entrypoint — exactly as the timing of ``ArchitectureAgentEntrypoint``'s
        own ``_ensure_agent`` lazy build already is today."""
        ...
