"""Identifiers for Traceability Engine rows (``P04-S02-M16-T01``).

``new_link_id`` mirrors every other prefixed-ULID convention in this
codebase (data_model.md §2) — one random id per real, created row.

``compute_artifact_key`` is deliberately **not** a random id — the one
real, disclosed design decision this ticket needed a product-owner
call on (see :mod:`ai_os_kernel.traceability_engine.link_writer`'s own
module docstring for the full reasoning): a real-world artifact like
requirement ``FR-019`` is referenced independently, at different
times, by different callers (a Documentation Agent today, a QA Agent
tomorrow) with no shared state between them. A random key would force
every caller to already know an artifact's own row id before it could
link to it; a deterministic key computed from the artifact's own
real-world identity (``artifact_type`` + ``external_id``) lets any
caller compute the identical key independently and land on the same
row, with no prior lookup.
"""

from ulid import ULID


def new_link_id() -> str:
    return f"link_{ULID()}"


def compute_artifact_key(*, artifact_type: str, external_id: str) -> str:
    """Deterministic ``trace.artifacts.artifact_key`` for a given
    ``(artifact_type, external_id)`` pair — the same two artifacts
    (e.g. requirement ``FR-019``) always resolve to the identical key,
    from any caller, at any time. ``artifact_type`` is drawn from a
    closed, ten-value vocabulary (never containing ``:``), so this
    plain composite is unambiguous without hashing.
    """
    return f"{artifact_type}:{external_id}"
