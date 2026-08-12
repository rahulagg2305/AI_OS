# Configuration Management Deep Dive – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Configuration Management Deep Dive  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document deepens the design of **Configuration Management** in AI_OS.

It builds on the Configuration Manager Design and provides more detail on layering, precedence, validation, environment handling, feature flags, and experiment overrides.

This document is subordinate to:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Configuration Manager Design  
5. Coding Standards & Best Practices  

---

## Implementation Status (2026-07-28; §3.3 OTLP row updated 2026-08-01; §3.3 Redis row updated 2026-08-04)

**Partially built — the mechanics that exist match this document; several sections describe layers or features with no code behind them yet.** Verified against `kernel/src/ai_os_kernel/configuration_manager/`. **The rest of this section (layers, §3.1/§3.2, §4/§5) predates several steps completed later the same day this document was first checked (the full 7-layer precedence arc, `P01-S02-M01-T01/T03/T04/T06/T07/T08`) and is known-stale beyond the §3.3 row below — due its own dedicated refresh, not attempted piecemeal here:**

- **§3.1 File layout:** `config/platform.yaml` and `config/llm.yaml` exist; **`config/quality_gates.yaml` and `config/retention.yaml` do not exist on disk.** All four `infra/environments/*.yaml` files (`local`, `dev`, `staging`, `production`) exist, matching the document exactly.
- **§3.2 Format and typing is real but narrower than stated:** `ConfigurationManager.load()` (`configuration_manager/loader.py`) reads YAML with `yaml.safe_load` and validates the merged result against one Pydantic model, `PlatformConfig` — there is no per-section Pydantic model system yet, and `PlatformConfig` itself has exactly 7 fields (`env`, `role`, `host`, `port`, `log_level`, `capability_pack_dirs`, `manifest_schema_path`), none of them LLM, quality-gate, or retention settings, so `config/llm.yaml`'s existence does not mean its contents are consumed through this path today.
- **Only 3 of the 7 declared layers are implemented**, per the loader module's own docstring: built-in defaults (1), platform config file (3), environment config file (4). Pack defaults (2), runtime overrides (5), experiment overrides (6), and secret resolution (7) are not implemented — there is no code path for any of them yet.
- **§3.3 Environment variables:** `AIOS_ENV`, `AIOS_ROLE`, `AIOS_DATABASE_URL` are real and read directly from the environment, exactly as documented (`configuration_manager/bootstrap_env.py`, `persistence/settings.py`). **`OTEL_EXPORTER_OTLP_ENDPOINT` is now real too** (`P01-S05-M04-T03`, `ai_os_kernel/observability/settings.py:ObservabilitySettings`, read directly in `bootstrap.build_app()`) — unset (every environment today) keeps the console exporters. **`AIOS_REDIS_URL` is now real too** (`P02-S07-M23-T01`, `ai_os_kernel/caching/settings.py:RedisSettings`, `caching/client.py:build_redis_client`) — unset (every environment today) means no Redis client is built; nothing in a real Kernel composition calls `build_redis_client` yet, so this is a working connection layer, not caching behavior. **`AIOS_SECRET_BACKEND` is not implemented as a selector**: only one Secrets Manager backend exists (`secrets_manager/env_provider.py`), and no factory reads this variable to choose among `file`/`vault`/`aws`/`gcp`/`azure` — those five backends do not exist.
- **§4 Feature flags and §5 Experiment overrides are entirely unbuilt** — no feature-flag type or field exists anywhere in the Kernel, and the Experiment Manager they'd feed is 0% built.
- **§6 Validation is real**: an unknown key or wrong type in `platform.yaml`/an environment file raises `ConfigurationError` at `load()` time via `PlatformConfig.model_validate`, matching "invalid configuration should prevent startup."

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (module 4, Configuration Manager).

---

## 2. Design Goals

Configuration Management must:

- Make behaviour changeable without code changes
- Support multiple environments cleanly
- Provide clear precedence rules
- Validate configuration early
- Support feature flags and experiment overrides
- Keep secrets out of ordinary configuration
- Be auditable

---

## 3. Configuration Layers & Precedence

**The precedence order is defined once, in `../kernel/configuration_manager.md` §4.** It is not restated here — two copies of a precedence list is how they drift apart, which is exactly what happened in v1.0 of these documents.

This document covers the **concrete mechanics**: file layout, formats, environment variable mapping, and validation.

### 3.1 File layout

```text
config/
├── platform.yaml            layer 3 — platform-wide defaults
├── llm.yaml                 model aliases, fallback chains, pricing
├── quality_gates.yaml       gate thresholds
└── retention.yaml           retention windows

infra/environments/
├── local.yaml               layer 4
├── dev.yaml
├── staging.yaml
└── production.yaml
```

Pack defaults (layer 2) come from each pack's manifest `configSchema` defaults, namespaced under `packs.<pack_id>`.

### 3.2 Format and typing

YAML, loaded via `pydantic-settings` into typed models. Every configuration section has a Pydantic model; an unknown key or a wrong type fails at startup rather than at first use.

### 3.3 Environment variables

Environment variables carry only the bootstrap minimum, so the deployment does not become a second undocumented configuration system:

| Variable | Purpose |
|---|---|
| `AIOS_ENV` | Selects the environment configuration file |
| `AIOS_ROLE` | `api` or `worker` |
| `AIOS_DATABASE_URL` | PostgreSQL connection |
| `AIOS_REDIS_URL` | Redis connection |
| `AIOS_SECRET_BACKEND` | `env` \| `file` \| `vault` \| `aws` \| `gcp` \| `azure` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Telemetry export |

Everything else is a configuration file value.

---

## 4. Feature Flags

- Feature flags must be first-class configuration items.
- Flags can enable/disable capabilities, change routing behaviour, or control experimental features.
- Flags should be readable by Kernel components and, through controlled interfaces, by Capability Packs.
- Changes to critical flags should be auditable.

---

## 5. Experiment Overrides

For multi-LLM experiments and controlled tests, the platform must support temporary, isolated overrides of:

- Model selection
- Prompt versions
- Temperature and other LLM parameters
- Feature flags
- Other relevant settings

These overrides must not leak into other concurrent workflows.

---

## 6. Validation

- Configuration should be validated against schemas where practical.
- Invalid configuration should prevent startup or be clearly reported.
- Pack-declared configuration schemas should be respected.

---

## 7. Secrets in Configuration

- Ordinary configuration files may contain **references** to secrets.
- Secret **values** are resolved by the Secrets Management system at runtime.
- Secret values must never be stored in normal configuration files or logs.

---

## 8. Relationship with Other Components

- Almost every Kernel component depends on configuration.
- **LLM Gateway** uses it heavily for providers, models, budgets, and routing.
- **Workflow Engine** uses it for timeouts, retries, and feature flags.
- **Capability Packs** declare configuration schemas and defaults.
- **Evaluation / Benchmarking** uses experiment overrides.
- **Security Manager** and **Secrets Management** collaborate on sensitive values.
- **Observability** records significant configuration changes.

---

## 9. Observability & Audit

Significant configuration changes and the configuration set used by a workflow/experiment should be auditable so that runs are reproducible and debuggable.

---

## 10. Current Status

This document deepens the Configuration Management design. File formats and environment layout are settled and real (YAML, `config/` + `infra/environments/`) — see the Implementation Status section near the top for exactly which layers, files, and env vars exist versus which (pack defaults, runtime/experiment overrides, secret resolution, feature flags) remain unbuilt.

---

## 11. Final Authority

Order of precedence:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Configuration Manager Design  
5. Configuration Management Deep Dive  
6. Source Code

---

## 12. Related Documents

- [`../kernel/configuration_manager.md`](../kernel/configuration_manager.md) — the parent design this document deepens; defines the canonical 7-layer precedence order
- [`../../09_security/secrets_management.md`](../../09_security/secrets_management.md) — the secrets layer (§7) this document defers to, itself only partially built (env backend only)
- [`../platform/technology_stack.md`](../platform/technology_stack.md) — confirms `pydantic-settings`/Pydantic as the validation technology
- [`../../19_roadmap/feature_inventory.md`](../../19_roadmap/feature_inventory.md) — live build status
