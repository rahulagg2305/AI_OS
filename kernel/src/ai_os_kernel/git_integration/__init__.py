"""Git Integration Service (``P03-S01-M24-T01``) — see
:mod:`ai_os_kernel.git_integration.service`'s own module docstring for
the real design.

Lives under ``kernel/src/ai_os_kernel/`` like every other real module
built this session, not as a separate ``platform_services/`` uv
workspace member — a deliberate, disclosed scope decision (product
owner approved): the ticket's own ``module_path`` is
``platform_services/git_integration``, a board label validated only
against the ticket's module number (``scripts/roadmap/stages.py``), not
cross-checked against real file location — the identical precedent
``P03-S05-M14-T04``/``T05`` already established. Whether Platform
Services become a genuinely separate packaging/deployment tier is real,
deferred, later architecture work.
"""

from __future__ import annotations
