"""Real error types for the Quality Gate Engine's own components — the
identical "one clear exception per real failure mode" discipline every
other Kernel package's own ``errors.py`` already establishes."""


class GateNotRegisteredError(Exception):
    """A caller asked to resolve a ``gateId`` no
    :class:`~ai_os_kernel.quality_gate_engine.registry.GateRegistry`
    implementation has a registered
    :class:`~ai_os_kernel.quality_gate_engine.registry.GateDefinition`
    for."""


class DuplicateGateIdError(Exception):
    """Two packs (or two entries within one pack) declared the same
    ``qualityGates[].id`` — gate ids are resolved raw, not derived with
    a ``pack_id/`` prefix the way agent/tool ids are (see
    :mod:`ai_os_kernel.quality_gate_engine.registry`'s own docstring for
    why), so a real collision is a real, structural ambiguity this
    module refuses to silently resolve by picking a winner."""
