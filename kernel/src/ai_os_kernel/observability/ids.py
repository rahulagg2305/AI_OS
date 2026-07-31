"""Prefixed ULID identifiers for observability/audit rows.

Mirrors :mod:`ai_os_kernel.workflow_engine.ids` exactly (data_model.md
§2: "Prefixed ULID text, for example `wf_01HQ…`, `stp_01HQ…`. Sortable,
opaque, safe in URLs and logs.").
"""

from ulid import ULID


def new_audit_id() -> str:
    return f"aud_{ULID()}"
