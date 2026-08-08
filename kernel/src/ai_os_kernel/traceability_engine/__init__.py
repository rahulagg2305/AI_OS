"""Traceability Engine — Requirement -> Architecture -> Implementation -> Test links.

Explicit links only, never inferred silently. Supports impact analysis
and coverage queries (e.g. "which requirements have no verifying test").

- :class:`TraceLinkWriter`/:class:`SqlTraceLinkWriter` (added
  2026-08-08, ``P04-S02-M16-T01``) — the real ``trace.links`` writer.
  Upserts both endpoint ``trace.artifacts`` rows inline, keyed
  deterministically off their own real-world identity, then records
  (or, for an already-open identical triple, idempotently returns) the
  link. See :mod:`ai_os_kernel.traceability_engine.link_writer`.
- :func:`~ai_os_kernel.traceability_engine.impact_query.find_affected_artifacts`
  (added 2026-08-08, ``P04-S02-M16-T02``) — data_model.md §8's own
  "recursive CTEs over trace.links" impact analysis, now real: every
  artifact transitively reachable from a given one via open links,
  traversed bidirectionally (a real, product-owner-decided design
  choice — see that module's own docstring), with a real cycle guard.
  See :mod:`ai_os_kernel.traceability_engine.impact_query`.

Not yet implemented: coverage analysis (``P04-S02-M16-T03``) and any
Agent/Workflow wiring — nothing calls this writer or query yet.

See docs/03_architecture/kernel/traceability_engine.md.
"""

from ai_os_kernel.traceability_engine.errors import (
    TraceabilityError,
    TraceabilityValidationError,
    TraceLinkNotFoundError,
)
from ai_os_kernel.traceability_engine.ids import compute_artifact_key, new_link_id
from ai_os_kernel.traceability_engine.impact_query import find_affected_artifacts
from ai_os_kernel.traceability_engine.link_writer import SqlTraceLinkWriter, TraceLinkWriter
from ai_os_kernel.traceability_engine.models import ArtifactInput, TraceArtifact, TraceLink

__all__ = [
    "ArtifactInput",
    "SqlTraceLinkWriter",
    "TraceArtifact",
    "TraceLink",
    "TraceLinkNotFoundError",
    "TraceLinkWriter",
    "TraceabilityError",
    "TraceabilityValidationError",
    "compute_artifact_key",
    "find_affected_artifacts",
    "new_link_id",
]
