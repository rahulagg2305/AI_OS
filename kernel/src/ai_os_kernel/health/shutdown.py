"""Graceful-shutdown coordinator (``P01-S04-M03-T06``).

**Goal: drain in-flight work before the process exits, not abruptly
kill it.** Before this step, ``ai_os_kernel.bootstrap._lifespan``
stopped its two background loops (the Pack Health Collector's poll
loop, the Lease Reaper's reap loop) with the same four lines of
cancel-and-await code duplicated twice in its own ``finally`` block —
and the scheduled audit-chain verification job
(:mod:`ai_os_kernel.observability.audit_verification_job`,
``P01-S05-M04-T06``) had no shutdown path at all, because nothing
started it: it existed, fully built and unit-tested, but was never
wired into a real Kernel process. This module replaces the duplicated
pattern with one small, reusable, independently-tested coordinator and
is what lets that third job finally run for real.

**Two distinct stop shapes, not one, because "drain" means something
different for each.**

- A **cancelled** job (:meth:`GracefulShutdownCoordinator.register_task`)
  — the Pack Health Collector and Lease Reaper's own loops. Calling
  :meth:`asyncio.Task.cancel` raises :class:`asyncio.CancelledError`
  at the task's *next* await point, which is between iterations for
  both of these loops (each iteration is a single bounded poll/reap
  pass with no long-lived await inside it), so in practice nothing
  mid-step is interrupted — but the mechanism itself is still a hard
  interrupt request, not a request the loop can decline or delay.
- A **stop-event** job (:meth:`GracefulShutdownCoordinator.register_stop_event_task`)
  — the audit-chain verification job. Setting its ``stop_event``
  never interrupts anything; the loop notices the event only after its
  current pass finishes and then exits on its own
  (:func:`~ai_os_kernel.observability.audit_verification_job.run_periodic_audit_chain_verification`'s
  own docstring). This is the literal reading of this ticket's Output,
  "No work lost mid-step," for a job whose own author already chose
  the gentler shape — the coordinator does not downgrade it to a hard
  cancel just to have one uniform mechanism.

**Every registered job is stopped, then every registered job is
awaited — two separate passes, not stop-then-await one at a time.**
Issuing every stop signal first lets all jobs wind down concurrently;
awaiting them one at a time in a single interleaved loop would make
total shutdown time the *sum* of each job's own drain time instead of
the *maximum*, for no benefit.

**Does not drain in-flight HTTP requests.** That is the ASGI server's
own job (Uvicorn's graceful-shutdown handling: stop accepting new
connections, wait for in-flight ones, *then* run the app's shutdown
lifespan) and already completes before ``_lifespan``'s own shutdown
phase — the code this module's own docstring can affect — ever runs.
Reimplementing that here would duplicate, not improve on, infrastructure
this process does not own.

**``shutdown()`` is itself bounded — never an unconditional wait.** A
coordinator whose entire purpose is a clean shutdown would defeat that
purpose if one misbehaving job (a hung query, a genuine bug in a loop
this module does not control) could make it wait forever: the whole
process shutdown, and every caller blocked on it (a real deployment's
own termination, or a test's ``with TestClient(app):`` exit), would
hang indefinitely with it. Added defensively while investigating CI run
``30682840924``'s real 70+ minute hang — genuinely valuable regardless,
but **not itself what caused that hang**: the real cause, found via a
live-logging diagnostic run and fixed in
``tests/integration/test_bootstrap_pack_lifecycle.py``, was a
cross-event-loop hazard in that test's own code (an ``asyncio.run()``
call reusing an async repository built on a *different* event loop),
unrelated to this coordinator or its three managed loops — see that
test file's own docstring for the full root cause. ``grace_period_seconds``
bounds the total wait; any job still not finished when it elapses is
force-cancelled so shutdown can still complete. Its default,
``deployment_architecture.md``'s own documented drain bound (NFR-036:
"Up to 300 s for in-flight steps before forced termination") — not a
number invented for this fix, the platform's own existing policy for
exactly this situation.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass

from ai_os_kernel.observability.logging import get_logger

logger = get_logger(__name__)

# deployment_architecture.md / NFR-036's own documented graceful-
# shutdown drain bound — see this module's own docstring for why a
# bound exists at all.
_DEFAULT_GRACE_PERIOD_SECONDS = 300.0


@dataclass(frozen=True, slots=True)
class _CancelledJob:
    name: str
    task: asyncio.Task[None]


@dataclass(frozen=True, slots=True)
class _StopEventJob:
    name: str
    task: asyncio.Task[None]
    stop_event: asyncio.Event


class GracefulShutdownCoordinator:
    """Registers a process's background loops once, at startup, and
    drains all of them with one :meth:`shutdown` call.

    Registration order does not matter — every job is stopped
    concurrently, never sequentially (see this module's own docstring
    for why). ``grace_period_seconds`` bounds the total wait — see this
    module's own docstring for why a bound exists at all and where its
    default comes from.
    """

    def __init__(self, *, grace_period_seconds: float = _DEFAULT_GRACE_PERIOD_SECONDS) -> None:
        if grace_period_seconds <= 0:
            raise ValueError("grace_period_seconds must be positive")
        self._jobs: list[_CancelledJob | _StopEventJob] = []
        self._grace_period_seconds = grace_period_seconds

    def register_task(self, name: str, task: asyncio.Task[None]) -> None:
        """Registers a loop stopped by cancelling ``task`` directly —
        the shape a loop with no cooperative stop signal of its own
        needs."""
        self._jobs.append(_CancelledJob(name=name, task=task))

    def register_stop_event_task(
        self, name: str, task: asyncio.Task[None], stop_event: asyncio.Event
    ) -> None:
        """Registers a loop stopped by setting ``stop_event`` — the
        gentler shape for a loop that already accepts one and drains
        its current iteration before exiting on its own."""
        self._jobs.append(_StopEventJob(name=name, task=task, stop_event=stop_event))

    async def shutdown(self) -> None:
        """Stops every registered job and waits up to
        ``grace_period_seconds`` for each to genuinely finish before
        returning — the process must not exit, and the engine/resources
        those jobs use must not be disposed, until this completes.

        Any job still not done when the grace period elapses is
        force-cancelled so this method always returns — a stuck job is
        surfaced as a real ``graceful_shutdown.job_forced`` warning, not
        an indefinite hang.

        Idempotent to call with zero registered jobs (a Kernel process
        with no database, hence none of these loops started at all).
        """
        if not self._jobs:
            return

        for job in self._jobs:
            if isinstance(job, _StopEventJob):
                job.stop_event.set()
            else:
                job.task.cancel()

        tasks = [job.task for job in self._jobs]
        _done, still_running = await asyncio.wait(tasks, timeout=self._grace_period_seconds)
        for task in still_running:
            task.cancel()

        for job in self._jobs:
            with contextlib.suppress(asyncio.CancelledError):
                await job.task
            if job.task in still_running:
                logger.warning("graceful_shutdown.job_forced", job=job.name)
            else:
                logger.info("graceful_shutdown.job_stopped", job=job.name)
