"""Configuration routes (api_architecture.md §6.5: ``GET /config``,
``PATCH /config``, ``GET /config/flags``) — `P06-S01-M36-T04`, the last
remaining slice of module 36's own documented route surface this
session scoped down to (product-owner decision, 2026-08-06: the
Packs/config resource group, over Workflows or Approvals remainders,
since every route here reuses infrastructure that already exists with
zero new backing service needed).

**``GET /config`` calls :meth:`~ai_os_kernel.configuration_manager.
loader.ConfigurationManager.load`, never
:meth:`~ai_os_kernel.configuration_manager.loader.ConfigurationManager.
load_with_secrets_resolved`** — so "secrets redacted" (api_architecture.md
§6.5's own words) is structural, not a redaction step this route
performs: ``load()`` never resolves a ``secret://`` reference into a
real value at all, by that method's own documented scope (layer 7 is
``load_with_secrets_resolved``'s job alone). A ``secret://`` reference
surviving into the response is exactly that — a reference, never a
secret.

**``PATCH /config`` reuses :meth:`~ai_os_kernel.configuration_manager.
runtime_overrides.RuntimeOverrideStore.apply`, the exact "writer, then
route" sequence that class's own docstring already named as pending**
("Building the ``PATCH /api/v1/config`` route... is separate, later
work — this class is the layer that route calls into"). No parallel
audit mechanism: the same, already-proven
:class:`~ai_os_kernel.configuration_manager.audit.ConfigChangeWriter`
records the change before it takes effect, unchanged.

**Two real, minimal input checks keep this route to "non-security
configuration" (authentication_authorization.md §4.2's own
``maintainer`` grant wording), not invented business rules:**
``env``/``role`` are rejected (:class:`~ai_os_kernel.configuration_manager.
models.PlatformConfig`'s own docstring: "never a value a configuration
file may set"); a ``new_value`` that is a ``secret://`` string is
rejected (accepting one would let a caller inject a secret *reference*
through a route documented as non-security). **``config_key`` is
deliberately not restricted to ``PlatformConfig``'s own declared
fields** — :mod:`~ai_os_kernel.configuration_manager.feature_flags`'s
own docstring already documents feature flags as reading "a live
runtime override (layer 5)" through this identical
:class:`~ai_os_kernel.configuration_manager.runtime_overrides.
RuntimeOverrideStore`, keyed by flag name, never a ``PlatformConfig``
field; rejecting an unrecognised key here would silently break that
already-established, documented composition. A key genuinely unknown
to both still has a real, harmless effect: it changes nothing
observable in either ``GET /config`` or ``GET /config/flags``, an
honest no-op, not a confusing failure.

**``GET /config/flags`` enumerates every flag name any activated
pack's own manifest declares, then resolves each through the identical
:func:`~ai_os_kernel.configuration_manager.feature_flags.resolve_feature_flag`
every other real caller already uses — no parallel resolution logic.**
Constructs a fresh, empty
:class:`~ai_os_kernel.configuration_manager.feature_flags.
ExperimentOverrideStore` per request rather than requiring one on
``app.state``: this is a global, admin-facing view with no run in
scope (``run_id=None``), and that parameter's own resolution short-
circuits before ever touching the store when ``run_id`` is ``None`` —
a real, correctly-scoped-empty object, not a fake standing in for a
missing one (no Experiment Manager exists yet to own a real one).

**Every dependency resolves lazily via ``getattr(request.app.state,
..., None)``, the identical pattern every other route in this codebase
already establishes** — a missing ``configuration_manager``/
``runtime_override_store``/``config_change_writer`` degrades to a
clean ``503``, never a crash. ``pack_lifecycle_repository`` being
absent degrades further still, to an empty ``pack_manifests`` list
(layer 2 contributes nothing) rather than a ``503`` — packs are not
required for configuration to have a real, if narrower, effective
value.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ai_os_kernel.capability_manager.repository import PackLifecycleRepository
from ai_os_kernel.configuration_manager import (
    ConfigChangeAuditError,
    ConfigChangeWriter,
    ConfigurationError,
    ConfigurationManager,
    ExperimentOverrideStore,
    PlatformConfig,
    RuntimeOverrideStore,
    extract_feature_flag_defaults,
    resolve_feature_flag,
)
from ai_os_kernel.security_manager import (
    CONFIG_MANAGE,
    CONFIG_READ,
    SecurityContext,
    require_permission,
)
from ai_os_kernel.workflow_engine.pack_state import PackState

router = APIRouter(prefix="/api/v1", tags=["configuration"])

_IMMUTABLE_KEYS = frozenset({"env", "role"})


def _get_configuration_manager(request: Request) -> ConfigurationManager:
    manager: ConfigurationManager | None = getattr(request.app.state, "configuration_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="configuration manager is not available")
    return manager


def _get_runtime_override_store(request: Request) -> RuntimeOverrideStore:
    store: RuntimeOverrideStore | None = getattr(request.app.state, "runtime_override_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="runtime override store is not available")
    return store


def _get_config_change_writer(request: Request) -> ConfigChangeWriter:
    writer: ConfigChangeWriter | None = getattr(request.app.state, "config_change_writer", None)
    if writer is None:
        raise HTTPException(status_code=503, detail="config change writer is not available")
    return writer


def _get_pack_repository(request: Request) -> PackLifecycleRepository | None:
    return getattr(request.app.state, "pack_lifecycle_repository", None)


async def _activated_pack_manifests(
    repository: PackLifecycleRepository | None,
) -> list[dict[str, Any]]:
    """Every activated pack's own raw manifest, in activation order —
    :meth:`ConfigurationManager.load`'s own documented layer-2 input
    shape. A missing repository contributes nothing, the identical
    "absent means unaffected" degradation this codebase already applies
    to every other optional dependency."""
    if repository is None:
        return []
    all_packs = await repository.list_packs()
    activated = [pack for pack in all_packs if pack.state == PackState.ACTIVATED]
    activated.sort(key=lambda pack: pack.activated_at or datetime.min.replace(tzinfo=UTC))
    return [pack.manifest for pack in activated]


class UpdateConfigRequest(BaseModel):
    """``PATCH /config``'s own body — deliberately just the fields
    :meth:`RuntimeOverrideStore.apply` already takes. ``changed_by`` is
    not a client-supplied field: it is the authenticated principal's
    own id, the same "who did this comes from authentication" convention
    ``PackLifecycleActionRequest`` already establishes."""

    config_key: str
    new_value: Any
    reason: str


class FeatureFlagState(BaseModel):
    """One real, resolved feature flag — declared by at least one
    activated pack's own manifest, current value resolved through the
    identical layered precedence every other real caller uses."""

    name: str
    enabled: bool


@router.get("/config", response_model=PlatformConfig)
async def get_effective_config(
    request: Request,
    _security_context: SecurityContext = Depends(require_permission(CONFIG_READ)),  # noqa: B008
    configuration_manager: ConfigurationManager = Depends(_get_configuration_manager),  # noqa: B008
    runtime_override_store: RuntimeOverrideStore = Depends(_get_runtime_override_store),  # noqa: B008
) -> PlatformConfig:
    pack_manifests = await _activated_pack_manifests(_get_pack_repository(request))
    return configuration_manager.load(
        role=request.app.state.config.role,
        pack_manifests=pack_manifests,
        runtime_overrides=runtime_override_store.snapshot(),
    )


@router.patch("/config", response_model=PlatformConfig)
async def update_config(
    body: UpdateConfigRequest,
    request: Request,
    security_context: SecurityContext = Depends(require_permission(CONFIG_MANAGE)),  # noqa: B008
    configuration_manager: ConfigurationManager = Depends(_get_configuration_manager),  # noqa: B008
    runtime_override_store: RuntimeOverrideStore = Depends(_get_runtime_override_store),  # noqa: B008
    config_change_writer: ConfigChangeWriter = Depends(_get_config_change_writer),  # noqa: B008
) -> PlatformConfig:
    if body.config_key in _IMMUTABLE_KEYS:
        raise HTTPException(
            status_code=422, detail=f"'{body.config_key}' is bootstrap identity, not configurable"
        )
    if isinstance(body.new_value, str) and body.new_value.startswith("secret://"):
        raise HTTPException(
            status_code=422,
            detail="PATCH /config is for non-security configuration; secret:// references "
            "are not accepted here",
        )

    pack_manifests = await _activated_pack_manifests(_get_pack_repository(request))
    hypothetical_overrides = {
        **runtime_override_store.snapshot(),
        body.config_key: body.new_value,
    }
    # Validate the *would-be* result before touching the audit trail or
    # the store at all — a rejected change must leave no trace, real or
    # in-memory. `configuration_manager.load` never awaits anything (it
    # is the pure, synchronous merge — see that method's own docstring),
    # so this is a cheap, side-effect-free dry run.
    try:
        validated = configuration_manager.load(
            role=request.app.state.config.role,
            pack_manifests=pack_manifests,
            runtime_overrides=hypothetical_overrides,
        )
    except ConfigurationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"'{body.new_value!r}' is not a valid value for '{body.config_key}': {exc}",
        ) from exc

    try:
        await runtime_override_store.apply(
            config_change_writer,
            config_key=body.config_key,
            new_value=body.new_value,
            changed_by=security_context.principal.principal_id,
            reason=body.reason,
        )
    except ConfigChangeAuditError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return validated


@router.get("/config/flags", response_model=list[FeatureFlagState])
async def get_feature_flags(
    request: Request,
    _security_context: SecurityContext = Depends(require_permission(CONFIG_READ)),  # noqa: B008
    runtime_override_store: RuntimeOverrideStore = Depends(_get_runtime_override_store),  # noqa: B008
) -> list[FeatureFlagState]:
    pack_manifests = await _activated_pack_manifests(_get_pack_repository(request))
    names: set[str] = set()
    for manifest in pack_manifests:
        names.update(extract_feature_flag_defaults(manifest).keys())

    experiment_overrides = ExperimentOverrideStore()
    return [
        FeatureFlagState(
            name=name,
            enabled=resolve_feature_flag(
                name,
                run_id=None,
                experiment_overrides=experiment_overrides,
                runtime_overrides=runtime_override_store,
                pack_manifests=pack_manifests,
                default=False,
            ),
        )
        for name in sorted(names)
    ]
