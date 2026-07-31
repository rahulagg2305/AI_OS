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

## Implementation Status (2026-07-31)

**Built:** `kernel/src/ai_os_kernel/configuration_manager/` (6 modules). `ConfigurationManager` in `loader.py` resolves **4 of the 7 precedence layers** in §4 — layer 1 (built-in defaults, as field defaults on the `PlatformConfig` model in `models.py`), layer 2 (pack-level defaults: `extract_pack_defaults` reads the `default` values declared in a pack manifest's own `configSchema`, merged in via `ConfigurationManager.load`'s `pack_manifests` argument), layer 3 (`config/platform.yaml`), and layer 4 (`infra/environments/<env>.yaml`) — deep-merged in that order into one validated, frozen `PlatformConfig`. A missing file contributes nothing rather than erroring, so the layers beneath it apply. Only the `kernel:` top-level mapping of each file is read. `BootstrapEnv` in `bootstrap_env.py` is the separate, deliberately minimal `pydantic-settings` reader for the bootstrap-identity env vars that cannot themselves be file-driven (`AIOS_ENV`, `AIOS_ROLE`, database URL, and so on). `errors.py` raises `ConfigurationError` on an unknown environment, invalid YAML, a non-mapping top level, or a `PlatformConfig` validation failure. The valid-environment set (`local`, `dev`, `staging`, `production`) is a structural constant, not itself configuration. This component is constructed first in `kernel/src/ai_os_kernel/bootstrap.py`, before anything else. **Change Auditor:** `audit.py`'s `SqlConfigChangeWriter` now writes real `governance.config_changes` rows (old/new value *digests*, never the values themselves) and `verify_config_change` detects a digest tampered with directly in the database — so §8's audit question is answerable for a change recorded through this writer, though no call site yet invokes it (no runtime-override route exists to call it from). `evaluation.run_manifests` is still a table with no writer.

**Not built:** 3 of the 7 layers in §4 — layer 5 (runtime overrides via `PATCH /api/v1/config`; the route does not exist), layer 6 (experiment overrides; no experiment mechanism exists anywhere), layer 7 (`secret://` resolution at point of use; `kernel/src/ai_os_kernel/secrets_manager/` exists with an `env` backend but is **not wired into the configuration merge**). No Feature Flag Manager. No Configuration API. Discovering *which* packs are activated (Manifest Loader integration) is not wired into layer 2 either — `load`'s `pack_manifests` argument takes already-discovered manifests as plain input. The property tests §4 requires for precedence verification cover only the four implemented layers. Of §5's seven components, only Configuration Loader, Layer Merger and Schema Validator are real.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table) and `../../19_roadmap/implementation_status.md`. Detailed build history: `../../19_roadmap/history/INDEX.md` (specifically `001_project_bootstrap_and_configuration.md`).

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

This document defines the design baseline for the Configuration Manager. The four items v1.0 of this section deferred are settled as follows — none is left open as "to be refined."

| Item | Status |
|---|---|
| **Schema formats** | **Decided.** Configuration is typed and validated by Pydantic v2 / `pydantic-settings` models, not by an external schema language ([ADR-0008](../../18_decision_log/adr/ADR-0008-primary-language-and-runtime.md), [ADR-0004](../../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md)). The concrete model is `PlatformConfig` in `kernel/src/ai_os_kernel/configuration_manager/models.py`; the bootstrap-env model is `BootstrapEnv` in `bootstrap_env.py`. Pack-supplied configuration is the one exception, validated against the manifest's JSON Schema `configSchema` (`../capability_framework/manifest_schema.md`), because a pack's schema must be declarative and machine-readable to a Kernel that has never seen that pack. |
| **Storage locations** | **Decided, and already listed in §4.** `config/platform.yaml` (layer 3) and `infra/environments/<env>.yaml` (layer 4), each read from its `kernel:` top-level mapping. `../services/configuration_management.md` is the concrete file-layout and env-var-mapping reference. Only the six bootstrap-identity variables are env vars; everything else is a file value. |
| **Secret backend integration** | **Decided in [ADR-0024](../../18_decision_log/adr/ADR-0024-secrets-management-backend.md)** — `secret://<provider>/<name>[#version]` references resolved at point of use through a pluggable `SecretProvider`, with Vault as the production reference and four backends specified (env/file/vault/cloud). Real code exists in `kernel/src/ai_os_kernel/secrets_manager/` (`provider.py`, `env_provider.py`, `reference.py`, `value.py`) — `EnvSecretProvider` only. **Named remaining gap:** layer 7 is not wired into this component's merge, so a `secret://` reference appearing in `platform.yaml` today is resolved by no one; it is carried through as a literal string. Closing it needs one call site in `ConfigurationManager.load()`, not a new decision. |
| **API shapes** | **Decided at the platform level, unbuilt here.** Runtime overrides (layer 5) are `PATCH /api/v1/config` under the REST conventions in `../../07_api/api_architecture.md` ([ADR-0014](../../18_decision_log/adr/ADR-0014-api-style-and-realtime-transport.md)); the CLI surface is `aios config` (`../../07_api/cli_design.md`). **Named remaining gap:** neither the route nor the CLI exists, and neither can be built credibly before the Change Auditor exists — §4 requires runtime overrides to be audited, and `governance.config_changes` still has no writer. Order is therefore: writer, then route. |

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Configuration Manager Design  
6. Source Code

---

## 11. Related Documents

**Governing decisions (ADRs):**
- [ADR-0004 — Interface-Driven and Configuration over Code](../../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md) — the principle this component implements
- [ADR-0008 — Primary Language and Runtime](../../18_decision_log/adr/ADR-0008-primary-language-and-runtime.md) — Pydantic v2 / `pydantic-settings` as the validation mechanism
- [ADR-0022 — Reproducibility over Determinism](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md) — why experiment overrides outrank runtime overrides
- [ADR-0024 — Secrets Management Backend](../../18_decision_log/adr/ADR-0024-secrets-management-backend.md) — layer 7
- [ADR-0015 — Testing and CI](../../18_decision_log/adr/ADR-0015-testing-and-ci.md) — precedence verified by property tests
- [ADR-0014 — API Style and Realtime Transport](../../18_decision_log/adr/ADR-0014-api-style-and-realtime-transport.md) — the runtime-override route

**Superior documents:**
- `../platform/system_architecture.md`
- `kernel_architecture.md`
- `../../21_templates/CODING_STANDARDS_AND_BEST_PRACTICES.md`

**Concrete reference (does not restate §4's order):**
- `../services/configuration_management.md` — file layout, env-var mapping

**Interacting subsystems:**
- `llm_gateway.md` — provider credentials, model mappings, budgets, routing rules
- `workflow_engine.md` — timeouts, retry policies, feature flags
- `capability_manager.md` — which packs are enabled
- `evaluation_engine.md` — experiment overrides create controlled conditions
- `manifest_loader.md` — where packs are discovered
- `security_manager.md` — secure configuration values
- `../platform/platform_sdk.md` §5.8 `ConfigService`, §5.9 `SecretResolver` — the pack-facing surface (specified, not yet built)
- `../../09_security/secrets_management.md`

**Owned tables:**
- `../../08_database/data_model.md` §9.2 (`governance.config_changes`)

**Reference:**
- `../../20_glossary/glossary.md`
- `../../19_roadmap/feature_inventory.md`, `../../19_roadmap/implementation_status.md`, `../../19_roadmap/history/INDEX.md`
