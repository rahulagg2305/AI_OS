"""The Platform Integration Layer (`voice_architecture.md` §4.5) —
this ticket's own real, first increment (`P06-S06-M33-T01`).

**Lives inside the Kernel, not `capability_packs/voice_jarvis` —
a genuine structural finding, not the originally planned home.** A
first attempt built this as a pure external HTTP-client Capability
Pack, mirroring `tools/aios`'s own proven "pure API client" shape.
`pack_contract_suite` check 7 (`platform_sdk.md` §9/§10) caught it for
real: **any** direct HTTP client import in pack code is forbidden,
full stop — including a call to the platform's own Kernel API, not
only a third-party provider (`ai_os_sdk.testing.forbidden_imports`'s
own module docstring, "sixth category": "a compliant pack reaches
external services only through the SDK's own Protocols ... never a
raw transport library"). No SDK Protocol for "read workflow status" or
"decide an approval" exists yet, so this increment lives here instead
— the identical "build inside the Kernel, not a separate package"
precedent Notification Service and the Speech Gateway itself already
establish — and calls the real Kernel-internal Protocols directly (no
HTTP at all, no serialization round trip).

**Real, disclosed, NOT built this step**: wake word, STT, intent
recognition (needs the LLM Gateway per §4.8), and the §4.7 TTS output
half (needs `SpeechGateway.synthesize()`, also Kernel-internal — a
real caller can reach it directly once one exists, unlike the earlier,
rejected pack design). See this ticket's own README-equivalent (the
package docstring) for the full disclosed scope.

**Authorization**: `voice_architecture.md` §5 — "voice commands must
be authenticated and authorized." This router takes an
already-authenticated :class:`~ai_os_kernel.security_manager.models.
Principal` (a caller — a future voice HTTP/WS endpoint — has already
verified the bearer token; this layer never does that itself, the
identical division every other Kernel-internal service in this
codebase already follows), and enforces the same real
``workflow:read`` permission gate `routes.workflows`'s own read routes
already require for `list_workflows`/`get_workflow_status`.
`decide_approval` needs no separate check here: `ApprovalService.decide`
already enforces its own real, class-scoped authorization.
"""

from __future__ import annotations

from typing import Protocol, cast

from ai_os_kernel.health import HealthService
from ai_os_kernel.security_manager import WORKFLOW_READ, Principal, permissions_for_roles
from ai_os_kernel.security_manager.errors import ApprovalNotAuthorizedError
from ai_os_kernel.voice_jarvis.errors import VoiceIntentError
from ai_os_kernel.voice_jarvis.models import VoiceActionResult, VoiceIntent
from ai_os_kernel.workflow_engine.errors import ApprovalNotPendingError
from ai_os_kernel.workflow_engine.human_approval import ApprovalService, Decision
from ai_os_kernel.workflow_engine.instance import WorkflowInstance
from ai_os_kernel.workflow_engine.repository import WorkflowListCursor

_VALID_DECISIONS = {"approved", "rejected"}


class WorkflowStatusReader(Protocol):
    """The one, narrow real read side this router needs — a real
    :class:`~ai_os_kernel.workflow_engine.repository.
    WorkflowInstanceRepository` structurally satisfies this
    automatically (it is a strict superset), the identical
    "declare only what you actually use" shape
    :class:`~ai_os_kernel.observability.audit_verification_job.
    AuditChainReader` already establishes for its own, unrelated
    real reader."""

    async def list_instances(
        self, *, limit: int, before: WorkflowListCursor | None = None
    ) -> list[WorkflowInstance]: ...

    async def get_instance(self, workflow_id: str) -> WorkflowInstance | None: ...


class PlatformIntentRouter:
    def __init__(
        self,
        *,
        health_service: HealthService,
        workflow_instance_repository: WorkflowStatusReader,
        approval_service: ApprovalService,
    ) -> None:
        self._health_service = health_service
        self._workflow_instance_repository = workflow_instance_repository
        self._approval_service = approval_service

    async def handle(self, intent: VoiceIntent, *, principal: Principal) -> VoiceActionResult:
        if intent.intent_type == "check_health":
            return await self._check_health()
        if intent.intent_type == "list_workflows":
            self._require_permission(principal, WORKFLOW_READ)
            return await self._list_workflows()
        if intent.intent_type == "get_workflow_status":
            self._require_permission(principal, WORKFLOW_READ)
            return await self._get_workflow_status(intent)
        return await self._decide_approval(intent, principal)

    def _require_permission(self, principal: Principal, permission: str) -> None:
        if permission not in permissions_for_roles(principal.roles):
            raise VoiceIntentError(
                f"principal '{principal.principal_id}' lacks required permission '{permission}'"
            )

    async def _check_health(self) -> VoiceActionResult:
        report = await self._health_service.readiness()
        return VoiceActionResult(
            intent_type="check_health",
            platform_action="HealthService.readiness()",
            response_text=f"Platform status is {report.status}.",
            raw_response=report.model_dump(mode="json"),
        )

    async def _list_workflows(self) -> VoiceActionResult:
        instances = await self._workflow_instance_repository.list_instances(limit=100)
        count = len(instances)
        return VoiceActionResult(
            intent_type="list_workflows",
            platform_action="WorkflowInstanceRepository.list_instances()",
            response_text=f"There {'is' if count == 1 else 'are'} {count} "
            f"workflow instance{'' if count == 1 else 's'}.",
            raw_response={"count": count},
        )

    async def _get_workflow_status(self, intent: VoiceIntent) -> VoiceActionResult:
        if not intent.workflow_id:
            raise VoiceIntentError("get_workflow_status requires workflow_id")
        instance = await self._workflow_instance_repository.get_instance(intent.workflow_id)
        if instance is None:
            raise VoiceIntentError(f"no workflow instance with id '{intent.workflow_id}'")
        step_clause = (
            f", currently at step '{instance.current_step_id}'" if instance.current_step_id else ""
        )
        return VoiceActionResult(
            intent_type="get_workflow_status",
            platform_action="WorkflowInstanceRepository.get_instance()",
            response_text=f"Workflow {intent.workflow_id} is {instance.status.value}{step_clause}.",
            raw_response=instance.model_dump(mode="json"),
        )

    async def _decide_approval(
        self, intent: VoiceIntent, principal: Principal
    ) -> VoiceActionResult:
        if not intent.approval_id:
            raise VoiceIntentError("decide_approval requires approval_id")
        if intent.decision not in _VALID_DECISIONS:
            raise VoiceIntentError(
                f"decision must be one of {sorted(_VALID_DECISIONS)}, got {intent.decision!r}"
            )
        try:
            decided = await self._approval_service.decide(
                approval_id=intent.approval_id,
                principal=principal,
                decision=cast(Decision, intent.decision),
                comment=None,
            )
        except (ApprovalNotPendingError, ApprovalNotAuthorizedError) as exc:
            raise VoiceIntentError(str(exc)) from exc
        return VoiceActionResult(
            intent_type="decide_approval",
            platform_action="ApprovalService.decide()",
            response_text=f"Approval {intent.approval_id} was {decided.status}.",
            raw_response=decided.model_dump(mode="json"),
        )
