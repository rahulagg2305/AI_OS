"""Tool-invocation boundary models (``platform_sdk.md`` §4.3, §5.6).

**``TrustTier`` lives here, not in ``ai_os_sdk.contracts.tool`` where
step 3 first defined it.** Moved in step 6: ``ToolDescriptor`` (§5.6)
needs it too, and a model depending on a contract would invert this
package's own layering — contracts depend on models, never the
reverse (every other contract in this package, ``llm_gateway.py``,
``prompt_registry.py``, already imports from ``ai_os_sdk.models``, not
the other way around). ``ai_os_sdk.contracts.tool`` re-exports it
unchanged, so nothing built in steps 3–5 breaks.

**``ToolResult`` is the return type of ``ToolInvoker.invoke`` (§5.6)**,
per §4.3's dated *v1.0.0 Reconciliation Decision* block
(``platform_sdk_v1_scope.md`` step 2a) — a mixed narrow-and-extend
reconciliation against the real, working ``SandboxResult``
(``ai_os_kernel.sandbox.models``: ``exit_code``, ``stdout``, ``stderr``,
``timed_out``, ``truncated``, ``duration_seconds``). Narrowed:
``stdout_ref``/``stderr_ref`` (needs ``StorageService``, 0% built) become
inline ``stdout``/``stderr`` strings, and ``artifacts`` is dropped for
the same reason. **Extended:** ``timed_out``/``truncated`` — the
documented shape has no way to express either distinctly from a
non-zero exit code, and a caller parsing truncated output as complete
would draw a wrong conclusion silently.

``ToolResult.error`` is a :class:`~ai_os_sdk.models.error.StructuredError`,
imported from :mod:`ai_os_sdk.models.error` rather than from
``ai_os_sdk.errors`` — the latter would create a real import cycle (this
module needs ``StructuredError``, and ``ai_os_sdk.errors`` needs
:class:`~ai_os_sdk.models.common.TraceContext`). See
:mod:`ai_os_sdk.models.error`'s own docstring for the full reasoning;
``ai_os_sdk.errors.StructuredError`` remains the same object.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_os_sdk.models.error import StructuredError


class TrustTier(StrEnum):
    """The two-value closed vocabulary from
    ``platform_sdk/schemas/manifest.schema.json``'s own
    ``tools[].trustTier`` enum — the authoritative artifact, which is
    also what ``ai_os_kernel.workflow_engine.tool.TrustTier`` mirrors.

    **Defined here rather than imported.** ``platform_sdk.md`` §2 rule 1
    makes this SDK the dependency floor: it depends on no other AI_OS
    distribution, so it cannot import the Kernel's equivalent enum. Both
    enums independently mirror the same JSON Schema, which is what keeps
    them in agreement; the schema is the single source of truth, not
    either class.

    A consequence worth stating plainly: because these are two distinct
    Python types, a Kernel-typed tool is **not statically assignable**
    to this SDK ``Tool`` Protocol, even though it satisfies it at
    runtime. Bridging that is the Kernel-side adapter's job (step 6a),
    and it is expected rather than a defect.
    """

    TIER1_SANDBOXED = "tier1_sandboxed"
    """Untrusted execution. **Mandatory** for any tool that executes a
    command, compiles, runs tests, installs dependencies, or processes
    untrusted repository content (ADR-0016, tool execution sandboxing)."""

    TIER2_TRUSTED = "tier2_trusted"
    """In-process platform operations only, under canonical-path
    allowlisting. Never for executing generated or untrusted code."""


class ToolDescriptor(BaseModel):
    """One entry in ``ToolInvoker.available_tools()`` (§5.6).

    In v1.0.0, exactly one real descriptor exists —
    :data:`~ai_os_sdk.contracts.tool_invoker.PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR`
    — so ``available_tools()`` has a genuine, non-empty answer instead of
    the empty tuple a pack-declared-tool registry would return today
    (the one real pack declares zero tools).
    """

    model_config = ConfigDict(frozen=True)

    tool_id: str
    trust_tier: TrustTier
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class ToolStatus(StrEnum):
    """The two-value outcome of one tool invocation (§4.3's documented
    ``status: success|failure``)."""

    SUCCESS = "success"
    FAILURE = "failure"


class ToolResult(BaseModel):
    """The outcome of one ``ToolInvoker.invoke()`` call — see this
    module's docstring for exactly which fields of §4.3's documented
    shape this narrows, extends, or keeps, and why.

    Two invariants are enforced on construction:

    - ``outputs`` and ``error`` are mutually exclusive, gated by
      ``status`` — a result cannot claim success with no output, nor
      failure with no error to report.
    - ``exit_code`` **must** be ``None`` when ``timed_out`` is ``True``
      — mirroring ``SandboxResult``'s own documented rule "a killed
      process never produces a real exit code worth reporting"
      (``sandbox/models.py:52-53``). **The reverse is deliberately not
      enforced.** An earlier draft of this model required ``exit_code``
      whenever ``timed_out`` was ``False`` — running the real
      ``LocalSubprocessSandbox`` against a command that overflows
      ``max_output_bytes`` disproved that: a cap breach kills the
      process before it exits on its own
      (``sandbox/executor.py``'s own ``cap_exceeded`` branch,
      ``_finished_result(wait_task, None)``), so ``exit_code`` can be
      ``None`` with ``timed_out=False`` and ``truncated=True`` too. Real
      execution, not the documented shape or an assumption, is what
      caught this.

    ``truncated`` is deliberately **not** constrained against ``status``
    or ``exit_code`` — the real sandbox can truncate the output of an
    otherwise-successful run (each stream is capped independently of
    whether the command itself succeeded), so a truncated *and*
    successful result is a real, valid state, not a contradiction.
    """

    model_config = ConfigDict(frozen=True)

    status: ToolStatus
    outputs: dict[str, Any] | None = None
    error: StructuredError | None = None
    exit_code: int | None = None
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool
    duration_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _outputs_xor_error_matches_status(self) -> ToolResult:
        if self.status is ToolStatus.SUCCESS:
            if self.outputs is None:
                raise ValueError("outputs must be set when status is success")
            if self.error is not None:
                raise ValueError("error must be omitted when status is success")
        else:
            if self.error is None:
                raise ValueError("error must be set when status is failure")
            if self.outputs is not None:
                raise ValueError("outputs must be omitted when status is failure")
        return self

    @model_validator(mode="after")
    def _exit_code_is_none_when_timed_out(self) -> ToolResult:
        """One-directional only — see this class's own docstring for
        why a cap-breach-triggered kill (``truncated=True``,
        ``timed_out=False``) can *also* leave ``exit_code`` ``None``,
        which rules out the reverse implication."""
        if self.timed_out and self.exit_code is not None:
            raise ValueError("exit_code must be None when timed_out is true")
        return self
