# Secrets Management – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Secrets Management  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the design of **Secrets Management** in AI_OS.

Secrets (API keys, tokens, passwords, certificates, etc.) must be handled securely so that they never appear in source code, Capability Packs, logs, or prompts. This is a critical security and governance requirement.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. Security Manager Design  
4. Configuration Manager Design  
5. Authentication & Authorization Deep Dive  

---

## Implementation Status (updated 2026-08-08, `P07-S02-M19-T01`)

**Three of the four §5 backend adapters now exist.** Verified against `kernel/src/ai_os_kernel/secrets_manager/`: `env_provider.py` (`EnvSecretProvider`, ADR-0024-scoped to local development only), `file_provider.py` (`FileSecretProvider`, added `P01-S02-M19-T03` — a plaintext mounted file, not age/SOPS decryption; see that module's own docstring), and `vault_provider.py` (`VaultSecretProvider`, added `P07-S02-M19-T01` — real Vault KV v2, token auth only). Cloud secret managers remain unimplemented. **The backend-selection factory this section previously said did not exist is now real**: `backend_selection.py`'s `build_secret_provider_from_env()` reads `AIOS_SECRET_BACKEND` exactly as this document's own §5 always documented, and is the one thing `bootstrap.py`'s three real callers now go through — none of them hardcode `EnvSecretProvider()` anymore. `secret_reference_for()` (same module) keeps a reference's own backend segment in agreement with whichever backend the factory selected, closing a real gap the two hardcoded, pre-existing references (Anthropic API key, JWT signing key) would otherwise have hit silently.

**Real:** the `secret://<provider>/<name>[#version]` reference format and its parser (`reference.py`, regex-validated); the `SecretValue` wrapper (`value.py`) — its `__str__`/`__repr__` do return `"***"` exactly as §5 and §6 describe; the Access Broker (`access_broker.py`, `P01-S02-M19-T04`) — authorization via `security_manager`'s `secret:access` permission (`admin` role only) plus a real, hash-chained `governance.audit_log` row for every attempt, allowed or denied; the TTL cache + rotation-invalidation layer (`cache.py`, `P01-S02-M19-T05`) — `CachingSecretProvider` wraps any backend with a per-reference cache (default 300 s per this document's own §6) plus an explicit `invalidate()` hook; the prompt-assembly leak scan (`leak_scan.py`, `P01-S02-M19-T06`) — rejects a rendered prompt containing a resolved secret value verbatim and audits the block. §8's "must record who/what requested a secret" is implemented at the Access Broker's gate specifically — a resolution that bypasses it (the Configuration Manager's own resolution path, noted below) is not yet audited at the point of access.

**Not yet wired into any specific consumer** (LLM Gateway, Git Integration Service, ...) — the Access Broker, cache, and leak scan all exist as composable building blocks but nothing in the codebase calls them yet.

Authoritative, always-current status: `../19_roadmap/feature_inventory.md`.

---

## 2. Design Goals

Secrets Management must:

- Keep secrets out of source code and configuration files that are committed
- Provide secure injection of secrets at runtime
- Support rotation
- Limit exposure (least privilege, short lifetime where practical)
- Be fully auditable
- Integrate cleanly with the Configuration Manager and Security Manager

---

## 3. Core Principles

- **Never hard-code secrets**
- **Never store secrets in Capability Packs**
- **Never log secrets**
- **Never send secrets to LLMs** unless absolutely unavoidable and explicitly approved
- Secrets must be referenced by identity/name, not by value, in most of the platform
- Access to secrets must be authorized and audited

---

## 4. Core Responsibilities

- Store secrets securely (via an approved backend)
- Provide controlled access to secrets at runtime
- Inject secrets into the components that need them (e.g., LLM Gateway providers, Git credentials, external services)
- Support rotation and revocation
- Record access for audit purposes
- Integrate with configuration so that components request secrets by reference

---

## 5. High-Level Structure

```text
Secrets Management
│
├── SecretProvider (SDK Protocol)
├── Backend Adapters
│     ├── env         local development only
│     ├── file        age/SOPS encrypted, single-node
│     ├── vault       HashiCorp Vault — REFERENCE PRODUCTION BACKEND
│     └── cloud       AWS / GCP / Azure secret managers
├── Access Broker           authorization + audit per access
├── Resolution Layer        late, narrow, in-memory only
├── SecretValue wrapper     __str__/__repr__ return "***"
├── TTL cache + rotation invalidation
└── Audit Logger            records the NAME, never the value
```

**Reference format:** `secret://<provider>/<name>[#<version>]`, for example `secret://vault/llm/anthropic-api-key`. Configuration files, manifests, and the database contain references only; a value that looks like a literal credential fails validation.

Backend is selected by `AIOS_SECRET_BACKEND`. Decided in [ADR-0024](../18_decision_log/adr/ADR-0024-secrets-management-backend.md).

---

## 6. Key Design Rules

- Components ask for a secret by reference; they never own storage of the value.
- The LLM Gateway, Speech Gateway, Git Integration Service, and external connectors are the primary consumers.
- Capability Packs declare the secret references they need in the manifest, and receive them only if granted.
- Configuration files may contain secret *references*, never secret *values*.
- **A resolved secret is wrapped in `SecretValue`.** Its `__str__` and `__repr__` return `***`, so accidental logging, serialisation, or inclusion in an error message is prevented by the type rather than by reviewer vigilance. Access to the raw value requires an explicit method call.
- **A secret never enters a Tier 1 sandbox.** Operations that need a credential — `git push`, a provider call — are performed by a platform service that holds the credential and exposes only the *operation*. The sandbox receives a capability, not a secret. This is the single most important rule here: injecting credentials into the environment the sandbox exists to contain would defeat the containment entirely.
- **A secret is never sent to a model.** Prompt assembly rejects content matching a resolved secret value, as defence in depth.
- Rotation takes effect within the cache TTL (default 300 s) with no restart.

---

## 7. Relationship with Other Components

- **Configuration Manager** works with Secrets Management to resolve secret references.
- **Security Manager** enforces who/what may access which secrets.
- **LLM Gateway** obtains provider API keys through this system.
- **Git Integration Service** obtains repository credentials through this system.
- **Observability** records secret access events (without recording the secret values).
- **Capability Packs** must never embed secrets.

---

## 8. Observability & Audit Requirements

Must record:

- Who/what requested a secret
- Which secret was requested (by name/id)
- Time of access
- Success or failure
- Correlation with Trace ID / Workflow ID when applicable

Never record the secret value itself.

---

## 9. Current Status

This document defines the design baseline for Secrets Management. See the Implementation Status section near the top: the reference format and `SecretValue` wrapper are real; three of four backends (`env`, `file`, `vault`) are implemented, cloud secret managers are not; the Access Broker, TTL cache/rotation, and the real `AIOS_SECRET_BACKEND` switch are all real too. Not yet wired into any specific consumer.

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. Security Manager Design  
4. Secrets Management  
5. Source Code

---

## 11. Related Documents

- [`security_architecture.md`](security_architecture.md) §7 — the security-relevant invariants this document is the detail behind
- [`authentication_authorization.md`](authentication_authorization.md) — the identity/permission system that governs who may request a secret
- [ADR-0024](../18_decision_log/adr/ADR-0024-secrets-management-backend.md) — the backend decision this document implements (`env`, `file`, and `vault` real; cloud secret managers not yet built)
- [`../19_roadmap/feature_inventory.md`](../19_roadmap/feature_inventory.md) — live build status
