"""Unit tests for the real-time event stream endpoint
(``ai_os_kernel.routes.stream``, ``P06-S02-M37-T01``).

No real database: this endpoint's only two real dependencies
(``app.state.token_verifier``, ``app.state.event_bus``) are both built
unconditionally in ``_lifespan`` regardless of database configuration
(see ``bootstrap.py``'s own comment on ``app.state.event_bus``) — the
identical "auth/bus boundary only" scope
``tests/unit/kernel/routes/test_workflows.py`` already establishes for
its own database-backed sibling routes.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.event_bus.bus import InProcessEventBus
from ai_os_kernel.event_bus.models import Event

SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "unit-test-signing-key-at-least-32-bytes-long"


def _config() -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
    )


def _token(roles: list[str], *, signing_key: str = _SIGNING_KEY) -> str:
    claims = {
        "sub": "test-user",
        "roles": roles,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, signing_key, algorithm="HS256")


def _publish(client: TestClient, event_bus: InProcessEventBus, event: Event) -> None:
    """Publishes ``event`` on the same event loop the app's own
    ``TestClient`` runs on, via its real ``portal`` — the one real
    bridge a synchronous test has into that loop, not a second one."""
    assert client.portal is not None
    client.portal.call(event_bus.publish, event)


def test_a_missing_bearer_token_is_refused_before_accept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect("/api/v1/stream"),
    ):
        pass
    assert excinfo.value.code == 1008
    assert excinfo.value.reason == "missing or invalid bearer token"


def test_an_invalid_token_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect(
            "/api/v1/stream", headers={"Authorization": "Bearer not-a-real-token"}
        ),
    ):
        pass
    assert excinfo.value.code == 1008


def test_a_token_without_workflow_read_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect(
            "/api/v1/stream",
            headers={"Authorization": f"Bearer {_token([])}"},
        ),
    ):
        pass
    assert excinfo.value.code == 1008
    assert excinfo.value.reason == "missing required permission: workflow:read"


def test_a_bare_test_client_never_configures_the_security_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No ``with`` block — ``_lifespan`` never runs, mirroring
    ``test_workflows.py``'s own identical invariant test — so
    ``app.state.token_verifier`` genuinely does not exist, exercised
    through the route's own ``getattr(..., None)`` fallback, not
    skipped."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    client = TestClient(app)

    with (
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect(
            "/api/v1/stream",
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        ),
    ):
        pass
    assert excinfo.value.code == 1008
    assert excinfo.value.reason == "missing or invalid bearer token"


def test_an_unknown_topic_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with (
        TestClient(app) as client,
        client.websocket_connect(
            "/api/v1/stream", headers={"Authorization": f"Bearer {_token(['viewer'])}"}
        ) as websocket,
    ):
        websocket.send_text('{"topic": "not-a-real-topic"}')
        with pytest.raises(WebSocketDisconnect) as excinfo:
            websocket.receive_text()
    assert excinfo.value.code == 1008
    assert excinfo.value.reason == "unknown topic: 'not-a-real-topic'"


def test_an_experiment_topic_is_refused_with_a_clear_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``Event`` has no ``experiment_id`` field — see ``routes/stream.py``'s
    own module docstring for why this is a real, disclosed refusal, not
    a silently-accepted topic that could never match anything."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with (
        TestClient(app) as client,
        client.websocket_connect(
            "/api/v1/stream", headers={"Authorization": f"Bearer {_token(['viewer'])}"}
        ) as websocket,
    ):
        websocket.send_text('{"topic": "experiment:exp-1"}')
        with pytest.raises(WebSocketDisconnect) as excinfo:
            websocket.receive_text()
    assert excinfo.value.code == 1008
    assert "experiment_id" in (excinfo.value.reason or "")


def test_a_real_published_event_genuinely_reaches_a_subscribed_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real proof this ticket exists for: a real ``Event``,
    published to the exact same ``InProcessEventBus``
    ``app.state.event_bus`` holds, genuinely reaches a real, connected
    WebSocket client subscribed to the matching ``workflow:{id}``
    topic — end to end, not asserted against an isolated bus instance."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        event_bus: InProcessEventBus = app.state.event_bus

        with client.websocket_connect(
            "/api/v1/stream", headers={"Authorization": f"Bearer {_token(['viewer'])}"}
        ) as websocket:
            websocket.send_text('{"topic": "workflow:wf-real-1"}')

            _publish(
                client,
                event_bus,
                Event(
                    event_type="workflow.step_completed",
                    source="test",
                    workflow_id="wf-real-1",
                    payload={"stepId": "build"},
                ),
            )

            received = websocket.receive_text()
            assert '"workflow_id":"wf-real-1"' in received
            assert '"event_type":"workflow.step_completed"' in received


def test_an_event_for_a_different_workflow_id_does_not_reach_the_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        event_bus: InProcessEventBus = app.state.event_bus

        with client.websocket_connect(
            "/api/v1/stream", headers={"Authorization": f"Bearer {_token(['viewer'])}"}
        ) as websocket:
            websocket.send_text('{"topic": "workflow:wf-real-1"}')

            _publish(
                client,
                event_bus,
                Event(event_type="workflow.step_completed", source="test", workflow_id="wf-other"),
            )
            _publish(
                client,
                event_bus,
                Event(
                    event_type="workflow.step_completed",
                    source="test",
                    workflow_id="wf-real-1",
                    payload={"stepId": "matched"},
                ),
            )

            received = websocket.receive_text()
            assert '"stepId":"matched"' in received


def test_a_system_topic_matches_the_real_event_type_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        event_bus: InProcessEventBus = app.state.event_bus

        with client.websocket_connect(
            "/api/v1/stream", headers={"Authorization": f"Bearer {_token(['viewer'])}"}
        ) as websocket:
            websocket.send_text('{"topic": "system"}')

            _publish(
                client,
                event_bus,
                Event(event_type="workflow.step_completed", source="test", workflow_id="wf-1"),
            )
            _publish(client, event_bus, Event(event_type="system.pack_activated", source="test"))

            received = websocket.receive_text()
            assert '"event_type":"system.pack_activated"' in received
