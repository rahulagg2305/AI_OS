"""``POST /api/v1/voice/intent`` — the Voice (Jarvis) subsystem's first
production entry point.

**Why this exists.** `voice_jarvis` was risk register R-018 item 5: real,
tested code (`PlatformIntentRouter`, 4 real intents, a real permission
gate) with zero production importers, no route, and no entry point. The
whole subsystem was unreachable from any running process. This route is
the thinnest thing that makes it genuinely reachable — it constructs the
already-real router from already-real, already-bootstrapped collaborators
and calls its already-real `handle`. No new intent logic lives here.

**The contract is invented here, and that is disclosed rather than
glossed.** Neither `voice_architecture.md` nor `api_architecture.md` §6
documents any voice endpoint at all, so the path, the request shape and
the status-code mapping had to be chosen (product owner, 2026-08-13).
Every choice reuses an existing precedent rather than inventing a second
convention:

* ``/api/v1/voice/intent`` follows the ``/api/v1/<subsystem>/<noun>``
  shape ``/traceability/impact``, ``/usage/tokens`` and ``/gates/results``
  already use.
* The request body **is** the already-real
  :class:`~ai_os_kernel.voice_jarvis.models.VoiceIntent`, and the
  response **is** the already-real
  :class:`~ai_os_kernel.voice_jarvis.models.VoiceActionResult` — no
  parallel route-local DTOs that could drift from the router's own
  contract.
* ``POST`` rather than ``GET``: `decide_approval` genuinely mutates
  state, and one endpoint accepting one intent union is what the router
  itself already models.

**Permissions are deliberately not re-checked here.** `authenticate`
establishes the real principal; the router then applies exactly the gates
it already applies — ``workflow:read`` for the two read intents, and
`ApprovalService`'s own real class-scoped authorization for
``decide_approval``. Adding a flat route-level permission would either
duplicate that logic or, worse, disagree with it — the identical
reasoning ``POST``/``DELETE /api/v1/security/role-grants`` already
records for being authenticated but not flat-permission-gated.

**Speech is still not wired.** This accepts an *already-structured*
intent, never audio: wake word, STT and TTS remain genuinely unbuilt, and
`speech_gateway` therefore remains idle and disclosed under R-018. The
route does not pretend otherwise.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.health import HealthService
from ai_os_kernel.security_manager import SecurityContext, authenticate
from ai_os_kernel.security_manager.errors import ApprovalNotAuthorizedError
from ai_os_kernel.security_manager.role_administration import SqlRoleGrantRepository
from ai_os_kernel.voice_jarvis.errors import VoiceIntentError
from ai_os_kernel.voice_jarvis.intent_router import PlatformIntentRouter
from ai_os_kernel.voice_jarvis.models import VoiceActionResult, VoiceIntent
from ai_os_kernel.workflow_engine.errors import ApprovalNotPendingError
from ai_os_kernel.workflow_engine.human_approval import ApprovalService, SqlApprovalRepository
from ai_os_kernel.workflow_engine.repository import WorkflowInstanceRepository

router = APIRouter(prefix="/api/v1", tags=["voice"])


def _get_engine(request: Request) -> AsyncEngine:
    # The identical `app.state.database_engine` accessor
    # `routes/approvals.py`/`routes/traceability.py` already establish.
    engine: AsyncEngine | None = getattr(request.app.state, "database_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="voice subsystem is not available")
    return engine


def _build_router(request: Request) -> PlatformIntentRouter:
    """Assemble the real router from the real, already-bootstrapped
    collaborators. Built per request rather than once at startup for the
    same reason `routes/approvals.py` builds its own `ApprovalService`
    per request: `SqlApprovalRepository`/`SqlRoleGrantRepository` are
    thin engine wrappers, and a per-request build cannot capture a stale
    engine across a lifespan restart."""
    engine = _get_engine(request)
    health_service: HealthService | None = getattr(request.app.state, "health_service", None)
    instance_repository: WorkflowInstanceRepository | None = getattr(
        request.app.state, "workflow_instance_repository", None
    )
    if health_service is None or instance_repository is None:
        raise HTTPException(status_code=503, detail="voice subsystem is not available")
    return PlatformIntentRouter(
        health_service=health_service,
        workflow_instance_repository=instance_repository,
        approval_service=ApprovalService(
            SqlApprovalRepository(engine),
            role_grant_repository=SqlRoleGrantRepository(engine),
        ),
    )


@router.post("/voice/intent", response_model=VoiceActionResult)
async def handle_voice_intent(
    request: Request,
    intent: VoiceIntent,
    security_context: SecurityContext = Depends(authenticate),  # noqa: B008
) -> VoiceActionResult:
    intent_router = _build_router(request)
    try:
        return await intent_router.handle(intent, principal=security_context.principal)
    except ApprovalNotAuthorizedError as exc:
        # The identical mapping `routes/approvals.py` already uses for
        # the identical two exceptions, reached through the identical
        # `ApprovalService.decide` call.
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ApprovalNotPendingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except VoiceIntentError as exc:
        # `PlatformIntentRouter` raises this both for a missing required
        # slot and for a failed permission check, so it cannot be mapped
        # to a single status here without re-deriving the router's own
        # decision. 400 is chosen because the router's own contract
        # treats it as "this intent, as submitted, cannot be actioned" —
        # a real, disclosed coarsening, not a claim that authorization
        # and validation are the same thing.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
