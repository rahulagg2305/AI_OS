"""Real, persisted Traceability Engine rows — what
:meth:`~ai_os_kernel.traceability_engine.link_writer.SqlTraceLinkWriter.record_link`
writes and :meth:`~ai_os_kernel.traceability_engine.link_writer.SqlTraceLinkWriter.get_open_link`
reads back, mirroring :class:`~ai_os_kernel.observability.audit.AuditLogRecord`'s
own "one real, persisted row" shape exactly.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TraceArtifact(BaseModel):
    """One real, persisted ``trace.artifacts`` row (data_model.md §8)."""

    model_config = ConfigDict(frozen=True)

    artifact_key: str
    artifact_type: str
    external_id: str
    title: str
    location: str
    version: str


class ArtifactInput(BaseModel):
    """One endpoint (source or target) of a real link a caller wants
    recorded — every field :meth:`~ai_os_kernel.traceability_engine.
    link_writer.SqlTraceLinkWriter.record_link` needs to upsert the
    real ``trace.artifacts`` row this artifact resolves to, grouped
    into one value object purely for a readable call site (identical
    fields to :class:`TraceArtifact` minus the computed ``artifact_key``,
    never a new column or concept)."""

    model_config = ConfigDict(frozen=True)

    artifact_type: str
    external_id: str
    title: str
    location: str
    version: str


class TraceLink(BaseModel):
    """One real, persisted ``trace.links`` row (data_model.md §8)."""

    model_config = ConfigDict(frozen=True)

    link_id: str
    source_key: str
    relationship: str
    target_key: str
    confidence: str
    created_by: str
    created_by_type: str
    created_at: datetime
    closed_at: datetime | None
