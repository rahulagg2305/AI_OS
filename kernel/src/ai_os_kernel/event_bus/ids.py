"""Prefixed ULID identifiers for Event Bus events.

data_model.md §2: "Prefixed ULID text, for example `wf_01HQ…`,
`stp_01HQ…`. Sortable, opaque, safe in URLs and logs." Deliberately
``bevt_``, not ``evt_`` — ``workflow.workflow_events`` already owns
that prefix for a genuinely different concept (event *sourcing*, this
module's own docstring's own explicit disclaimer), and reusing it here
would make an id ambiguous about which "event" it names.
"""

from ulid import ULID


def new_event_id() -> str:
    return f"bevt_{ULID()}"


def new_outbox_id() -> str:
    return f"obx_{ULID()}"
