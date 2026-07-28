# Configuration Manager Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Configuration Manager Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the design of the **Configuration Manager**, a core component of the AI_OS Platform Kernel.

The Configuration Manager is the central authority for all runtime configuration in the platform. It enforces the principle of “Configuration over Code” and ensures that behaviour can be changed without modifying source code.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Coding Standards & Best Practices  

---

## 2. Design Goals

The Configuration Manager must:

- Provide a single, consistent way to access configuration
- Support multiple layers of configuration (defaults, environment, runtime overrides)
- Allow configuration to be environment-aware (local, staging, production)
- Support feature flags
- Keep secrets out of source code and out of Capability Packs
- Make configuration changes auditable
- Remain simple and reliable

---

## 3. Core Responsibilities

- Load configuration from approved sources
- Merge configuration layers in a defined order of precedence
- Provide typed and validated access to configuration values
- Support feature flags
- Integrate with secret management for sensitive values
- Expose configuration to Kernel components and (through controlled interfaces) to Capability Packs
- Record significant configuration changes for audit purposes

---

## 4. Configuration Layers (Canonical Order of Precedence)

**This is the single authoritative precedence order for AI_OS.** Layer 7 has the highest priority. `../services/configuration_management.md` is the concrete reference (file layout, env var mapping) and does not restate this order.

| # | Layer | Source |
|---|---|---|
| 1 | Built-in defaults | Code |
| 2 | Pack-level defaults | Capability Pack manifests and their `configSchema` defaults |
| 3 | Platform configuration | `config/platform.yaml` |
| 4 | Environment configuration | `infra/environments/<env>.yaml` / Kubernetes `ConfigMap` |
| 5 | Runtime overrides | `PATCH /api/v1/config`, audited |
| 6 | **Experiment overrides** | Per-run, isolated to that run |
| 7 | Secret values | Resolved at point of use from `secret://` references |

Two points that were previously ambiguous and are now settled:

- **Experiment overrides (6) beat runtime overrides (5).** An experiment must be able to pin conditions regardless of what an operator changed globally mid-run; otherwise a configuration change during an experiment would silently alter the conditions being measured ([ADR-0022](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md)).
- **Experiment overrides are isolated.** They apply only to workflows belonging to that experiment and never leak into concurrent workflows.

The resolved configuration set for every workflow run is recorded in its run manifest, so "what configuration was active for this run?" is always answerable.

Precedence is verified by property tests ([ADR-0015](../../18_decision_log/adr/ADR-0015-testing-and-ci.md)).

---

## 5. High-Level Structure

```text
Configuration Manager
│
├── Configuration Loader
├── Layer Merger
├── Schema Validator
├── Feature Flag Manager
├── Secret Resolver
├── Configuration API
└── Change Auditor
```

---

## 6. Key Design Rules

- No component should read configuration files directly; all access goes through the Configuration Manager.
- Secrets must never be stored in plain text in the repository or in Capability Packs.
- Configuration should be validated against schemas where practical.
- Experiment-specific overrides must be supported so that multi-LLM runs can control relevant settings without code changes.

---

## 7. Relationship with Other Components

- Almost every Kernel component depends on the Configuration Manager.
- **LLM Gateway** uses it for provider credentials, model mappings, budgets, and routing rules.
- **Workflow Engine** uses it for timeouts, retry policies, and feature flags.
- **Capability Packs** may declare configuration schemas and defaults, but runtime values are resolved by the Configuration Manager.
- **Evaluation / Experiment Engine** uses overrides to create controlled experimental conditions.

---

## 8. Observability & Audit

Significant configuration access and all configuration changes should be auditable.  
At minimum, the system should be able to answer: “What configuration was active during this workflow / experiment run?”

---

## 9. Current Status

This document defines the design baseline for the Configuration Manager.

Detailed schema formats, storage locations, secret backend integration, and API shapes will be refined during implementation.

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Configuration Manager Design  
6. Source Code
