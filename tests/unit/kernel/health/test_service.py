"""Unit tests for the Health Service's status aggregation."""

import asyncio

from ai_os_kernel.health import ComponentStatus, HealthService


def test_overall_status_is_ready_when_every_component_is_ok() -> None:
    service = HealthService(
        [
            lambda: ComponentStatus(name="a", status="ok"),
            lambda: ComponentStatus(name="b", status="ok"),
        ]
    )

    report = asyncio.run(service.readiness())

    assert report.status == "ready"
    assert [c.name for c in report.components] == ["a", "b"]


def test_overall_status_is_degraded_when_any_component_is_not_ok() -> None:
    service = HealthService(
        [
            lambda: ComponentStatus(name="a", status="ok"),
            lambda: ComponentStatus(name="b", status="error", detail="boom"),
        ]
    )

    report = asyncio.run(service.readiness())

    assert report.status == "degraded"


def test_no_checks_reports_ready() -> None:
    service = HealthService([])

    report = asyncio.run(service.readiness())

    assert report.status == "ready"
    assert report.components == []


def test_an_async_check_is_genuinely_awaited() -> None:
    """Proves HealthService supports a check that returns an Awaitable,
    not just a plain ComponentStatus — the real capability this step
    added so a check can read real state through an async accessor
    (e.g. a database query), mixed freely with synchronous checks."""

    async def async_check() -> ComponentStatus:
        return ComponentStatus(name="async", status="ok", detail="awaited for real")

    service = HealthService(
        [
            lambda: ComponentStatus(name="sync", status="ok"),
            async_check,
        ]
    )

    report = asyncio.run(service.readiness())

    assert report.status == "ready"
    assert [c.name for c in report.components] == ["sync", "async"]
    async_component = next(c for c in report.components if c.name == "async")
    assert async_component.detail == "awaited for real"


def test_an_async_check_that_reports_degraded_makes_the_overall_status_degraded() -> None:
    async def async_check() -> ComponentStatus:
        return ComponentStatus(name="async", status="degraded", detail="stuck")

    service = HealthService([lambda: ComponentStatus(name="sync", status="ok"), async_check])

    report = asyncio.run(service.readiness())

    assert report.status == "degraded"
