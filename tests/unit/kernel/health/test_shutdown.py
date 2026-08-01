"""``GracefulShutdownCoordinator`` — proves in-flight work is drained
cleanly on shutdown, not silently dropped or abruptly killed.
``P01-S04-M03-T06``.
"""

from __future__ import annotations

import asyncio
import time

import pytest
import structlog.testing

from ai_os_kernel.health.shutdown import GracefulShutdownCoordinator


def test_shutdown_with_no_registered_jobs_is_a_clean_no_op() -> None:
    async def _run() -> None:
        coordinator = GracefulShutdownCoordinator()
        await coordinator.shutdown()  # must not raise or hang

    asyncio.run(_run())


def test_a_cancelled_job_is_stopped_and_genuinely_awaited() -> None:
    async def _run() -> None:
        coordinator = GracefulShutdownCoordinator()
        started = asyncio.Event()

        async def loop() -> None:
            while True:
                started.set()
                await asyncio.sleep(3600)  # would hang forever if never cancelled

        task = asyncio.create_task(loop())
        coordinator.register_task("example", task)
        await started.wait()

        await coordinator.shutdown()

        assert task.done()
        assert task.cancelled()

    asyncio.run(_run())


def test_a_stop_event_job_finishes_its_in_flight_iteration_before_stopping() -> None:
    """The core "no work lost mid-step" property: setting the stop
    event must not interrupt work already in progress -- the loop
    finishes what it started, then exits on its own."""

    async def _run() -> None:
        coordinator = GracefulShutdownCoordinator()
        iteration_started = asyncio.Event()
        work_completed = False

        async def loop(stop_event: asyncio.Event) -> None:
            nonlocal work_completed
            while not stop_event.is_set():
                iteration_started.set()
                await asyncio.sleep(0.2)  # simulates in-flight work
                work_completed = True
                return

        stop_event = asyncio.Event()
        task = asyncio.create_task(loop(stop_event))
        coordinator.register_stop_event_task("example", task, stop_event)

        await iteration_started.wait()
        assert not work_completed  # the in-flight iteration is still running

        await coordinator.shutdown()

        assert work_completed  # the in-flight work genuinely finished, not dropped
        assert task.done()
        assert not task.cancelled()  # exited on its own, never interrupted

    asyncio.run(_run())


def test_multiple_jobs_are_drained_concurrently_not_sequentially() -> None:
    """Two 0.2s drains should take ~0.2s together, not ~0.4s -- proves
    shutdown() issues every stop signal first, then awaits all of
    them, rather than stopping one job fully before starting the
    next."""

    async def _run() -> float:
        coordinator = GracefulShutdownCoordinator()

        async def slow_loop(stop_event: asyncio.Event) -> None:
            await asyncio.sleep(0.2)

        stop_event_a = asyncio.Event()
        stop_event_b = asyncio.Event()
        coordinator.register_stop_event_task(
            "a", asyncio.create_task(slow_loop(stop_event_a)), stop_event_a
        )
        coordinator.register_stop_event_task(
            "b", asyncio.create_task(slow_loop(stop_event_b)), stop_event_b
        )

        start = time.monotonic()
        await coordinator.shutdown()
        return time.monotonic() - start

    elapsed = asyncio.run(_run())

    assert elapsed < 0.35  # well under the ~0.4s sequential-drain would take


def test_shutdown_logs_each_stopped_job_by_name() -> None:
    async def _run() -> None:
        coordinator = GracefulShutdownCoordinator()
        task = asyncio.create_task(asyncio.sleep(3600))
        coordinator.register_task("example_job", task)

        with structlog.testing.capture_logs() as logs:
            await coordinator.shutdown()

        stopped = [e for e in logs if e["event"] == "graceful_shutdown.job_stopped"]
        assert len(stopped) == 1
        assert stopped[0]["job"] == "example_job"

    asyncio.run(_run())


def test_registering_an_already_finished_task_does_not_hang() -> None:
    async def _run() -> None:
        coordinator = GracefulShutdownCoordinator()
        task = asyncio.create_task(asyncio.sleep(0))
        await task  # already done before registration

        coordinator.register_task("already_done", task)
        await coordinator.shutdown()  # must not raise or hang

        assert task.done()
        assert not task.cancelled()

    asyncio.run(_run())


def test_grace_period_seconds_must_be_positive() -> None:
    with pytest.raises(ValueError, match="grace_period_seconds must be positive"):
        GracefulShutdownCoordinator(grace_period_seconds=0)


def test_a_job_that_never_stops_on_its_own_is_force_cancelled_after_the_grace_period() -> None:
    """The real fix for CI run 30682840924's own 70+ minute hang: a
    coordinator with no bound at all lets one stuck job hang the whole
    shutdown forever. This proves shutdown() always returns -- a job
    that ignores its own stop_event entirely (simulating exactly a
    hung background loop, whatever the real cause) is force-cancelled
    once the grace period elapses, not waited on indefinitely."""

    async def _run() -> None:
        coordinator = GracefulShutdownCoordinator(grace_period_seconds=0.1)

        async def stuck_loop(stop_event: asyncio.Event) -> None:
            await asyncio.sleep(3600)  # ignores stop_event entirely -- a genuine hang

        stop_event = asyncio.Event()
        task = asyncio.create_task(stuck_loop(stop_event))
        coordinator.register_stop_event_task("stuck", task, stop_event)

        start = time.monotonic()
        with structlog.testing.capture_logs() as logs:
            await coordinator.shutdown()  # must return, not hang for 3600s
        elapsed = time.monotonic() - start

        assert elapsed < 1.0  # bounded by the grace period, not the stuck job's own sleep
        assert task.done()
        assert task.cancelled()  # force-cancelled, not left running
        forced = [e for e in logs if e["event"] == "graceful_shutdown.job_forced"]
        assert len(forced) == 1
        assert forced[0]["job"] == "stuck"
        assert forced[0]["log_level"] == "warning"

    asyncio.run(_run())


def test_a_healthy_job_within_the_grace_period_is_not_force_cancelled() -> None:
    """The grace period must not punish a job that stops normally,
    just quickly enough -- only a genuinely stuck one is forced."""

    async def _run() -> None:
        coordinator = GracefulShutdownCoordinator(grace_period_seconds=10.0)
        task = asyncio.create_task(asyncio.sleep(0.05))
        coordinator.register_task("quick", task)

        with structlog.testing.capture_logs() as logs:
            await coordinator.shutdown()

        forced = [e for e in logs if e["event"] == "graceful_shutdown.job_forced"]
        stopped = [e for e in logs if e["event"] == "graceful_shutdown.job_stopped"]
        assert forced == []
        assert len(stopped) == 1

    asyncio.run(_run())
