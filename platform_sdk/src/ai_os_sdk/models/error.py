"""``ErrorCategory`` and ``StructuredError`` — the platform error
taxonomy's data shapes (``platform_sdk.md`` §4.4).

**Live here, not in ``ai_os_sdk.errors``, despite §4.4 grouping them
with the ``AiOsError`` exception hierarchy.** Moved in step 6:
:class:`~ai_os_sdk.models.tool.ToolResult` needs :class:`StructuredError`
for its own ``error`` field, and having a model import from the
``errors`` package (which itself imports
:class:`~ai_os_sdk.models.common.TraceContext`) creates a real import
cycle — importing ``ai_os_sdk.errors`` first triggers ``ai_os_sdk.models``
package init, which reaches ``models.tool``, which needs
``ai_os_sdk.errors`` again, mid-initialization. The same problem
:class:`~ai_os_sdk.models.tool.TrustTier` was moved out of
``ai_os_sdk.contracts.tool`` to avoid, one step earlier, for the
identical reason: a lower layer cannot import a higher one.

Both names remain public via ``ai_os_sdk.errors.ErrorCategory`` /
``ai_os_sdk.errors.StructuredError`` — ``ai_os_sdk.errors.taxonomy`` now
imports them from here and re-exports them unchanged, so nothing built
in steps 2–5 breaks. Only the ``AiOsError`` exception hierarchy itself
(the classes that are *raised*, not merely carried as data) stays
defined in ``ai_os_sdk.errors.taxonomy``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai_os_sdk.models.common import TraceContext


class ErrorCategory(StrEnum):
    """The six platform error categories (``error_handling_retry.md``
    §3). Values are the lower-case wire forms §4.4 specifies.
    """

    TRANSIENT = "transient"
    """May succeed on retry: network timeout, rate limit, provider
    overload, lock contention, chain exhausted."""

    PERMANENT = "permanent"
    """Will not succeed with the same input: invalid input, schema
    validation failure, context window exceeded, unsupported capability,
    model refusal."""

    QUALITY = "quality"
    """Raised by a Quality Gate or review. Not retriable — it requires
    corrective work, not another attempt."""

    INFRASTRUCTURE = "infrastructure"
    """Platform-side failure: database unavailable, configuration
    missing, secret backend unreachable, provider auth failure. The only
    category whose retriability is genuinely case-by-case."""

    BUDGET = "budget"
    """A declared ceiling was reached. Not retried automatically — an
    operator raising the ceiling is the resolution, per §3."""

    SECURITY = "security"
    """An authorization or policy denial. Never retried automatically,
    and always audited (§3)."""


class StructuredError(BaseModel):
    """The serialised form of any platform error (``platform_sdk.md``
    §4.4). Returned by Agents, Tools, and Kernel components; recorded on
    ``workflow_instances.error`` and ``workflow_steps.error``
    (``data_model.md`` §4.1, §4.3).

    Frozen, and ``extra`` deliberately not forbidden, for the same
    reasons as every model in :mod:`ai_os_sdk.models.common` — see that
    module's docstring.

    **``trace`` is required.** §4.4 marks ``retry_after_seconds`` and
    ``details`` as nullable and pointedly does *not* mark ``trace``, so
    required is the faithful reading: an error that cannot be correlated
    to a trace is not diagnosable, and §4.4's own field list ends with
    "correlation identifiers" as a stated requirement. A raise site that
    does not know its trace context therefore cannot produce a
    ``StructuredError`` directly — it raises an
    :class:`~ai_os_sdk.errors.AiOsError` and the boundary that *does*
    know the trace performs the conversion. See
    :meth:`~ai_os_sdk.errors.AiOsError.to_structured_error`.
    """

    model_config = ConfigDict(frozen=True)

    error_code: str
    """Stable, catalogued identifier — the value dashboards and alerts
    key on (§3). The catalogue itself does not exist yet; §3 places it in
    ``platform_sdk/errors/``, and populating it needs real producers,
    which arrive with the Protocols in later steps."""

    category: ErrorCategory
    message: str
    """Human-readable. **Never contains a secret** (§4.4)."""

    retriable: bool
    retry_after_seconds: float | None = Field(default=None, ge=0)
    details: dict[str, Any] | None = None
    trace: TraceContext
