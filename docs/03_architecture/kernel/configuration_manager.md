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

## Implementation Status (2026-08-07)

**Built:** `kernel/src/ai_os_kernel/configuration_manager/` (9 modules). `ConfigurationManager` in `loader.py` resolves **all 7 precedence layers** in §4 — layer 1 (built-in defaults, as field defaults on the `PlatformConfig` model in `models.py`), layer 2 (pack-level defaults: `extract_pack_defaults` reads the `default` values declared in a pack manifest's own `configSchema`, merged in via `ConfigurationManager.load`'s `pack_manifests` argument), layer 3 (`config/platform.yaml`), layer 4 (`infra/environments/<env>.yaml`), layer 5 (runtime overrides: `runtime_overrides.py`'s `RuntimeOverrideStore` holds the live, in-memory state; its `apply` audits the change via the Change Auditor below, then applies it; `load`'s `runtime_overrides` argument merges a plain snapshot in above every file layer), layer 6 — **now two real, deliberately separate halves, not one mechanism** — and layer 7 (secret resolution: `secrets.py`'s `resolve_secret_references` resolves every `secret://` reference surviving the layer 1-6 merge through an injected `SecretProvider`, via the async sibling method `ConfigurationManager.load_with_secrets_resolved` — `load` itself stays synchronous).

**Layer 6, half A — feature flags** (`P01-S02-M01-T07`): `feature_flags.py`'s `ExperimentOverrideStore` keys *boolean* overrides by `run_id` — deliberately never merged into the shared process-wide dict, since §4 requires it isolated per run; `resolve_feature_flag` resolves one flag through a run's override, then a live runtime override, then the last pack manifest declaring it, then a caller default. **Layer 6, half B — arbitrary-value experiment overrides** (`P01-S02-M01-T05`, added 2026-08-07): "an experiment definition" -> "overrides scoped to one run" for *any* config key, a real, distinct need half A's boolean-only type cannot hold. `ConfigurationManager.load`'s new `pinned_conditions` argument (a plain, per-call `Mapping[str, Any]`, `None`-default) merges strictly above `runtime_overrides` — "experiment overrides (6) beat runtime overrides (5)" — and flows through `load_with_secrets_resolved` too, ahead of layer 7. Isolation is structural, not policy: nothing is ever stored on `self`, so two concurrent `load()` calls with different `pinned_conditions` can never observe each other's layer 6 (proven: `tests/unit/kernel/configuration_manager/test_loader.py`). **Investigated and kept separate from half A, not unified**, when built: widening `ExperimentOverrideStore` to `Any` would have reopened its own already-evidenced ticket for a real integration depth of exactly one caller (`GET /config/flags`, which always passes an empty, request-scoped store) — too shallow to justify the cost; the two halves share the same §4 precedence slot but not the same live-state mechanism.

Layers 1-5 deep-merge and validate into one frozen `PlatformConfig`; layer 6 (both halves) is its own separate, per-call/per-run resolution path (never a `PlatformConfig` field, by design); layer 7's result is a plain `dict`, not a `PlatformConfig`, because a resolved value is `SecretValue`-wrapped (ADR-0024 rule 2) and no field on that model is secret-shaped yet — deliberately not invented speculatively. A missing file contributes nothing rather than erroring, so the layers beneath it apply. Only the `kernel:` top-level mapping of each file is read. `BootstrapEnv` in `bootstrap_env.py` is the separate, deliberately minimal `pydantic-settings` reader for the bootstrap-identity env vars that cannot themselves be file-driven (`AIOS_ENV`, `AIOS_ROLE`, database URL, and so on). `errors.py` raises `ConfigurationError` on an unknown environment, invalid YAML, a non-mapping top level, or a `PlatformConfig` validation failure. The valid-environment set (`local`, `dev`, `staging`, `production`) is a structural constant, not itself configuration. This component is constructed first in `kernel/src/ai_os_kernel/bootstrap.py`, before anything else. **Change Auditor:** `audit.py`'s `SqlConfigChangeWriter` now writes real `governance.config_changes` rows (old/new value *digests*, never the values themselves) and `verify_config_change` detects a digest tampered with directly in the database — so §8's audit question is answerable for a change recorded through this writer; `RuntimeOverrideStore.apply` is its first real call site. `evaluation.run_manifests` is still a table with no writer.

**Not built:** No standalone Feature Flag Manager component or Experiment Manager service — both layer-6 mechanisms exist and are proven, but nothing yet calls `ExperimentOverrideStore.set_override` or passes a real `pinned_conditions` mapping from an experiment-running component, because no such component exists yet (the Benchmarking Pack, `P04-S03-M34`, has no manifest/submission path). No Configuration API — the `PATCH /api/v1/config` route and `aios config` CLI that would call `RuntimeOverrideStore.apply` do not exist yet (§6's "writer, then route" ordering: the writer exists now; the route is what remains). Discovering *which* packs are activated (Manifest Loader integration) is not wired into layer 2 either — `load`'s `pack_manifests` argument takes already-discovered manifests as plain input. Layer 7 resolves references passed to it but nothing yet calls `load_with_secrets_resolved` from a real startup path, and no `PlatformConfig` field is secret-shaped yet — the layer exists for the day one is. The property tests §4 requires for precedence verification now cover all seven layers, including both layer-6 halves. Of §5's seven components, only Configuration Loader, Layer Merger and Schema Validator are real.

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
| **Secret backend integration** | **Decided in [ADR-0024](../../18_decision_log/adr/ADR-0024-secrets-management-backend.md), and now wired into the merge.** `secret://<provider>/<name>[#version]` references resolved at point of use through a pluggable `SecretProvider`, with Vault as the production reference and four backends specified (env/file/vault/cloud). Real code exists in `kernel/src/ai_os_kernel/secrets_manager/` (`provider.py`, `env_provider.py`, `reference.py`, `value.py`) — `EnvSecretProvider` only. `configuration_manager/secrets.py`'s `resolve_secret_references` (`P01-S02-M01-T06`) resolves a `secret://` reference surviving the layer 1-6 merge, called via `ConfigurationManager.load_with_secrets_resolved`. **Named remaining gap:** the result is a plain `dict`, not a `PlatformConfig` — a resolved value is `SecretValue`-wrapped per ADR-0024 rule 2, and no field on that model is secret-shaped yet, so there is nothing today for a resolved secret to actually reach through the normal `load()` path. |
| **API shapes** | **Decided at the platform level, partially built here.** Runtime overrides (layer 5) are `PATCH /api/v1/config` under the REST conventions in `../../07_api/api_architecture.md` ([ADR-0014](../../18_decision_log/adr/ADR-0014-api-style-and-realtime-transport.md)); the CLI surface is `aios config` (`../../07_api/cli_design.md`). The layer itself and its audit writer both now exist (`RuntimeOverrideStore.apply`, `SqlConfigChangeWriter`) — §4's "must be audited" requirement is satisfied at the layer level. **Named remaining gap:** neither the HTTP route nor the CLI exists yet to call `RuntimeOverrideStore.apply`. |

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
