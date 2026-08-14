<!-- GENERATED FILE - DO NOT EDIT BY HAND.
     Source of truth: docs/19_roadmap/tickets/**.md
                      + docs/19_roadmap/feature_inventory.md (module %)
     Regenerate:      python -m scripts.roadmap.generate
     Verified by:     tests/roadmap/test_generated_docs_are_current.py
     Hand edits are overwritten and fail CI. -->

# AI_OS - Roadmap Status

**Generated:** 2026-08-14 from 282 Task tickets.

This file is a rollup. **A normal development step must not read it** (`docs/process/standing_rules.md`): read only your own Task ticket and its direct dependencies.

**Ticket-weighted completion: 94%** (265 of 282 Task-equivalents complete) — the share of *currently ticketed* work that is done. A `partial` Task counts half. This number moves very little late in a project: each newly discovered Task adds to the denominator as well as, eventually, the numerator.

**Module-average completion: 62%** (2706 points across 44 modules, unweighted mean; 1694 points remain to 100%) — the share of the *system itself* that exists, from `feature_inventory.md`'s per-module table. A module reaches 100% only when the subsystem is genuinely complete, so this is the harder and more honest of the two.

**Neither number alone is the answer, and the gap between them is the point.** Report both, every time (`docs/process/reporting_format.md`).

| Phase | Stage | Tasks | Done | Partial | Todo | % |
|---|---|---:|---:|---:|---:|---:|
| P01 (A) | S01 Process, Packaging and Persistence Baseline | 5 | 5 | 0 | 0 | 100% |
| P01 (A) | S02 Configuration and Secrets | 14 | 14 | 0 | 0 | 100% |
| P01 (A) | S03 Manifest Discovery and Schema | 6 | 6 | 0 | 0 | 100% |
| P01 (A) | S04 Health and Lifecycle | 6 | 6 | 0 | 0 | 100% |
| P01 (A) | S05 Observability and Audit | 7 | 7 | 0 | 0 | 100% |
| P01 (A) | S06 CI and Test Infrastructure | 10 | 10 | 0 | 0 | 100% |
| P02 (B) | S01 Workflow Execution Core | 18 | 18 | 0 | 0 | 100% |
| P02 (B) | S02 LLM Gateway | 12 | 12 | 0 | 0 | 100% |
| P02 (B) | S03 Prompt and Context Assembly | 20 | 19 | 0 | 1 | 95% |
| P02 (B) | S04 Knowledge, Memory and Retrieval | 20 | 16 | 0 | 4 | 80% |
| P02 (B) | S05 Capability Manager and Platform SDK | 20 | 20 | 0 | 0 | 100% |
| P02 (B) | S06 Quality Gate Engine | 11 | 11 | 0 | 0 | 100% |
| P02 (B) | S07 Platform Services and Error Model | 13 | 10 | 0 | 3 | 77% |
| P02 (B) | S08 Kernel HTTP Surface | 4 | 4 | 0 | 0 | 100% |
| P03 (C) | S01 Sandboxed Tool Execution | 8 | 7 | 1 | 0 | 94% |
| P03 (C) | S02 Software Engineering Pack Agents | 8 | 8 | 0 | 0 | 100% |
| P03 (C) | S03 Software Engineering Pack Workflows | 6 | 6 | 0 | 0 | 100% |
| P03 (C) | S04 Pack Tools and Declared Quality Gates | 4 | 4 | 0 | 0 | 100% |
| P03 (C) | S05 Security and Human Approval | 10 | 10 | 0 | 0 | 100% |
| P03 (C) | S06 Threat Controls | 2 | 2 | 0 | 0 | 100% |
| P04 (D) | S01 Evaluation Engine | 16 | 16 | 0 | 0 | 100% |
| P04 (D) | S02 Traceability Engine | 5 | 5 | 0 | 0 | 100% |
| P04 (D) | S03 Benchmarking Pack | 5 | 5 | 0 | 0 | 100% |
| P05 (E) | S01 Document Processing | 2 | 2 | 0 | 0 | 100% |
| P05 (E) | S02 Project Intelligence Pack | 9 | 7 | 0 | 2 | 78% |
| P06 (F) | S01 API Completion and Published Contract | 6 | 4 | 1 | 1 | 75% |
| P06 (F) | S02 Realtime Stream | 1 | 1 | 0 | 0 | 100% |
| P06 (F) | S03 Dashboard | 3 | 3 | 0 | 0 | 100% |
| P06 (F) | S04 Command Line Interface | 2 | 0 | 1 | 1 | 25% |
| P06 (F) | S05 Notifications | 2 | 2 | 0 | 0 | 100% |
| P06 (F) | S06 Voice | 3 | 1 | 2 | 0 | 67% |
| P07 (G) | S01 Deployment and Infrastructure | 4 | 1 | 2 | 1 | 50% |
| P07 (G) | S02 Security Hardening | 3 | 3 | 0 | 0 | 100% |
| P07 (G) | S03 Performance, Chaos and Coverage | 3 | 2 | 1 | 0 | 83% |
| P08 (H) | S01 Remaining Pack Agents | 7 | 7 | 0 | 0 | 100% |
| P08 (H) | S02 Remaining Pack Workflows | 2 | 2 | 0 | 0 | 100% |
| P09 (-) | S01 Roadmap System Restructuring (R1-R4) | 5 | 5 | 0 | 0 | 100% |

## Phase totals

| Phase | Tasks | Done | % |
|---|---:|---:|---:|
| P01 (Stage A) - Platform Skeleton | 48 | 48 | 100% |
| P02 (Stage B) - Minimum Viable Kernel | 118 | 110 | 93% |
| P03 (Stage C) - First Real Capability Pack | 38 | 37 | 99% |
| P04 (Stage D) - Evaluation and Multi-LLM Experimentation | 26 | 26 | 100% |
| P05 (Stage E) - Project Intelligence | 11 | 9 | 82% |
| P06 (Stage F) - Dashboard, Voice, Notifications | 17 | 11 | 76% |
| P07 (Stage G) - Hardening and Production Readiness | 10 | 6 | 75% |
| P08 (Stage H) - Expansion | 9 | 9 | 100% |
| P09 (Stage -) - Roadmap System and Process | 5 | 5 | 100% |

## Ready to start

10 Task(s) whose dependencies are all satisfied (Definition of Ready, `docs/process/ticket_templates.md`):

- `P02-S04-M09-T07` A real production caller for document ingestion
- `P02-S04-M09-T08` Permission-aware knowledge retrieval
- `P02-S04-M09-T09` Knowledge Version Manager
- `P02-S07-M21-T02` ArtifactStore Protocol and a real production caller
- `P02-S07-M23-T04` Wire ResponseCache into the real LLM Gateway call path
- `P05-S02-M32-T08` Project Intelligence agent over the five real Tools
- `P05-S02-M32-T09` Multi-language dependency extraction
- `P06-S01-M36-T06` GET /gates/trends
- `P06-S04-M38-T02` aios workflow retry, and the logs command group
- `P07-S01-M40-T04` gVisor RuntimeClass in the Helm chart

## Blocked

2 Task(s) with a real blocker that is **not** a `depends_on` edge — an unresolved decision or a missing prerequisite no other Task owns (Definition of Ready item 5). Their dependencies may well all be `done`; that does not make them ready. Each ticket's own body states its blocker:

- `P02-S03-M08-T14` Wire AIContextPackResolver into a production composition
- `P02-S04-M10-T03` Promotion logic

## Dependency review signal

0 `todo` Task(s) record no dependency although an earlier Task in the same module is unfinished. **Advisory only** — some Tasks genuinely start from nothing. Review when touching that module.

