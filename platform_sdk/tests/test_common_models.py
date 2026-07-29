"""Step 2 of ``platform_sdk_v1_scope.md``: the four shared boundary
models (``platform_sdk.md`` §4.1, §4.2).

Tests the validation these models actually enforce, not their field
names — a test that only restates the field list would pass for any
misspelling that was misspelled consistently in both places.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from ai_os_sdk.models import (
    V1_TENANT_ID,
    ArtifactRef,
    SecurityContext,
    StepBudget,
    TraceContext,
    is_artifact_id,
)

_VALID_DIGEST = "sha256:" + "a" * 64


def _artifact(**overrides: object) -> ArtifactRef:
    fields: dict[str, object] = {
        "artifact_id": _VALID_DIGEST,
        "media_type": "text/markdown",
        "size_bytes": 12,
        "uri": "s3://bucket/key",
    }
    fields.update(overrides)
    return ArtifactRef(**fields)


class TestArtifactRef:
    def test_accepts_a_well_formed_sha256_reference(self) -> None:
        assert _artifact().artifact_id == _VALID_DIGEST

    @pytest.mark.parametrize(
        "bad_id",
        [
            "a" * 64,  # no scheme
            "sha256:" + "a" * 63,  # too short
            "sha256:" + "a" * 65,  # too long
            "sha256:" + "A" * 64,  # upper case — one artifact, one representation
            "sha256:" + "g" * 64,  # not hex
            "md5:" + "a" * 32,  # wrong algorithm
            "",
        ],
    )
    def test_rejects_anything_that_is_not_sha256_lower_hex(self, bad_id: str) -> None:
        with pytest.raises(ValidationError):
            _artifact(artifact_id=bad_id)

    def test_allows_a_zero_byte_artifact(self) -> None:
        """An empty artifact is addressable — SHA-256 has a digest for
        empty input — so `size_bytes=0` is valid, not a degenerate case."""
        assert _artifact(size_bytes=0).size_bytes == 0

    def test_rejects_a_negative_size(self) -> None:
        with pytest.raises(ValidationError):
            _artifact(size_bytes=-1)

    def test_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            _artifact().artifact_id = _VALID_DIGEST  # type: ignore[misc]

    def test_ignores_rather_than_rejects_an_unknown_field(self) -> None:
        """platform_sdk.md §8 makes a new optional field a *minor* bump;
        rejecting extras would make every such release breaking for older
        readers. See models/common.py's own docstring."""
        assert _artifact(some_future_field="x").artifact_id == _VALID_DIGEST

    def test_is_artifact_id_matches_the_models_own_validation(self) -> None:
        assert is_artifact_id(_VALID_DIGEST)
        assert not is_artifact_id("sha256:nope")


class TestTraceContext:
    def test_requires_trace_id_and_span_id(self) -> None:
        trace = TraceContext(trace_id="t", span_id="s")
        assert trace.trace_id == "t"
        assert trace.span_id == "s"
        assert trace.workflow_id is None
        assert trace.run_id is None

    @pytest.mark.parametrize("missing", ["trace_id", "span_id"])
    def test_rejects_a_context_that_cannot_be_correlated(self, missing: str) -> None:
        fields = {"trace_id": "t", "span_id": "s"}
        del fields[missing]
        with pytest.raises(ValidationError):
            TraceContext(**fields)

    def test_carries_all_five_optional_correlation_ids(self) -> None:
        """§4.1 names seven fields total. The Kernel's two existing
        partial TraceContexts carry subsets; this is the canonical one."""
        trace = TraceContext(
            trace_id="t",
            span_id="s",
            workflow_id="wf_1",
            step_id="stp_1",
            agent_id="software-engineering/qa-test",
            experiment_id="exp_1",
            run_id="run_1",
        )
        assert trace.workflow_id == "wf_1"
        assert trace.step_id == "stp_1"
        assert trace.agent_id == "software-engineering/qa-test"
        assert trace.experiment_id == "exp_1"
        assert trace.run_id == "run_1"


class TestSecurityContext:
    def test_defaults_to_no_roles_and_no_permissions(self) -> None:
        """Deny by default: an identity with nothing granted grants
        nothing (authentication_authorization.md §4.3)."""
        context = SecurityContext(principal_id="p", principal_type="user")
        assert context.roles == frozenset()
        assert context.permissions == frozenset()
        assert not context.has_permission("llm:invoke")

    def test_has_permission_reads_the_effective_set(self) -> None:
        context = SecurityContext(
            principal_id="p",
            principal_type="service_account",
            permissions=frozenset({"llm:invoke", "sandbox:execute"}),
        )
        assert context.has_permission("llm:invoke")
        assert context.has_permission("sandbox:execute")
        assert not context.has_permission("secret:manage")

    @pytest.mark.parametrize("principal_type", ["user", "service_account", "agent"])
    def test_accepts_the_three_documented_principal_types(self, principal_type: str) -> None:
        context = SecurityContext(principal_id="p", principal_type=principal_type)
        assert context.principal_type == principal_type

    def test_rejects_an_undocumented_principal_type(self) -> None:
        with pytest.raises(ValidationError):
            SecurityContext(principal_id="p", principal_type="robot")

    def test_tenant_id_is_pinned_to_the_v1_reserved_value(self) -> None:
        """§4.1: `tenant_id (reserved, always "default" in v1)`.
        Multi-tenancy is out of scope for v1 (security_architecture.md §4)."""
        assert SecurityContext(principal_id="p", principal_type="user").tenant_id == V1_TENANT_ID
        with pytest.raises(ValidationError):
            SecurityContext(principal_id="p", principal_type="user", tenant_id="other")

    def test_cannot_be_widened_by_mutation(self) -> None:
        """§4.1: "immutable; may only be narrowed, never widened"."""
        context = SecurityContext(principal_id="p", principal_type="user")
        with pytest.raises(ValidationError):
            context.permissions = frozenset({"secret:manage"})  # type: ignore[misc]


class TestStepBudget:
    def test_every_ceiling_is_optional(self) -> None:
        """An absent ceiling means "not bounded on this axis", which is
        not the same as a ceiling of zero."""
        budget = StepBudget()
        assert budget.max_tokens is None
        assert budget.max_cost_usd is None
        assert budget.max_tool_calls is None
        assert budget.max_wall_seconds is None

    def test_accepts_positive_ceilings(self) -> None:
        budget = StepBudget(
            max_tokens=1000,
            max_cost_usd=Decimal("0.500000"),
            max_tool_calls=4,
            max_wall_seconds=30.0,
        )
        assert budget.max_tokens == 1000
        assert budget.max_cost_usd == Decimal("0.500000")
        assert budget.max_tool_calls == 4
        assert budget.max_wall_seconds == 30.0

    @pytest.mark.parametrize(
        "field",
        ["max_tokens", "max_cost_usd", "max_tool_calls", "max_wall_seconds"],
    )
    @pytest.mark.parametrize("bad_value", [0, -1])
    def test_rejects_a_zero_or_negative_ceiling(self, field: str, bad_value: int) -> None:
        with pytest.raises(ValidationError):
            StepBudget(**{field: bad_value})

    def test_cost_is_decimal_not_float(self) -> None:
        """data_model.md §2 requires NUMERIC(14,6) for USD and states
        "Never floating point" — a cost ceiling compared against
        accumulated float error is a ceiling that can be overrun."""
        budget = StepBudget(max_cost_usd=Decimal("0.1"))
        assert isinstance(budget.max_cost_usd, Decimal)
        assert budget.max_cost_usd == Decimal("0.1")
