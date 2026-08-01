<!-- GENERATED FILE - DO NOT EDIT BY HAND.
     Source of truth: docs/19_roadmap/tickets/**.md
     Regenerate:      python -m scripts.roadmap.generate
     Verified by:     tests/roadmap/test_generated_docs_are_current.py
     Hand edits are overwritten and fail CI. -->

# AI_OS - Roadmap Status

**Generated:** 2026-08-01 from 224 Task tickets.

This file is a rollup. **A normal development step must not read it** (`docs/process/standing_rules.md`): read only your own Task ticket and its direct dependencies.

**Overall: 48%** (108.5 of 224 Task-equivalents complete)

| Phase | Stage | Tasks | Done | Partial | Todo | % |
|---|---|---:|---:|---:|---:|---:|
| P01 (A) | S01 Process, Packaging and Persistence Baseline | 4 | 3 | 0 | 1 | 75% |
| P01 (A) | S02 Configuration and Secrets | 14 | 12 | 0 | 2 | 86% |
| P01 (A) | S03 Manifest Discovery and Schema | 6 | 3 | 0 | 3 | 50% |
| P01 (A) | S04 Health and Lifecycle | 6 | 5 | 0 | 1 | 83% |
| P01 (A) | S05 Observability and Audit | 6 | 4 | 0 | 2 | 67% |
| P01 (A) | S06 CI and Test Infrastructure | 10 | 7 | 0 | 3 | 70% |
| P02 (B) | S01 Workflow Execution Core | 13 | 8 | 0 | 5 | 62% |
| P02 (B) | S02 LLM Gateway | 12 | 6 | 1 | 5 | 54% |
| P02 (B) | S03 Prompt and Context Assembly | 16 | 8 | 0 | 8 | 50% |
| P02 (B) | S04 Knowledge, Memory and Retrieval | 14 | 4 | 0 | 10 | 29% |
| P02 (B) | S05 Capability Manager and Platform SDK | 19 | 16 | 0 | 3 | 84% |
| P02 (B) | S06 Quality Gate Engine | 8 | 4 | 0 | 4 | 50% |
| P02 (B) | S07 Platform Services and Error Model | 7 | 1 | 0 | 6 | 14% |
| P02 (B) | S08 Kernel HTTP Surface | 4 | 4 | 0 | 0 | 100% |
| P03 (C) | S01 Sandboxed Tool Execution | 6 | 4 | 0 | 2 | 67% |
| P03 (C) | S02 Software Engineering Pack Agents | 8 | 6 | 0 | 2 | 75% |
| P03 (C) | S03 Software Engineering Pack Workflows | 3 | 1 | 0 | 2 | 33% |
| P03 (C) | S04 Pack Tools and Declared Quality Gates | 3 | 1 | 0 | 2 | 33% |
| P03 (C) | S05 Security and Human Approval | 5 | 2 | 0 | 3 | 40% |
| P03 (C) | S06 Threat Controls | 2 | 1 | 0 | 1 | 50% |
| P04 (D) | S01 Evaluation Engine | 8 | 3 | 0 | 5 | 38% |
| P04 (D) | S02 Traceability Engine | 3 | 0 | 0 | 3 | 0% |
| P04 (D) | S03 Benchmarking Pack | 4 | 0 | 0 | 4 | 0% |
| P05 (E) | S01 Document Processing | 2 | 0 | 0 | 2 | 0% |
| P05 (E) | S02 Project Intelligence Pack | 6 | 0 | 0 | 6 | 0% |
| P06 (F) | S01 API Completion and Published Contract | 4 | 0 | 0 | 4 | 0% |
| P06 (F) | S02 Realtime Stream | 1 | 0 | 0 | 1 | 0% |
| P06 (F) | S03 Dashboard | 3 | 0 | 0 | 3 | 0% |
| P06 (F) | S04 Command Line Interface | 1 | 0 | 0 | 1 | 0% |
| P06 (F) | S05 Notifications | 2 | 0 | 0 | 2 | 0% |
| P06 (F) | S06 Voice | 2 | 0 | 0 | 2 | 0% |
| P07 (G) | S01 Deployment and Infrastructure | 3 | 0 | 0 | 3 | 0% |
| P07 (G) | S02 Security Hardening | 3 | 0 | 0 | 3 | 0% |
| P07 (G) | S03 Performance, Chaos and Coverage | 2 | 0 | 0 | 2 | 0% |
| P08 (H) | S01 Remaining Pack Agents | 7 | 0 | 0 | 7 | 0% |
| P08 (H) | S02 Remaining Pack Workflows | 2 | 0 | 0 | 2 | 0% |
| P09 (-) | S01 Roadmap System Restructuring (R1-R4) | 5 | 5 | 0 | 0 | 100% |

## Phase totals

| Phase | Tasks | Done | % |
|---|---:|---:|---:|
| P01 (Stage A) - Platform Skeleton | 46 | 34 | 74% |
| P02 (Stage B) - Minimum Viable Kernel | 93 | 51 | 55% |
| P03 (Stage C) - First Real Capability Pack | 27 | 15 | 56% |
| P04 (Stage D) - Evaluation and Multi-LLM Experimentation | 15 | 3 | 20% |
| P05 (Stage E) - Project Intelligence | 8 | 0 | 0% |
| P06 (Stage F) - Dashboard, Voice, Notifications | 13 | 0 | 0% |
| P07 (Stage G) - Hardening and Production Readiness | 8 | 0 | 0% |
| P08 (Stage H) - Expansion | 9 | 0 | 0% |
| P09 (Stage -) - Roadmap System and Process | 5 | 5 | 100% |

## Ready to start

58 Task(s) whose dependencies are all satisfied (Definition of Ready, `docs/process/ticket_templates.md`):

- `P01-S01-M40-T04` Runtime container image
- `P01-S02-M19-T06` Prompt-assembly secret leak scan
- `P01-S03-M02-T03` Entry-point discovery
- `P01-S03-M02-T04` Remaining semantic manifest rules
- `P01-S04-M03-T06` Graceful-shutdown coordinator
- `P01-S05-M04-T03` OTLP export to a Collector
- `P01-S06-M42-T04` tests/security by threat id
- `P01-S06-M42-T05` tests/performance against NFR targets
- `P01-S06-M43-T04` Green integration stage on Linux
- `P02-S01-M05-T09` decision step type
- `P02-S01-M05-T10` parallel step type
- `P02-S01-M05-T11` sub_workflow step type
- `P02-S01-M05-T12` Multi-instance worker loop
- `P02-S01-M05-T13` Scheduler for delayed workflow starts
- `P02-S02-M06-T08` Streaming completions
- `P02-S02-M06-T09` Embeddings
- `P02-S02-M06-T10` Provider token counting
- `P02-S02-M06-T11` Rate limiter
- `P02-S03-M07-T05` Composition and inheritance
- `P02-S03-M07-T06` Cache boundary index
- `P02-S03-M08-T07` AI-context-pack resolver
- `P02-S03-M08-T08` Runtime-config resolver
- `P02-S03-M08-T09` Filter and ranker
- `P02-S03-M08-T10` Persisted context audit logger
- `P02-S04-M09-T03` Indexing component
- ... and 33 more

## Dependency review signal

1 `todo` Task(s) record no dependency although an earlier Task in the same module is unfinished. **Advisory only** — some Tasks genuinely start from nothing. Review when touching that module.

- `P01-S06-M42-T05` tests/performance against NFR targets
