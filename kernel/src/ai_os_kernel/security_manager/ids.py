"""Prefixed ULID identifiers for Security Manager rows.

Mirrors :mod:`ai_os_kernel.workflow_engine.ids`/
:mod:`ai_os_kernel.observability.ids` exactly (data_model.md §2:
"Prefixed ULID text, for example `wf_01HQ…`, `stp_01HQ…`. Sortable,
opaque, safe in URLs and logs.").
"""

from ulid import ULID


def new_role_grant_id() -> str:
    return f"rg_{ULID()}"
