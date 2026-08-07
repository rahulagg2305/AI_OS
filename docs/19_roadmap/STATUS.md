<!-- GENERATED FILE - DO NOT EDIT BY HAND.
     Source of truth: docs/19_roadmap/tickets/**.md
     Regenerate:      python -m scripts.roadmap.generate
     Verified by:     tests/roadmap/test_generated_docs_are_current.py
     Hand edits are overwritten and fail CI. -->

# AI_OS - Roadmap Status

**Generated:** 2026-08-07 from 246 Task tickets.

This file is a rollup. **A normal development step must not read it** (`docs/process/standing_rules.md`): read only your own Task ticket and its direct dependencies.

**Overall: 80%** (198 of 246 Task-equivalents complete)

| Phase | Stage | Tasks | Done | Partial | Todo | % |
|---|---|---:|---:|---:|---:|---:|
| P01 (A) | S01 Process, Packaging and Persistence Baseline | 5 | 5 | 0 | 0 | 100% |
| P01 (A) | S02 Configuration and Secrets | 14 | 13 | 0 | 1 | 93% |
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
| P03 (C) | S01 Sandboxed Tool Execution | 8 | 7 | 0 | 1 | 88% |
| P03 (C) | S02 Software Engineering Pack Agents | 8 | 7 | 0 | 1 | 88% |
| P03 (C) | S03 Software Engineering Pack Workflows | 6 | 6 | 0 | 0 | 100% |
| P03 (C) | S04 Pack Tools and Declared Quality Gates | 4 | 4 | 0 | 0 | 100% |
| P03 (C) | S05 Security and Human Approval | 10 | 10 | 0 | 0 | 100% |
| P03 (C) | S06 Threat Controls | 2 | 2 | 0 | 0 | 100% |
| P04 (D) | S01 Evaluation Engine | 11 | 7 | 0 | 4 | 64% |
| P04 (D) | S02 Traceability Engine | 3 | 0 | 0 | 3 | 0% |
| P04 (D) | S03 Benchmarking Pack | 4 | 0 | 0 | 4 | 0% |
| P05 (E) | S01 Document Processing | 2 | 0 | 0 | 2 | 0% |
| P05 (E) | S02 Project Intelligence Pack | 6 | 0 | 0 | 6 | 0% |
| P06 (F) | S01 API Completion and Published Contract | 4 | 3 | 1 | 0 | 88% |
| P06 (F) | S02 Realtime Stream | 1 | 0 | 0 | 1 | 0% |
| P06 (F) | S03 Dashboard | 3 | 0 | 0 | 3 | 0% |
| P06 (F) | S04 Command Line Interface | 1 | 0 | 0 | 1 | 0% |
| P06 (F) | S05 Notifications | 2 | 0 | 0 | 2 | 0% |
| P06 (F) | S06 Voice | 2 | 0 | 0 | 2 | 0% |
| P07 (G) | S01 Deployment and Infrastructure | 3 | 0 | 0 | 3 | 0% |
| P07 (G) | S02 Security Hardening | 3 | 0 | 0 | 3 | 0% |
| P07 (G) | S03 Performance, Chaos and Coverage | 2 | 0 | 0 | 2 | 0% |
| P08 (H) | S01 Remaining Pack Agents | 7 | 4 | 0 | 3 | 57% |
| P08 (H) | S02 Remaining Pack Workflows | 2 | 0 | 0 | 2 | 0% |
| P09 (-) | S01 Roadmap System Restructuring (R1-R4) | 5 | 5 | 0 | 0 | 100% |

## Phase totals

| Phase | Tasks | Done | % |
|---|---:|---:|---:|
| P01 (Stage A) - Platform Skeleton | 47 | 45 | 96% |
| P02 (Stage B) - Minimum Viable Kernel | 100 | 97 | 98% |
| P03 (Stage C) - First Real Capability Pack | 38 | 36 | 95% |
| P04 (Stage D) - Evaluation and Multi-LLM Experimentation | 18 | 7 | 39% |
| P05 (Stage E) - Project Intelligence | 8 | 0 | 0% |
| P06 (Stage F) - Dashboard, Voice, Notifications | 13 | 3 | 27% |
| P07 (Stage G) - Hardening and Production Readiness | 8 | 0 | 0% |
| P08 (Stage H) - Expansion | 9 | 4 | 44% |
| P09 (Stage -) - Roadmap System and Process | 5 | 5 | 100% |

## Ready to start

18 Task(s) whose dependencies are all satisfied (Definition of Ready, `docs/process/ticket_templates.md`):

- `P03-S01-M20-T05` Stronger isolation tier
- `P03-S02-M29-T08` technical-planner agent
- `P04-S01-M12-T04` Metrics collector
- `P04-S02-M16-T01` trace.links writer
- `P04-S03-M34-T01` Experiment definition with pinned conditions
- `P05-S01-M26-T01` Parser adapters
- `P06-S02-M37-T01` WebSocket stream endpoint
- `P06-S03-M39-T01` Dashboard scaffold on the generated client
- `P06-S04-M38-T01` aios CLI
- `P06-S05-M22-T01` Notification channels
- `P06-S06-M25-T01` Speech Gateway
- `P07-S01-M40-T01` Kubernetes manifests and Helm chart
- `P07-S01-M40-T03` Backup and restore rehearsal
- `P07-S02-M14-T01` OIDC authentication
- `P07-S02-M19-T01` Vault secrets backend
- `P07-S03-M42-T01` Chaos tests
- `P08-S01-M29-T06` refactoring agent
- `P08-S01-M29-T07` performance agent

## Dependency review signal

0 `todo` Task(s) record no dependency although an earlier Task in the same module is unfinished. **Advisory only** — some Tasks genuinely start from nothing. Review when touching that module.

