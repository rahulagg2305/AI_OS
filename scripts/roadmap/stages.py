"""The Phase and Stage vocabulary, and the frozen Module registry.

**Phase and Module numbering are frozen** (the Phase R1 decision).
Phases ``P01``-``P08`` are a fixed bijection onto the roadmap's existing
Stages A-H (``docs/19_roadmap/implementation_roadmap.md`` §3); Modules
``M01``-``M44`` keep the exact numbers ``feature_inventory.md`` §5 has
always used, because dozens of documents reference them. Neither is ever
renumbered. Only Stage and Task allocate fresh numbers.

Stages are the level R1 found genuinely missing: a *named work-slice*
inside a Phase. The ``Platform SDK v1.0.0`` initiative was exactly this
and had nowhere to live, so it became a standalone scope document.
"""

from __future__ import annotations

# P01..P08 <-> roadmap Stage letters A..H. Never renumbered; letters kept
# as aliases so every existing "Stage B" reference stays resolvable.
PHASES: dict[int, tuple[str, str]] = {
    1: ("A", "Platform Skeleton"),
    2: ("B", "Minimum Viable Kernel"),
    3: ("C", "First Real Capability Pack"),
    4: ("D", "Evaluation and Multi-LLM Experimentation"),
    5: ("E", "Project Intelligence"),
    6: ("F", "Dashboard, Voice, Notifications"),
    7: ("G", "Hardening and Production Readiness"),
    8: ("H", "Expansion"),
    # P09 has no roadmap Stage letter: the restructuring that built this
    # ticket system is process work, not one of implementation_roadmap.md
    # §3's product delivery Stages. Recorded as its own Phase (2026-07-31,
    # R4) so the work is visible to the very system it created rather
    # than existing only in commit history.
    9: ("-", "Roadmap System and Process"),
}

# (phase, stage) -> stage title. Named work-slices, derived from the
# roadmap's own per-stage deliverable groupings.
STAGES: dict[tuple[int, int], str] = {
    (1, 1): "Process, Packaging and Persistence Baseline",
    (1, 2): "Configuration and Secrets",
    (1, 3): "Manifest Discovery and Schema",
    (1, 4): "Health and Lifecycle",
    (1, 5): "Observability and Audit",
    (1, 6): "CI and Test Infrastructure",
    (2, 1): "Workflow Execution Core",
    (2, 2): "LLM Gateway",
    (2, 3): "Prompt and Context Assembly",
    (2, 4): "Knowledge, Memory and Retrieval",
    (2, 5): "Capability Manager and Platform SDK",
    (2, 6): "Quality Gate Engine",
    (2, 7): "Platform Services and Error Model",
    (2, 8): "Kernel HTTP Surface",
    (3, 1): "Sandboxed Tool Execution",
    (3, 2): "Software Engineering Pack Agents",
    (3, 3): "Software Engineering Pack Workflows",
    (3, 4): "Pack Tools and Declared Quality Gates",
    (3, 5): "Security and Human Approval",
    (3, 6): "Threat Controls",
    (4, 1): "Evaluation Engine",
    (4, 2): "Traceability Engine",
    (4, 3): "Benchmarking Pack",
    (5, 1): "Document Processing",
    (5, 2): "Project Intelligence Pack",
    (6, 1): "API Completion and Published Contract",
    (6, 2): "Realtime Stream",
    (6, 3): "Dashboard",
    (6, 4): "Command Line Interface",
    (6, 5): "Notifications",
    (6, 6): "Voice",
    (7, 1): "Deployment and Infrastructure",
    (7, 2): "Security Hardening",
    (7, 3): "Performance, Chaos and Coverage",
    (8, 1): "Remaining Pack Agents",
    (8, 2): "Remaining Pack Workflows",
    (9, 1): "Roadmap System Restructuring (R1-R4)",
}

# Module number -> name. Frozen: these are feature_inventory.md §5's own
# numbers. M35 (Analytics Pack) is retired, not reused.
MODULES: dict[int, str] = {
    1: "Configuration Manager",
    2: "Manifest Loader (+ Schema)",
    3: "Health & Lifecycle",
    4: "Observability & Audit",
    5: "Workflow Engine",
    6: "LLM Gateway",
    7: "Prompt Engine",
    8: "Context Manager",
    9: "Knowledge Manager",
    10: "Memory Manager",
    11: "Retrieval / Search & Vector Search",
    12: "Evaluation Engine",
    13: "Capability Manager",
    14: "Security Manager",
    15: "Quality Gate Engine",
    16: "Traceability Engine",
    17: "Event Bus",
    18: "Tool Invoker (SDK interface)",
    19: "Secrets Manager",
    20: "Sandbox / SandboxExecutor",
    21: "Storage Service",
    22: "Notification Service",
    23: "Caching (Redis)",
    24: "Git Integration Service",
    25: "Speech Gateway",
    26: "Document Processing",
    27: "Platform SDK (ai-os-sdk package)",
    28: "Manifest Schema (JSON Schema)",
    29: "SE Pack - Agents",
    30: "SE Pack - Workflows",
    31: "SE Pack - Tools & Quality Gates",
    32: "Project Intelligence Pack",
    33: "Voice (Jarvis) Pack",
    34: "Benchmarking Pack",
    36: "API (HTTP surface)",
    37: "WebSocket stream",
    38: "CLI (aios)",
    39: "Dashboard",
    40: "Deployment & Infrastructure",
    41: "Threat Controls (T1-T12)",
    42: "Testing Infrastructure",
    43: "CI Pipeline",
    44: "Platform-wide AiOsError hierarchy",
    # M45 appended 2026-07-31 (R4). Existing module numbers are frozen;
    # *appending* a new one is how a genuinely new module is added. This
    # is the ticket system, generator, and process rules themselves —
    # none of M01-M44 covers them, and filing them under Testing
    # Infrastructure or CI Pipeline would have been wrong.
    45: "Roadmap & Process System",
}


# Module number -> the repository path that module's work lives in.
#
# Added 2026-07-31 from the R3 pilot's own finding: a ticket named no
# path, so the working session had to derive the location from the
# module *number* via this file. That worked only because the mapping
# was already known — a genuine gap for a session without it. Every
# ticket now carries `module_path:` populated from here.
#
# Paths marked PLANNED do not exist on disk yet (git does not track
# empty directories — see docs/process/folder_structure.md). They are
# the agreed location, so the Task that fills one creates it there
# rather than inventing a second convention.
MODULE_PATHS: dict[int, str] = {
    1: "kernel/src/ai_os_kernel/configuration_manager",
    2: "kernel/src/ai_os_kernel/manifest_loader",
    3: "kernel/src/ai_os_kernel/health",
    4: "kernel/src/ai_os_kernel/observability",
    5: "kernel/src/ai_os_kernel/workflow_engine",
    6: "kernel/src/ai_os_kernel/llm_gateway",
    7: "kernel/src/ai_os_kernel/prompt_engine",
    8: "kernel/src/ai_os_kernel/context_manager",
    9: "kernel/src/ai_os_kernel/knowledge_manager",
    10: "kernel/src/ai_os_kernel/memory_manager",
    11: "kernel/src/ai_os_kernel/retrieval",
    12: "kernel/src/ai_os_kernel/evaluation_engine",
    13: "kernel/src/ai_os_kernel/capability_manager",
    14: "kernel/src/ai_os_kernel/security_manager",
    15: "kernel/src/ai_os_kernel/quality_gate_engine",
    16: "kernel/src/ai_os_kernel/traceability_engine",
    17: "kernel/src/ai_os_kernel/event_bus",
    18: "platform_sdk/src/ai_os_sdk/contracts",
    19: "kernel/src/ai_os_kernel/secrets_manager",
    20: "kernel/src/ai_os_kernel/sandbox",
    21: "kernel/src/ai_os_kernel/storage_service",  # PLANNED
    # 22/24/25 corrected 2026-08-11 (full-project audit): these pointed at
    # `platform_services/<name>`, a directory that has never existed in this
    # repository. Every one of these three subsystems was in fact built
    # inside the Kernel. The generator validates ticket module_path against
    # this registry, but not this registry against the filesystem, so the
    # mismatch passed CI silently. Their tickets were corrected in the same
    # step.
    22: "kernel/src/ai_os_kernel/notification",
    23: "kernel/src/ai_os_kernel/caching",  # PLANNED
    24: "kernel/src/ai_os_kernel/git_integration",
    25: "kernel/src/ai_os_kernel/speech_gateway",
    26: "kernel/src/ai_os_kernel/document_processing",  # PLANNED
    27: "platform_sdk/src/ai_os_sdk",
    28: "platform_sdk/schemas",
    29: "capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents",
    30: "capability_packs/software-engineering/workflows",
    31: "capability_packs/software-engineering/src/ai_os_pack_software_engineering",
    32: "capability_packs/project_intelligence",  # PLANNED
    # 33 corrected 2026-08-11 (full-project audit): `capability_packs/
    # voice_jarvis` does not exist and deliberately never will — that pack
    # was attempted and rejected the same day (`P06-S06-M33-T01`) because a
    # pure HTTP-client pack violates the real pack_contract_suite
    # import-boundary check. The real Platform Integration Layer lives in
    # the Kernel. See docs/process/folder_structure.md's capability_packs row.
    33: "kernel/src/ai_os_kernel/voice_jarvis",
    34: "capability_packs/benchmarking",  # PLANNED
    36: "kernel/src/ai_os_kernel/routes",
    37: "kernel/src/ai_os_kernel/routes",
    38: "tools/aios",  # PLANNED
    39: "dashboard",  # PLANNED
    40: "infra",
    41: "tests/security",  # PLANNED
    42: "tests",
    43: ".github/workflows",
    44: "platform_sdk/src/ai_os_sdk/errors",
    45: "scripts/roadmap",
}


def phase_label(phase: int) -> str:
    letter, title = PHASES[phase]
    return f"P{phase:02d} (Stage {letter}) - {title}"


def stage_title(phase: int, stage: int) -> str:
    return STAGES.get((phase, stage), "UNNAMED STAGE")
