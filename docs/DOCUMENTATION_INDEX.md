# AI_OS – Overall Documentation Index

**Project:** AI_OS (AI Operating System)
**Document:** Overall Documentation Index
**Version:** 2.0
**Status:** Approved
**Last Updated:** 2026-07-25

---

## 1. Purpose

Master index of all AI_OS documentation, so any human or LLM can find the authoritative document for a topic without relying on chat history.

Every entry shows its **status**, because a reader needs to know whether a document carries authority. Per Constitution Article 9, only *Approved* architecture documents govern; `Accepted` is the equivalent state for an ADR.

---

## 2. How to Use This Index

1. Start with `../README.md` and `../PROJECT_INDEX.md` for orientation.
2. Read the Constitution and the AI Governance Framework.
3. **Read the Decision Log** (`18_decision_log/README.md`) — it records every technology and architecture decision, and is the fastest route to understanding why the platform is shaped as it is.
4. Use this index to find the detailed document you need.
5. On conflict, follow the precedence rules in the Project Constitution.

---

## 3. Governance and Foundation

| Document | Path | Status |
|---|---|---|
| README | `../README.md` | Approved |
| PROJECT_INDEX | `../PROJECT_INDEX.md` | Approved |
| Project Constitution | `00_constitution/project_constitution.md` | Immutable |
| AI Governance Framework | `00_constitution/ai_governance_framework.md` | Active |
| Coding Standards & Best Practices | `21_templates/CODING_STANDARDS_AND_BEST_PRACTICES.md` | Mandatory |
| **Glossary** | `20_glossary/glossary.md` | Approved |
| ADR Process & Templates | `18_decision_log/adr/adr_process_and_templates.md` | Approved |
| **Decision Log Index (all 25 ADRs)** | `18_decision_log/README.md` | Active |

## 4. Requirements

| Document | Path | Status |
|---|---|---|
| **Functional Requirements** | `02_requirements/functional/functional_requirements.md` | Approved |
| **Non-Functional Requirements** | `02_requirements/non_functional/nfr.md` | Approved |
| **Constraints and Assumptions** | `02_requirements/constraints/constraints.md` | Approved |

## 5. Platform Architecture

| Document | Path | Status |
|---|---|---|
| System Architecture | `03_architecture/platform/system_architecture.md` | Approved (v2.0) |
| **Technology Stack** | `03_architecture/platform/technology_stack.md` | Approved |
| **Platform SDK Specification** | `03_architecture/platform/platform_sdk.md` | Approved |
| Kernel Architecture | `03_architecture/kernel/kernel_architecture.md` | Approved (v2.0) |
| Capability Pack Contract | `03_architecture/capability_framework/capability_pack_contract.md` | Approved |
| Manifest Schema | `03_architecture/capability_framework/manifest_schema.md` | Approved (v2.0) |
| **Manifest JSON Schema (machine-readable, authoritative)** | `../platform_sdk/schemas/manifest.schema.json` | Approved |

## 6. Kernel Subsystems

| Document | Path | Status |
|---|---|---|
| Workflow Engine | `03_architecture/kernel/workflow_engine.md` | Approved (v2.0) |
| LLM Gateway | `03_architecture/kernel/llm_gateway.md` | Approved (v2.0) |
| Prompt Engine | `03_architecture/kernel/prompt_engine.md` | Approved |
| Context Manager | `03_architecture/kernel/context_manager.md` | Approved |
| Knowledge Manager | `03_architecture/kernel/knowledge_manager.md` | Approved |
| Memory Manager | `03_architecture/kernel/memory_manager.md` | Approved |
| Evaluation Engine | `03_architecture/kernel/evaluation_engine.md` | Approved |
| Configuration Manager | `03_architecture/kernel/configuration_manager.md` | Approved |
| Manifest Loader | `03_architecture/kernel/manifest_loader.md` | Approved |
| Capability Manager | `03_architecture/kernel/capability_manager.md` | Approved |
| Security Manager | `03_architecture/kernel/security_manager.md` | Approved |
| Quality Gate Engine | `03_architecture/kernel/quality_gate_engine.md` | Approved |
| Traceability Engine | `03_architecture/kernel/traceability_engine.md` | Approved |
| Event Bus | `03_architecture/kernel/event_bus.md` | Approved |
| Logging, Audit & Observability | `03_architecture/kernel/observability.md` | Approved |
| Health & Lifecycle | `03_architecture/kernel/health_lifecycle.md` | Approved |

## 7. Agents and Workflows

| Document | Path | Status |
|---|---|---|
| Agent Architecture & Contract | `03_architecture/agents/agent_architecture.md` | Approved |
| Agent Catalog | `05_agents/agent_catalog.md` | Approved |
| **Agent Specifications** | `05_agents/agent_specifications.md` | Approved |
| Agent Communication & Coordination | `03_architecture/agents/agent_communication.md` | Approved |
| Workflow Architecture | `03_architecture/workflow/workflow_architecture.md` | Approved |
| Standard Workflow Patterns | `03_architecture/workflow/workflow_patterns.md` | Approved |
| State Management | `03_architecture/workflow/state_management.md` | Approved |
| Error Handling & Retry | `03_architecture/workflow/error_handling_retry.md` | Approved |
| Human Approval Points | `03_architecture/governance/human_approval_points.md` | Approved |
| Quality Gates Framework | `03_architecture/quality/quality_gates_framework.md` | Approved |

## 8. Capability Packs

| Document | Path | Status |
|---|---|---|
| Capability Pack Development Guide | `06_capability_packs/capability_pack_development_guide.md` | Approved |
| Software Engineering – Overview | `06_capability_packs/software_engineering/overview.md` | Approved |
| Software Engineering – Agents | `06_capability_packs/software_engineering/agents.md` | Approved |
| **Software Engineering – Workflows** | `06_capability_packs/software_engineering/workflows.md` | Approved |
| Software Engineering – Tools & Quality Gates | `06_capability_packs/software_engineering/tools_quality_gates.md` | Approved |
| Project Intelligence – Overview | `06_capability_packs/project_intelligence/overview.md` | Approved |
| Project Intelligence – Agents & Workflows | `06_capability_packs/project_intelligence/agents_workflows.md` | Approved |
| Voice (Jarvis) – High-level Design | `06_capability_packs/voice_jarvis/overview.md` | Approved |
| Benchmarking – High-level Design | `06_capability_packs/benchmarking/overview.md` | Approved |

## 9. Platform Services and Data

| Document | Path | Status |
|---|---|---|
| Storage Service | `03_architecture/services/storage_service.md` | Approved |
| Search & Vector Search | `03_architecture/services/search_vector_search.md` | Approved |
| Document Processing | `03_architecture/services/document_processing.md` | Approved |
| Notification Service | `03_architecture/services/notification_service.md` | Approved |
| Caching Strategy | `03_architecture/services/caching_strategy.md` | Approved |
| Git Integration Service | `03_architecture/services/git_integration.md` | Approved |
| Configuration Management (reference) | `03_architecture/services/configuration_management.md` | Approved |
| **Data Model** | `08_database/data_model.md` | Approved |

## 10. Security

| Document | Path | Status |
|---|---|---|
| **Security Architecture (threat model)** | `09_security/security_architecture.md` | Approved |
| Authentication & Authorization | `09_security/authentication_authorization.md` | Approved |
| Secrets Management | `09_security/secrets_management.md` | Approved |

## 11. APIs and Interfaces

| Document | Path | Status |
|---|---|---|
| **API Architecture** | `07_api/api_architecture.md` | Approved |
| CLI Design | `07_api/cli_design.md` | Approved |
| Dashboard Architecture | `13_dashboard/dashboard_architecture.md` | Approved |
| Dashboard Information Architecture | `13_dashboard/information_architecture.md` | Approved |
| Monitoring & Experiment Views | `13_dashboard/monitoring_experiment_views.md` | Approved |
| Voice (Jarvis) System Architecture | `14_voice_jarvis/voice_architecture.md` | Approved |
| Voice Configuration | `14_voice_jarvis/voice_configuration.md` | Approved |
| Intent Engine | `14_voice_jarvis/intent_engine.md` | Approved |
| Multi-modal Interaction | `14_voice_jarvis/multimodal_interaction.md` | Approved |

## 12. Quality, Observability, Operations

| Document | Path | Status |
|---|---|---|
| **Test Strategy** | `10_testing/test_strategy.md` | Approved |
| Observability Stack | `16_observability/observability_stack.md` | Approved |
| **Deployment Architecture** | `11_deployment/deployment_architecture.md` | Approved |
| **Operations Runbook** | `12_operations/operations_runbook.md` | Approved |

## 13. Knowledge and Traceability

| Document | Path | Status |
|---|---|---|
| AI Context Pack Strategy | `ai_context/ai_context_strategy.md` | Approved |
| AI Context Pack Structure | `ai_context/context_pack_structure.md` | Approved |
| Knowledge Base Structure & Governance | `knowledge/knowledge_base_structure.md` | Approved |
| Traceability Model | `03_architecture/traceability/traceability_model.md` | Approved |

## 14. Roadmap

| Document | Path | Status |
|---|---|---|
| Implementation Roadmap | `19_roadmap/implementation_roadmap.md` | Approved (v2.0) |
| **Implementation Status (living, short)** | `19_roadmap/implementation_status.md` | Active |
| **Implementation History Index (detailed, split by milestone)** | `19_roadmap/history/INDEX.md` | Active |
| Phase 0 Completion Review | `19_roadmap/phase_0_completion_review.md` | Approved |
| Documentation Baseline Record | `19_roadmap/documentation_freeze.md` | Approved (v2.0) |

## 15. Process Docs (Claude Code / Contributor Workflow)

| Document | Path | Status |
|---|---|---|
| **CLAUDE.md (auto-read every session)** | `../CLAUDE.md` | Active |
| Files to Read First | `process/files_to_read_first.md` | Active |
| Standing Rules (scope, docs, git discipline) | `process/standing_rules.md` | Active |
| Reporting Format | `process/reporting_format.md` | Active |
| Coding Standards (curated pointer) | `process/coding_standards.md` | Active |
| Folder Structure (real vs. placeholder) | `process/folder_structure.md` | Active |

---

## 16. Reading Order for a New Contributor or Model

1. `../README.md` → `../PROJECT_INDEX.md`
2. `00_constitution/project_constitution.md`
3. `00_constitution/ai_governance_framework.md`
4. `20_glossary/glossary.md` — the vocabulary is precise and several terms are easy to conflate
5. `18_decision_log/README.md` — all 25 ADRs, plus the open decision points
6. `03_architecture/platform/system_architecture.md`
7. `03_architecture/platform/technology_stack.md`
8. `03_architecture/platform/platform_sdk.md` — the boundary everything else respects
9. `02_requirements/functional/functional_requirements.md`
10. `02_requirements/non_functional/nfr.md`
11. The subsystem documents relevant to your task
12. `19_roadmap/implementation_roadmap.md` — what is being built now

---

## 17. Maintenance

Update this index whenever a document is added, moved, renamed, or changes status. A document not listed here is not discoverable, which for this project is equivalent to not existing.

---

## 18. Final Authority

This index is a navigation aid. On conflict, the individual authoritative documents, the Architecture Decision Records, and the Project Constitution prevail.
