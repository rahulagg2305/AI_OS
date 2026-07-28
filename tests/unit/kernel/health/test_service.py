"""Unit tests for the Health Service's status aggregation."""

from ai_os_kernel.health import ComponentStatus, HealthService


def test_overall_status_is_ready_when_every_component_is_ok() -> None:
    service = HealthService(
        [
            lambda: ComponentStatus(name="a", status="ok"),
            lambda: ComponentStatus(name="b", status="ok"),
        ]
    )

    report = service.readiness()

    assert report.status == "ready"
    assert [c.name for c in report.components] == ["a", "b"]


def test_overall_status_is_degraded_when_any_component_is_not_ok() -> None:
    service = HealthService(
        [
            lambda: ComponentStatus(name="a", status="ok"),
            lambda: ComponentStatus(name="b", status="error", detail="boom"),
        ]
    )

    report = service.readiness()

    assert report.status == "degraded"


def test_no_checks_reports_ready() -> None:
    service = HealthService([])

    report = service.readiness()

    assert report.status == "ready"
    assert report.components == []
