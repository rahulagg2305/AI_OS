"""Prefixed ULID identifiers for workflow-state rows.

data_model.md §2: "Prefixed ULID text, for example `wf_01HQ…`,
`stp_01HQ…`. Sortable, opaque, safe in URLs and logs."
"""

from ulid import ULID


def new_workflow_id() -> str:
    return f"wf_{ULID()}"


def new_event_id() -> str:
    return f"evt_{ULID()}"


def new_lease_id() -> str:
    return f"lease_{ULID()}"


def new_step_id() -> str:
    return f"stp_{ULID()}"


def new_gate_result_id() -> str:
    return f"gr_{ULID()}"
