<!-- GENERATED FILE - DO NOT EDIT BY HAND.
     Source of truth: docs/19_roadmap/tickets/**.md
     Regenerate:      python -m scripts.roadmap.generate
     Verified by:     tests/roadmap/test_generated_docs_are_current.py
     Hand edits are overwritten and fail CI. -->

# AI_OS - Roadmap Status

**Generated:** 2026-08-04 from 238 Task tickets.

This file is a rollup. **A normal development step must not read it** (`docs/process/standing_rules.md`): read only your own Task ticket and its direct dependencies.

**Overall: 65%** (154.5 of 238 Task-equivalents complete)

| Phase | Stage | Tasks | Done | Partial | Todo | % |
|---|---|---:|---:|---:|---:|---:|
| P01 (A) | S01 Process, Packaging and Persistence Baseline | 5 | 5 | 0 | 0 | 100% |
| P01 (A) | S02 Configuration and Secrets | 14 | 13 | 0 | 1 | 93% |
| P01 (A) | S03 Manifest Discovery and Schema | 6 | 5 | 0 | 1 | 83% |
| P01 (A) | S04 Health and Lifecycle | 6 | 6 | 0 | 0 | 100% |
| P01 (A) | S05 Observability and Audit | 6 | 6 | 0 | 0 | 100% |
| P01 (A) | S06 CI and Test Infrastructure | 10 | 10 | 0 | 0 | 100% |
| P02 (B) | S01 Workflow Execution Core | 15 | 15 | 0 | 0 | 100% |
| P02 (B) | S02 LLM Gateway | 12 | 10 | 1 | 1 | 88% |
| P02 (B) | S03 Prompt and Context Assembly | 16 | 8 | 0 | 8 | 50% |
| P02 (B) | S04 Knowledge, Memory and Retrieval | 14 | 4 | 0 | 10 | 29% |
| P02 (B) | S05 Capability Manager and Platform SDK | 19 | 19 | 0 | 0 | 100% |
| P02 (B) | S06 Quality Gate Engine | 8 | 4 | 0 | 4 | 50% |
| P02 (B) | S07 Platform Services and Error Model | 7 | 7 | 0 | 0 | 100% |
| P02 (B) | S08 Kernel HTTP Surface | 4 | 4 | 0 | 0 | 100% |
| P03 (C) | S01 Sandboxed Tool Execution | 8 | 7 | 0 | 1 | 88% |
| P03 (C) | S02 Software Engineering Pack Agents | 8 | 6 | 0 | 2 | 75% |
| P03 (C) | S03 Software Engineering Pack Workflows | 6 | 4 | 0 | 2 | 67% |
| P03 (C) | S04 Pack Tools and Declared Quality Gates | 4 | 2 | 0 | 2 | 50% |
| P03 (C) | S05 Security and Human Approval | 10 | 10 | 0 | 0 | 100% |
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
| P01 (Stage A) - Platform Skeleton | 47 | 45 | 96% |
| P02 (Stage B) - Minimum Viable Kernel | 95 | 71 | 75% |
| P03 (Stage C) - First Real Capability Pack | 38 | 30 | 79% |
| P04 (Stage D) - Evaluation and Multi-LLM Experimentation | 15 | 3 | 20% |
| P05 (Stage E) - Project Intelligence | 8 | 0 | 0% |
| P06 (Stage F) - Dashboard, Voice, Notifications | 13 | 0 | 0% |
| P07 (Stage G) - Hardening and Production Readiness | 8 | 0 | 0% |
| P08 (Stage H) - Expansion | 9 | 0 | 0% |
| P09 (Stage -) - Roadmap System and Process | 5 | 5 | 100% |

## Ready to start

40 Task(s) whose dependencies are all satisfied (Definition of Ready, `docs/process/ticket_templates.md`):

- `P02-S03-M07-T05` Composition and inheritance
- `P02-S03-M07-T06` Cache boundary index
- `P02-S03-M08-T07` AI-context-pack resolver
- `P02-S03-M08-T08` Runtime-config resolver
- `P02-S03-M08-T09` Filter and ranker
- `P02-S03-M08-T10` Persisted context audit logger
- `P02-S04-M09-T03` Indexing component
- `P02-S04-M09-T05` Provenance and versioning
- `P02-S04-M10-T01` Memory store
- `P02-S04-M11-T03` Embedding writer
- `P02-S06-M15-T05` Gate Registry
- `P03-S01-M20-T05` Stronger isolation tier
- `P03-S02-M29-T07` code-reviewer agent
- `P03-S02-M29-T08` technical-planner agent
- `P03-S03-M30-T02` Structured Markdown specification input
- `P03-S04-M31-T02` Manifest-declared file and build tools
- `P03-S06-M41-T02` Remaining T2-T12 controls
- `P04-S01-M12-T04` Metrics collector
- `P04-S01-M12-T05` Run manifest recorder
- `P04-S02-M16-T01` trace.links writer
- `P04-S03-M34-T01` Experiment definition with pinned conditions
- `P05-S01-M26-T01` Parser adapters
- `P06-S01-M36-T01` Published OpenAPI contract artifact
- `P06-S01-M36-T02` RFC 9457 error shape
- `P06-S01-M36-T03` Idempotency-Key support
- ... and 15 more

## Dependency review signal

0 `todo` Task(s) record no dependency although an earlier Task in the same module is unfinished. **Advisory only** — some Tasks genuinely start from nothing. Review when touching that module.

