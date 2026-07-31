"""Layer 6, feature flags / experiment overrides (configuration_manager.md
§4: "Experiment overrides — Per-run, isolated to that run"; ADR-0022:
"Experiment overrides (6) beat runtime overrides (5) ... An experiment
must be able to pin conditions regardless of what an operator changed
globally mid-run") — ``P01-S02-M01-T07``.

**Unlike every other layer, this one is deliberately never merged into
the single, process-wide dict :meth:`~ai_os_kernel.configuration_manager.
loader.ConfigurationManager._merge_layers` builds.** §4 requires layer 6
"isolated to that run... apply only to workflows belonging to that
experiment and never leak into concurrent workflows" — a shared global
dict is exactly the wrong shape for that. :class:`ExperimentOverrideStore`
instead keys overrides by ``run_id``; a different run can never observe
another run's overrides, by construction, not by convention.

**Where a flag's readable state (this Task's Output) comes from, in
precedence order:**

1. This run's isolated override (:meth:`ExperimentOverrideStore.snapshot`),
   if ``run_id`` is given and it declares the flag — outranks everything.
2. A live runtime override (layer 5, :class:`~ai_os_kernel.
   configuration_manager.runtime_overrides.RuntimeOverrideStore`) —
   reused directly, not reimplemented, the same "compose with the layer
   already built" discipline layers 2-5-7 all followed.
3. The last activated pack manifest that declares the flag in its own
   ``featureFlags`` array (manifest.schema.json: ``{name, default,
   description}``) — a later pack overrides an earlier one, the same
   "later entry wins" rule :func:`~ai_os_kernel.configuration_manager.
   loader.extract_pack_defaults` already follows for ``configSchema``.
4. The caller-supplied ``default`` — layer 1's built-in-default role,
   for a flag no pack even declares.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from typing import Any

from ai_os_kernel.configuration_manager.runtime_overrides import RuntimeOverrideStore


def extract_feature_flag_defaults(manifest: Mapping[str, Any]) -> dict[str, bool]:
    """Pulls ``{name: default}`` out of a pack manifest's own top-level
    ``featureFlags`` array. A manifest with no ``featureFlags``, or an
    entry missing ``name``/``default``, contributes nothing."""
    entries = manifest.get("featureFlags")
    if not isinstance(entries, list):
        return {}
    return {
        entry["name"]: bool(entry["default"])
        for entry in entries
        if isinstance(entry, dict) and "name" in entry and "default" in entry
    }


class ExperimentOverrideStore:
    """Layer 6's live state: per-``run_id`` isolated feature-flag
    overrides. Thread-safe, mirroring
    :class:`~ai_os_kernel.configuration_manager.runtime_overrides.
    RuntimeOverrideStore`'s own shape."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_run: dict[str, dict[str, bool]] = {}

    def set_override(self, run_id: str, flag_name: str, value: bool) -> None:
        """Sets one flag for one run only — no other run's
        :meth:`snapshot` is ever affected by this call."""
        with self._lock:
            self._by_run.setdefault(run_id, {})[flag_name] = value

    def snapshot(self, run_id: str) -> dict[str, bool]:
        """Every override recorded for ``run_id`` — never another
        run's, by construction: a KeyError-free lookup on a different
        ``run_id`` simply returns an empty mapping."""
        with self._lock:
            return dict(self._by_run.get(run_id, {}))

    def clear_run(self, run_id: str) -> None:
        """Isolation's other half: once a run ends, its overrides do
        not linger to be accidentally inherited by an unrelated later
        run that happens to reuse identifying details."""
        with self._lock:
            self._by_run.pop(run_id, None)


def resolve_feature_flag(
    flag_name: str,
    *,
    run_id: str | None,
    experiment_overrides: ExperimentOverrideStore,
    runtime_overrides: RuntimeOverrideStore | None = None,
    pack_manifests: Sequence[Mapping[str, Any]] = (),
    default: bool = False,
) -> bool:
    """The one real function this Task's Output is: a flag's current,
    readable boolean state, resolved through every layer that can set
    one, in the precedence order this module's own docstring states."""
    if run_id is not None:
        run_overrides = experiment_overrides.snapshot(run_id)
        if flag_name in run_overrides:
            return run_overrides[flag_name]

    if runtime_overrides is not None:
        live_value = runtime_overrides.snapshot().get(flag_name)
        if isinstance(live_value, bool):
            return live_value

    resolved = default
    for manifest in pack_manifests:
        pack_flags = extract_feature_flag_defaults(manifest)
        if flag_name in pack_flags:
            resolved = pack_flags[flag_name]
    return resolved
