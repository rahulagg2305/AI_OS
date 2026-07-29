"""The boundary models shared by every other contract in this SDK
(``platform_sdk.md`` §4.1, plus ``StepBudget`` from §4.2).

**Field names are normative** — ``platform_sdk.md`` §4 states this
explicitly, so every name below is the specified name, not a local
preference.

**This module is the dependency floor of the floor.** It imports
nothing from ``ai_os_sdk`` and must never do so: ``ai_os_sdk.errors``
depends on *this* module (``StructuredError`` carries a
:class:`TraceContext`), so an import in the other direction would be
circular. Anything needed by both belongs here.

**Every model is frozen.** ``platform_sdk.md`` §2 rule 3 requires
Pydantic v2 validation "at both ends"; freezing additionally makes a
boundary value safe to pass across the pack/platform seam without a
defensive copy, and is what makes :class:`SecurityContext`'s documented
"immutable; may only be narrowed, never widened" rule structural rather
than advisory.

**``extra`` is deliberately *not* forbidden.** ``platform_sdk.md`` §8
defines adding a new optional field as a **minor** version bump. If
these models rejected unknown fields, a minor SDK release would break
every older reader — turning a documented-as-compatible change into a
breaking one. Unknown fields are therefore ignored, not rejected.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

# `sha256:<hex>` per platform_sdk.md §4.1 and data_model.md §2's
# "Content addressing" convention. A SHA-256 digest is exactly 64
# hexadecimal characters; lower-case only, so one artifact has exactly
# one representation and `artifact_id` equality is byte comparison.
ARTIFACT_ID_PATTERN = r"^sha256:[0-9a-f]{64}$"

_ARTIFACT_ID_RE = re.compile(ARTIFACT_ID_PATTERN)

# platform_sdk.md §4.1: `tenant_id (reserved, always "default" in v1)`.
# Multi-tenant isolation is explicitly out of scope for v1
# (security_architecture.md §4, "Out of scope for v1"), so this is
# pinned to a single permitted value rather than left open — widening it
# is a v2 concern and, per platform_sdk.md §8, its own major decision.
V1_TENANT_ID: Final[Literal["default"]] = "default"


class ArtifactRef(BaseModel):
    """A content-addressed reference to a stored artifact
    (``platform_sdk.md`` §4.1). Artifacts are referenced from workflow
    state, never embedded in it (``data_model.md`` §2).
    """

    model_config = ConfigDict(frozen=True)

    artifact_id: str = Field(pattern=ARTIFACT_ID_PATTERN)
    """``sha256:<64 lower-case hex chars>``. Validated on construction."""

    media_type: str
    """IANA media type of the stored content, e.g. ``text/markdown``."""

    size_bytes: int = Field(ge=0)
    """Size of the stored content. Zero is valid — an empty artifact is a
    real, addressable thing (SHA-256 has a well-defined digest for empty
    input)."""

    uri: str
    """Where the content actually lives, as resolved by the storage
    service. Not itself content-addressed: two URIs may serve the same
    ``artifact_id``."""


class TraceContext(BaseModel):
    """Correlation identifiers carried alongside every request, result,
    and error that crosses the boundary (``platform_sdk.md`` §4.1).

    **This is the canonical shape.** Two narrower ``TraceContext``
    classes already exist inside the Kernel —
    ``ai_os_kernel.observability.trace.TraceContext`` (no ``span_id``,
    no ``run_id``) and ``ai_os_kernel.llm_gateway.models.TraceContext``
    (``workflow_id``/``step_id`` only) — and **both of their docstrings
    already name this §4.1 shape as the canonical one they are reduced
    slices of**. Consolidating them onto this class is Kernel-side work
    scheduled by ``platform_sdk_v1_scope.md`` steps 2a/6a; it is not
    done here, and nothing in the Kernel changes as a result of this
    module existing.

    ``trace_id`` and ``span_id`` are required because a value that
    cannot be correlated to a span is not a trace context; everything
    else is optional because a given call may genuinely not be inside a
    workflow, a step, an agent, or an experiment.
    """

    model_config = ConfigDict(frozen=True)

    trace_id: str
    span_id: str
    workflow_id: str | None = None
    step_id: str | None = None
    agent_id: str | None = None
    experiment_id: str | None = None
    run_id: str | None = None


class SecurityContext(BaseModel):
    """The identity and *already-narrowed effective* permissions for one
    operation (``platform_sdk.md`` §4.1).

    **``permissions`` is the result of narrowing, not an input to it.**
    §4.4's monotonic-narrowing rule
    (``principal ∩ workflow ∩ agent ∩ tool``) is computed by whoever
    constructs this object; a holder reads an effective set and never
    recomputes or widens it. Frozen, so "may only be narrowed, never
    widened" cannot be violated by mutation.

    **No ``narrow()`` helper is provided here, deliberately.** The
    narrowing chain is not implemented anywhere in this codebase yet —
    ``ai_os_kernel.security_manager.models``' own docstring states it
    computes only the first (principal) term, because manifest-declared
    workflow/agent/tool permissions are not read at authorization time.
    Adding an operation whose semantics nothing yet exercises would be
    inventing the very architecture that step is meant to decide. This
    module defines the value; the chain that produces it belongs to the
    step that builds it.

    ``frozenset`` rather than ``list`` for both collections: membership
    is the only operation either is used for, order carries no meaning,
    and duplicates are not a representable state.
    """

    model_config = ConfigDict(frozen=True)

    principal_id: str
    principal_type: Literal["user", "service_account", "agent"]
    roles: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()
    tenant_id: Literal["default"] = V1_TENANT_ID
    """Reserved. Always ``"default"`` in v1 — see :data:`V1_TENANT_ID`."""

    def has_permission(self, permission: str) -> bool:
        """Whether this context grants ``permission``.

        Deny-by-default is the caller's rule to apply
        (``authentication_authorization.md`` §4.3); this only answers
        membership in the effective set.
        """
        return permission in self.permissions


class StepBudget(BaseModel):
    """Ceilings the platform enforces for one step
    (``platform_sdk.md`` §4.2).

    Every field is optional: an absent ceiling means "not bounded on
    this axis by this budget", which is different from a ceiling of
    zero. Each present ceiling must be positive — a budget of zero would
    forbid the work it was attached to, which is expressed by not
    scheduling the step, not by budgeting it at nothing.

    ``max_cost_usd`` is a :class:`~decimal.Decimal`, never a float:
    ``data_model.md`` §2 requires ``NUMERIC(14,6)`` for USD and states
    "Never floating point." A cost ceiling compared with accumulated
    float error is a ceiling that can be silently overrun.
    ``max_wall_seconds`` is a float because elapsed time carries no such
    exactness requirement.
    """

    model_config = ConfigDict(frozen=True)

    max_tokens: int | None = Field(default=None, gt=0)
    max_cost_usd: Decimal | None = Field(default=None, gt=0)
    max_tool_calls: int | None = Field(default=None, gt=0)
    max_wall_seconds: float | None = Field(default=None, gt=0)


def is_artifact_id(value: str) -> bool:
    """Whether ``value`` is a well-formed ``sha256:<hex>`` artifact id.

    Exposed so a caller can validate a candidate id *without*
    constructing an :class:`ArtifactRef` (which also requires
    ``media_type``, ``size_bytes``, and ``uri``) and without duplicating
    :data:`ARTIFACT_ID_PATTERN`.
    """
    return _ARTIFACT_ID_RE.match(value) is not None
