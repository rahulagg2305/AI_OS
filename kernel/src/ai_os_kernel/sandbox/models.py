"""The Sandbox's own reduced contract: what one execution produces
(:class:`SandboxResult`), and which ADR-0016 Tier 1 controls a given
:class:`~ai_os_kernel.sandbox.executor.SandboxExecutor` implementation
actually enforces at the OS level (:class:`SandboxGuarantees`).

**Why ``SandboxGuarantees`` exists at all.** ADR-0016 names five
Tier 1 controls this step's own approved framing distils to: no network
by default, no secrets, a wall-clock timeout, an output size cap, and no
host filesystem access beyond an explicit working directory. A backend
built on a plain OS subprocess (this step's only implementation,
:class:`~ai_os_kernel.sandbox.executor.LocalSubprocessSandbox`) can
genuinely enforce some of these (secrets, timeout, output cap) but
**cannot** enforce true network or filesystem containment without
namespace- or container-level isolation — ADR-0016's own "Alternatives
Considered" section rejects plain subprocess execution outright for
exactly this reason ("offers no meaningful containment for hostile
code"). Rather than silently claiming compliance it cannot deliver, or
silently downgrading what "Tier 1" means, each backend declares which
controls it actually enforces — the identical "declare a real, checkable
matrix rather than assert or hide a capability" shape already
established for the LLM Gateway's own ``ProviderCapabilities``
(:mod:`ai_os_kernel.llm_gateway.capability_negotiator`). A future
``DockerSandbox``/OCI backend would declare every field ``True``; a
caller (the still-unbuilt Tool Invoker) can and should refuse to run
genuinely untrusted code against a backend that does not.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SandboxGuarantees(BaseModel):
    """Which of ADR-0016's Tier 1 controls a specific
    :class:`~ai_os_kernel.sandbox.executor.SandboxExecutor`
    implementation actually enforces at the OS level — not what it
    merely attempts or documents an intent to."""

    model_config = ConfigDict(frozen=True)

    enforces_timeout: bool
    enforces_output_cap: bool
    enforces_secret_exclusion: bool
    enforces_network_isolation: bool
    enforces_filesystem_containment: bool


class SandboxResult(BaseModel):
    """The outcome of one :meth:`~ai_os_kernel.sandbox.executor.
    SandboxExecutor.execute` call.

    ``exit_code`` is ``None`` exactly when ``timed_out`` is ``True`` —
    a killed process never produces a real exit code worth reporting.
    ``truncated`` is ``True`` when either stdout or stderr hit
    ``max_output_bytes`` and was cut off; the cap applies independently
    to each stream, not to their combined total (a simpler, safer
    accounting model than tracking a shared running total across two
    concurrently-read streams).
    """

    model_config = ConfigDict(frozen=True)

    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool
    duration_seconds: float
