"""The Capability Manager's pack lifecycle routes (api_architecture.md
§6.5, extended — see below): register/install a pack, activate it,
deactivate it, and read one pack's current record — all gated on
``pack:manage``/``pack:read`` and reusing the bootstrap-wired
``app.state.pack_lifecycle_repository`` (built in
:mod:`ai_os_kernel.bootstrap`, see its module docstring) unchanged.

**``POST /api/v1/packs`` is not in api_architecture.md §6.5's documented
list.** That section documents only ``GET /packs``, ``GET /packs/{id}``,
``POST /packs/{id}/activate``, and ``POST /packs/{id}/deactivate`` — no
route shape for *registering* a pack in the first place exists in the
docs at all (packs were presumably expected to arrive through a
not-yet-built discovery/marketplace flow). This step's own approved
framing requires a register/install operation, so ``POST /api/v1/packs``
is a reasoned, minimal addition here: the same resource-creation
convention already used for ``POST /api/v1/workflows``/
``POST /api/v1/experiments`` (§6.1/§6.3), returning ``201`` for a newly
created resource — not an invented business rule, just a route shape
the docs never specified for this specific action. ``GET /api/v1/packs``
(the list endpoint §6.5 *does* document) is deliberately not built here
either — out of scope, this step covers exactly the four operations its
own framing named (register, activate, deactivate, get one pack).

**Activate/deactivate return ``200`` with the real, complete
``PackRecord``, not §6.5's documented ``202``.** ``202`` implies
accepted-for-later, asynchronous processing — appropriate for a future
design where pack activation may need to wait on ADR-0007 human
approval for a pack that affects platform behaviour. Neither approval
gating nor any async worker exists yet (explicitly out of scope this
step); `PackLifecycleRepository.activate()`/`.deactivate()` complete
synchronously and return a genuinely terminal state. Returning ``202``
for work already finished by the time the handler returns would
misrepresent what happened — the identical reasoning already applied to
``POST /api/v1/workflows``' own ``200``-not-``202`` deviation.

**Error mapping**: :class:`~ai_os_kernel.capability_manager.errors.PackAlreadyRegisteredError`/
:class:`~ai_os_kernel.capability_manager.errors.InvalidPackTransitionError`
→ ``409`` (api_architecture.md §8: "409 | State conflict" — the same
status the docs already use for a conflicting approval decision);
:class:`~ai_os_kernel.capability_manager.errors.PackNotFoundError`
→ ``404``. An unexpected
:class:`~ai_os_kernel.capability_manager.errors.PackRegistrationError`
(a genuine database failure) is not caught here — it propagates to
FastAPI's own default `500` handler, the same "no bespoke handling for
truly unexpected failures" convention every other route in this
codebase already follows.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ai_os_kernel.capability_manager.errors import (
    InvalidPackTransitionError,
    PackAlreadyRegisteredError,
    PackNotFoundError,
)
from ai_os_kernel.capability_manager.models import PackRecord
from ai_os_kernel.capability_manager.repository import PackLifecycleRepository
from ai_os_kernel.security_manager import (
    PACK_MANAGE,
    PACK_READ,
    SecurityContext,
    require_permission,
)

router = APIRouter(prefix="/api/v1", tags=["packs"])


def _get_repository(request: Request) -> PackLifecycleRepository:
    repository: PackLifecycleRepository | None = getattr(
        request.app.state, "pack_lifecycle_repository", None
    )
    if repository is None:
        raise HTTPException(status_code=503, detail="capability manager is not available")
    return repository


class RegisterPackRequest(BaseModel):
    """Deliberately just the fields
    :meth:`~ai_os_kernel.capability_manager.repository.PackLifecycleRepository.register`
    already takes — no discovery, no manifest schema validation (that
    remains the Manifest Loader's job at a different point in the
    pipeline this step does not touch)."""

    pack_id: str
    version: str
    manifest: dict[str, Any] = Field(default_factory=dict)
    sdk_version: str
    min_kernel_version: str
    reason: str


class PackLifecycleActionRequest(BaseModel):
    """Shared by activate/deactivate — just ``reason``. ``actor`` is
    deliberately not a client-supplied field: it is the authenticated
    principal's own id, the same "who did this comes from
    authentication, not client-declared honesty" convention
    ``start_workflow`` already established."""

    reason: str


@router.post("/packs", response_model=PackRecord, status_code=201)
async def register_pack(
    body: RegisterPackRequest,
    # Declared before `repository` so FastAPI resolves it first — see
    # ai_os_kernel.routes.workflows for the identical ordering rule and
    # the bug it was fixed to prevent (an unauthenticated/unauthorized
    # caller must never learn whether a backend is even up before
    # learning it lacks access).
    security_context: SecurityContext = Depends(require_permission(PACK_MANAGE)),  # noqa: B008
    repository: PackLifecycleRepository = Depends(_get_repository),  # noqa: B008
) -> PackRecord:
    try:
        return await repository.register(
            pack_id=body.pack_id,
            version=body.version,
            manifest=body.manifest,
            sdk_version=body.sdk_version,
            min_kernel_version=body.min_kernel_version,
            actor=security_context.principal.principal_id,
            reason=body.reason,
        )
    except PackAlreadyRegisteredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/packs/{pack_id}/activate", response_model=PackRecord)
async def activate_pack(
    pack_id: str,
    body: PackLifecycleActionRequest,
    security_context: SecurityContext = Depends(require_permission(PACK_MANAGE)),  # noqa: B008
    repository: PackLifecycleRepository = Depends(_get_repository),  # noqa: B008
) -> PackRecord:
    try:
        return await repository.activate(
            pack_id=pack_id, actor=security_context.principal.principal_id, reason=body.reason
        )
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidPackTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/packs/{pack_id}/deactivate", response_model=PackRecord)
async def deactivate_pack(
    pack_id: str,
    body: PackLifecycleActionRequest,
    security_context: SecurityContext = Depends(require_permission(PACK_MANAGE)),  # noqa: B008
    repository: PackLifecycleRepository = Depends(_get_repository),  # noqa: B008
) -> PackRecord:
    try:
        return await repository.deactivate(
            pack_id=pack_id, actor=security_context.principal.principal_id, reason=body.reason
        )
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidPackTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/packs/{pack_id}", response_model=PackRecord)
async def get_pack(
    pack_id: str,
    _security_context: SecurityContext = Depends(require_permission(PACK_READ)),  # noqa: B008
    repository: PackLifecycleRepository = Depends(_get_repository),  # noqa: B008
) -> PackRecord:
    pack = await repository.get_pack(pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"no pack with id '{pack_id}'")
    return pack
