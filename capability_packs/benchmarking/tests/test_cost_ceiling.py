"""Deterministic unit tests for `enforce_cost_ceiling` — pure, no I/O."""

from __future__ import annotations

from decimal import Decimal

import pytest

from ai_os_pack_benchmarking.cost_ceiling import CostCeilingExceededError, enforce_cost_ceiling


def test_a_projection_within_the_ceiling_is_accepted() -> None:
    enforce_cost_ceiling(projected_cost_usd=Decimal("5.00"), ceiling_usd=Decimal("10.00"))


def test_a_projection_exactly_at_the_ceiling_is_accepted() -> None:
    enforce_cost_ceiling(projected_cost_usd=Decimal("10.00"), ceiling_usd=Decimal("10.00"))


def test_a_projection_over_the_ceiling_is_refused() -> None:
    with pytest.raises(CostCeilingExceededError, match="exceeds this experiment's own declared"):
        enforce_cost_ceiling(projected_cost_usd=Decimal("10.01"), ceiling_usd=Decimal("10.00"))


def test_no_declared_ceiling_is_always_accepted() -> None:
    enforce_cost_ceiling(projected_cost_usd=Decimal("999999.00"), ceiling_usd=None)
