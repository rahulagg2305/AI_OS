"""Real-time event stream endpoint (`P06-S02-M37-T01`, FR-096,
[ADR-0014](../../../../docs/18_decision_log/adr/ADR-0014-api-style-and-realtime-transport.md)).

ADR-0014 names four topics (`workflow:{id}`, `experiment:{id}`,
`approvals`, `system`) and says server->client push "carries the same
versioned event envelope as the Event Bus" — this module is that real
wiring, reusing :class:`~ai_os_kernel.event_bus.bus.InProcessEventBus`
directly rather than inventing a second delivery mechanism.

**Two real, disclosed gaps investigated before writing this module, not
discovered after (product-owner decision via `AskUserQuestion`):**

1. **No Topic/Channel Manager exists** (`event_bus.md`'s own
   Implementation Status: "no Topic/Channel Manager"). The bus's own
   real filter primitive is `subscribe(event_type, handler)`, not a
   topic string. This module maps each of ADR-0014's own topic shapes
   onto the real fields `Event` already has: `workflow:{id}` matches
   `event.workflow_id`; `system`/`approvals` match an `event_type`
   prefix convention (`"system."`/`"approval."`) — a real, closed,
   documented vocabulary, not an arbitrary hardcoded value. `Event` has
   no `experiment_id` field, so `experiment:{id}` is refused with a
   clear, honest close reason rather than silently accepted and never
   matching anything.
2. **No real Kernel component publishes to the bus yet** (same
   document: "the Workflow Engine... does not yet... call
   `InProcessEventBus.publish`"). This module wires the real consumer
   side end to end — proven by a real test that publishes a real
   `Event` and asserts a connected client receives it — but a real
   production publisher (the Workflow Engine, Quality Gate Engine, ...)
   is genuinely separate, unbuilt work, not something this ticket's own
   Goal/Input/Output ("A subscription." / "Live events over
   /api/v1/stream.") asks for.

**Auth is real, not a parallel mechanism** — the same
:class:`~ai_os_kernel.security_manager.token_verifier.TokenVerifier` /
:func:`~ai_os_kernel.security_manager.role_administration.resolve_effective_roles`
/ :func:`~ai_os_kernel.security_manager.permissions.permissions_for_roles`
chain :func:`~ai_os_kernel.security_manager.dependencies.authenticate`
already uses, called directly here rather than through that function,
because FastAPI's `Depends()` resolves an HTTP `Request` for HTTP
routes and a `WebSocket` for WebSocket routes — `authenticate`'s own
signature is typed for the former. `WORKFLOW_READ` is required (the
same flat permission `GET /api/v1/workflows` already requires) —
matching ADR-0014's own "every channel enforces identically," and the
identical flat, no-per-instance-ownership permission model this
codebase uses everywhere else (no route in this codebase checks
"do you own this specific workflow instance").
"""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ai_os_kernel.event_bus.bus import EventBus, Subscription
from ai_os_kernel.event_bus.models import Event
from ai_os_kernel.observability.logging import get_logger
from ai_os_kernel.security_manager.errors import InvalidTokenError
from ai_os_kernel.security_manager.models import SecurityContext
from ai_os_kernel.security_manager.permissions import WORKFLOW_READ, permissions_for_roles
from ai_os_kernel.security_manager.role_administration import (
    RoleGrantRepository,
    resolve_effective_roles,
)
from ai_os_kernel.security_manager.token_verifier import TokenVerifier

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["stream"])

_WORKFLOW_TOPIC_PREFIX = "workflow:"
_EXPERIMENT_TOPIC_PREFIX = "experiment:"
_SYSTEM_TOPIC = "system"
_APPROVALS_TOPIC = "approvals"
_SYSTEM_EVENT_TYPE_PREFIX = "system."
_APPROVAL_EVENT_TYPE_PREFIX = "approval."

# RFC 6455 close codes — 1008 "Policy Violation" for every real refusal
# this endpoint itself decides (auth, permission, malformed/unknown
# topic); 1011 "Internal Error" for a genuinely unconfigured server.
_POLICY_VIOLATION = 1008
_INTERNAL_ERROR = 1011


async def _authenticate_websocket(websocket: WebSocket) -> SecurityContext | None:
    """The same real verify -> resolve-effective-roles -> compute-permissions
    chain :func:`~ai_os_kernel.security_manager.dependencies.authenticate`
    uses, read from the WebSocket handshake's own real headers (still a
    genuine HTTP request at that point) rather than through
    ``Depends(authenticate)`` — see this module's own docstring for why.
    Returns ``None`` for every real failure (unconfigured verifier,
    missing/malformed header, invalid token) — the caller closes the
    connection; this function never raises."""
    verifier: TokenVerifier | None = getattr(websocket.app.state, "token_verifier", None)
    if verifier is None:
        return None

    authorization = websocket.headers.get("authorization")
    if authorization is None or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[len("bearer ") :]

    try:
        principal = await verifier.verify(token)
    except InvalidTokenError:
        return None

    role_grant_repository: RoleGrantRepository | None = getattr(
        websocket.app.state, "role_grant_repository", None
    )
    principal = await resolve_effective_roles(principal, role_grant_repository)
    return SecurityContext(principal=principal, permissions=permissions_for_roles(principal.roles))


def _topic_is_recognized(topic: str) -> bool:
    return topic.startswith(_WORKFLOW_TOPIC_PREFIX) or topic in (_SYSTEM_TOPIC, _APPROVALS_TOPIC)


def _event_matches_topic(event: Event, topic: str) -> bool:
    """The real topic -> `Event` field mapping this module's own
    docstring discloses — see there for why `experiment:{id}` is
    refused before ever reaching here."""
    if topic.startswith(_WORKFLOW_TOPIC_PREFIX):
        return event.workflow_id == topic[len(_WORKFLOW_TOPIC_PREFIX) :]
    if topic == _SYSTEM_TOPIC:
        return event.event_type.startswith(_SYSTEM_EVENT_TYPE_PREFIX)
    if topic == _APPROVALS_TOPIC:
        return event.event_type.startswith(_APPROVAL_EVENT_TYPE_PREFIX)
    return False


@router.websocket("/stream")
async def stream(websocket: WebSocket) -> None:
    """One subscription per connection — the client's first text frame
    must be ``{"topic": "<topic>"}``; every matching real `Event`
    published to the bus afterward is pushed as its own JSON text frame
    (the versioned envelope itself, ADR-0014's "same event envelope").
    Refuses to accept the connection at all (never accept-then-close)
    for every auth/permission/configuration failure — the identical
    fail-closed posture ``authenticate``/``require_permission`` already
    establish for every HTTP route.
    """
    security_context = await _authenticate_websocket(websocket)
    if security_context is None:
        await websocket.close(code=_POLICY_VIOLATION, reason="missing or invalid bearer token")
        return
    if not security_context.has_permission(WORKFLOW_READ):
        await websocket.close(
            code=_POLICY_VIOLATION, reason=f"missing required permission: {WORKFLOW_READ}"
        )
        return

    event_bus: EventBus | None = getattr(websocket.app.state, "event_bus", None)
    if event_bus is None:
        await websocket.close(code=_INTERNAL_ERROR, reason="event bus is not configured")
        return

    await websocket.accept()

    topic: str | None = None
    subscription: Subscription | None = None

    async def _on_event(event: Event) -> None:
        if topic is not None and _event_matches_topic(event, topic):
            await websocket.send_text(event.model_dump_json())

    try:
        raw = await websocket.receive_text()
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.close(
                code=_POLICY_VIOLATION, reason="subscription message must be valid JSON"
            )
            return

        requested_topic = message.get("topic") if isinstance(message, dict) else None
        if not isinstance(requested_topic, str) or not requested_topic:
            await websocket.close(
                code=_POLICY_VIOLATION,
                reason="subscription message must declare a non-empty 'topic'",
            )
            return
        if requested_topic.startswith(_EXPERIMENT_TOPIC_PREFIX):
            await websocket.close(
                code=_POLICY_VIOLATION,
                reason=(
                    "'experiment:{id}' topics are not yet supported — "
                    "Event carries no experiment_id field to match against"
                ),
            )
            return
        if not _topic_is_recognized(requested_topic):
            await websocket.close(
                code=_POLICY_VIOLATION, reason=f"unknown topic: {requested_topic!r}"
            )
            return

        topic = requested_topic
        subscription = event_bus.subscribe(None, _on_event)
        logger.info(
            "stream.subscribed",
            principal_id=security_context.principal.principal_id,
            topic=topic,
        )

        while True:
            # Real disconnect detection — real event delivery happens
            # concurrently, from the bus's own per-subscriber consumer
            # task calling `_on_event` above, not from this loop.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if subscription is not None:
            event_bus.unsubscribe(subscription)
            logger.info(
                "stream.unsubscribed",
                principal_id=security_context.principal.principal_id,
                topic=topic,
            )
