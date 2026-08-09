<!-- GENERATED FILE - DO NOT EDIT BY HAND.
     Source of truth: docs/19_roadmap/tickets/**.md
     Regenerate:      python -m scripts.roadmap.generate
     Verified by:     tests/roadmap/test_generated_docs_are_current.py
     Hand edits are overwritten and fail CI. -->

# AI_OS - Roadmap Status

**Generated:** 2026-08-09 from 246 Task tickets.

This file is a rollup. **A normal development step must not read it** (`docs/process/standing_rules.md`): read only your own Task ticket and its direct dependencies.

**Overall: 92%** (226 of 246 Task-equivalents complete)

| Phase | Stage | Tasks | Done | Partial | Todo | % |
|---|---|---:|---:|---:|---:|---:|
| P01 (A) | S01 Process, Packaging and Persistence Baseline | 5 | 5 | 0 | 0 | 100% |
| P01 (A) | S02 Configuration and Secrets | 14 | 14 | 0 | 0 | 100% |
| P01 (A) | S03 Manifest Discovery and Schema | 6 | 5 | 0 | 1 | 83% |
| P01 (A) | S04 Health and Lifecycle | 6 | 6 | 0 | 0 | 100% |
| P01 (A) | S05 Observability and Audit | 6 | 6 | 0 | 0 | 100% |
| P01 (A) | S06 CI and Test Infrastructure | 10 | 10 | 0 | 0 | 100% |
| P02 (B) | S01 Workflow Execution Core | 15 | 15 | 0 | 0 | 100% |
| P02 (B) | S02 LLM Gateway | 12 | 11 | 1 | 0 | 96% |
| P02 (B) | S03 Prompt and Context Assembly | 20 | 19 | 0 | 1 | 95% |
| P02 (B) | S04 Knowledge, Memory and Retrieval | 14 | 13 | 0 | 1 | 93% |
| P02 (B) | S05 Capability Manager and Platform SDK | 19 | 19 | 0 | 0 | 100% |
| P02 (B) | S06 Quality Gate Engine | 9 | 9 | 0 | 0 | 100% |
| P02 (B) | S07 Platform Services and Error Model | 7 | 7 | 0 | 0 | 100% |
| P02 (B) | S08 Kernel HTTP Surface | 4 | 4 | 0 | 0 | 100% |
| P03 (C) | S01 Sandboxed Tool Execution | 8 | 7 | 1 | 0 | 94% |
| P03 (C) | S02 Software Engineering Pack Agents | 8 | 8 | 0 | 0 | 100% |
| P03 (C) | S03 Software Engineering Pack Workflows | 6 | 6 | 0 | 0 | 100% |
| P03 (C) | S04 Pack Tools and Declared Quality Gates | 4 | 4 | 0 | 0 | 100% |
| P03 (C) | S05 Security and Human Approval | 10 | 10 | 0 | 0 | 100% |
| P03 (C) | S06 Threat Controls | 2 | 2 | 0 | 0 | 100% |
| P04 (D) | S01 Evaluation Engine | 11 | 11 | 0 | 0 | 100% |
| P04 (D) | S02 Traceability Engine | 3 | 3 | 0 | 0 | 100% |
| P04 (D) | S03 Benchmarking Pack | 4 | 3 | 1 | 0 | 88% |
| P05 (E) | S01 Document Processing | 2 | 0 | 2 | 0 | 50% |
| P05 (E) | S02 Project Intelligence Pack | 6 | 0 | 3 | 3 | 25% |
| P06 (F) | S01 API Completion and Published Contract | 4 | 3 | 1 | 0 | 88% |
| P06 (F) | S02 Realtime Stream | 1 | 1 | 0 | 0 | 100% |
| P06 (F) | S03 Dashboard | 3 | 1 | 1 | 1 | 50% |
| P06 (F) | S04 Command Line Interface | 1 | 0 | 0 | 1 | 0% |
| P06 (F) | S05 Notifications | 2 | 0 | 2 | 0 | 50% |
| P06 (F) | S06 Voice | 2 | 0 | 0 | 2 | 0% |
| P07 (G) | S01 Deployment and Infrastructure | 3 | 1 | 2 | 0 | 67% |
| P07 (G) | S02 Security Hardening | 3 | 3 | 0 | 0 | 100% |
| P07 (G) | S03 Performance, Chaos and Coverage | 2 | 0 | 1 | 1 | 25% |
| P08 (H) | S01 Remaining Pack Agents | 7 | 6 | 0 | 1 | 86% |
| P08 (H) | S02 Remaining Pack Workflows | 2 | 1 | 1 | 0 | 75% |
| P09 (-) | S01 Roadmap System Restructuring (R1-R4) | 5 | 5 | 0 | 0 | 100% |

## Phase totals

| Phase | Tasks | Done | % |
|---|---:|---:|---:|
| P01 (Stage A) - Platform Skeleton | 47 | 46 | 98% |
| P02 (Stage B) - Minimum Viable Kernel | 100 | 97 | 98% |
| P03 (Stage C) - First Real Capability Pack | 38 | 37 | 99% |
| P04 (Stage D) - Evaluation and Multi-LLM Experimentation | 18 | 17 | 97% |
| P05 (Stage E) - Project Intelligence | 8 | 0 | 31% |
| P06 (Stage F) - Dashboard, Voice, Notifications | 13 | 5 | 54% |
| P07 (Stage G) - Hardening and Production Readiness | 8 | 4 | 69% |
| P08 (Stage H) - Expansion | 9 | 7 | 83% |
| P09 (Stage -) - Roadmap System and Process | 5 | 5 | 100% |

## Ready to start

7 Task(s) whose dependencies are all satisfied (Definition of Ready, `docs/process/ticket_templates.md`):

- `P05-S02-M32-T04` Architecture recovery
- `P05-S02-M32-T06` Untrusted provenance end to end
- `P06-S03-M39-T03` Cost and quality views
- `P06-S04-M38-T01` aios CLI
- `P06-S06-M25-T01` Speech Gateway
- `P07-S03-M42-T02` Cost anomaly alerting
- `P08-S01-M29-T07` performance agent

## Dependency review signal

0 `todo` Task(s) record no dependency although an earlier Task in the same module is unfinished. **Advisory only** — some Tasks genuinely start from nothing. Review when touching that module.

