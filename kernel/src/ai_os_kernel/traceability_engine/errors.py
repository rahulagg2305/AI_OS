"""Errors raised by the Traceability Engine."""


class TraceabilityValidationError(Exception):
    """A caller-supplied ``artifact_type``/``relationship``/
    ``confidence``/``created_by_type`` is not one of data_model.md
    §8's own closed vocabularies — raised here, before any real
    database call, so a caller gets a clear message instead of a raw
    ``CHECK`` constraint failure (mirrors
    :class:`~ai_os_kernel.observability.audit.AuditOutcome`'s own
    "clear error at construction time" reasoning, applied to plain
    ``str`` fields here since data_model.md §8 defines these as
    ``TEXT`` + ``CHECK``, not a Python enum anywhere)."""


class TraceabilityError(Exception):
    """A real database failure while recording or closing a
    traceability link — mirrors
    :class:`~ai_os_kernel.observability.errors.AuditLogError`'s own
    "wrap the real ``SQLAlchemyError``, name the operation" shape.
    """


class TraceLinkNotFoundError(Exception):
    """:meth:`~ai_os_kernel.traceability_engine.link_writer.
    SqlTraceLinkWriter.close_link` was asked to close a ``link_id``
    that does not exist, or that is already closed."""
