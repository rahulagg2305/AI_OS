"""Worker process-role entrypoint (ADR-0020, ``P01-S01-M40-T05``).

Started as::

    python -m ai_os_kernel.entrypoints.worker

See docs/11_deployment/deployment_architecture.md §2.

Genuinely runs the real, continuously-running multi-instance worker
loop (:func:`ai_os_kernel.bootstrap.build_workflow_worker_loop`) as its
own standalone process — the identical construction the ``api`` role's
own background task already uses, never a second, parallel copy. Before
this step this module was a placeholder that logged one line and
exited; the real loop existed (``P02-S01-M05-T14``) but only ever ran
inside the ``api`` role's own FastAPI lifespan.

Stops gracefully on ``SIGTERM``/``SIGINT`` — mirrors
deployment_architecture.md §7's own documented shape ("a worker stops
accepting new leases, finishes in-flight steps, releases leases, and
exits") via the same, already-real
:class:`~ai_os_kernel.health.shutdown.GracefulShutdownCoordinator` the
``api`` role's own ``_lifespan`` uses — not a second shutdown mechanism.
Signal handling is Unix-only (:meth:`asyncio.AbstractEventLoop.
add_signal_handler` has no Windows implementation); on a platform
without it, the loop still runs, just without a clean stop signal —
every real deployment target (Docker/Kubernetes) is Linux.

**Signal handlers are registered before anything else in ``_run()``,
never after — genuinely load-bearing, not a style preference.** Found
by reproducing a real hang against the built image (``docker stop``
forced to ``SIGKILL`` every time, never a clean exit): something in
``ai_os_kernel.bootstrap``'s own import graph — isolated to the
OpenTelemetry SDK, which installs its own signal handling as a side
effect once actually configured/imported through that path — clobbers
:meth:`asyncio.AbstractEventLoop.add_signal_handler` for the rest of
the process if a handler is registered *after* it. Registering first
(proven, both in isolation and against this module's own real
construction chain) sidesteps it entirely; nothing here disables or
patches OpenTelemetry itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

from ai_os_kernel.bootstrap import build_workflow_worker_loop, load_configuration
from ai_os_kernel.health.shutdown import GracefulShutdownCoordinator
from ai_os_kernel.observability import configure_logging, get_logger
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.settings import DatabaseSettings
from ai_os_kernel.workflow_engine.worker_loop import WORKER_POLL_INTERVAL_SECONDS, run_worker_loop

logger = get_logger("ai_os_kernel.entrypoints.worker")


def _register_stop_signals(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)


async def _run() -> None:
    # Must run before any ai_os_kernel.bootstrap call — see this
    # module's own docstring for the real, reproduced reason.
    stop = asyncio.Event()
    _register_stop_signals(stop)

    config = load_configuration()
    configure_logging(config.log_level)
    logger.info("ai_os_kernel.entrypoints.worker.starting", env=config.env, role=config.role)

    engine = build_engine(DatabaseSettings().database_url)
    shutdown_coordinator = GracefulShutdownCoordinator()

    try:
        worker = await build_workflow_worker_loop(engine)
        interval_seconds = config.worker_poll_interval_seconds or WORKER_POLL_INTERVAL_SECONDS
        task = asyncio.create_task(
            run_worker_loop(worker=worker, interval_seconds=interval_seconds)
        )
        shutdown_coordinator.register_task("workflow_worker_loop", task)
        logger.info("ai_os_kernel.entrypoints.worker.started", interval_seconds=interval_seconds)

        await stop.wait()
        logger.info("ai_os_kernel.entrypoints.worker.stopping")
    finally:
        await shutdown_coordinator.shutdown()
        await engine.dispose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
