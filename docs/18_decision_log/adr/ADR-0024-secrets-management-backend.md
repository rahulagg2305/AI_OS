# ADR-0024: Secrets Management — Reference-Based Resolution with Pluggable Backends

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect
**Related Documents:** `docs/09_security/secrets_management.md`, `docs/03_architecture/kernel/configuration_manager.md`

---

## Context

The Secrets Management design established the right principles — never in source, never in packs, never logged, referenced by name — but named no backend and no resolution mechanism, so it could not be implemented. AI_OS holds provider API keys, Git credentials, database credentials, and speech-provider keys, and it runs untrusted generated code in the same platform ([ADR-0016](ADR-0016-tool-execution-sandboxing.md)), which raises the stakes on where secret values are allowed to exist.

## Decision

**Secrets are referenced by URI and resolved at point of use through a `SecretProvider` Protocol.**

**Reference format:** `secret://<provider>/<name>[#<version>]`, for example `secret://vault/llm/anthropic-api-key`. Configuration files, manifests, and the database contain **references only**. A configuration value that looks like a literal credential fails validation.

**Backends (adapters behind one Protocol):**

| Backend | Use |
|---|---|
| Environment variables | Local development only. |
| Encrypted local file (age/SOPS) | Single-node deployments. |
| **HashiCorp Vault** | Reference production backend. Supports leases, rotation, and audited access. |
| Cloud secret managers (AWS/GCP/Azure) | Adapters for cloud deployments. |

**Handling rules — the part that makes the principles enforceable:**

1. **Resolution is late and narrow.** A secret is resolved at the moment of use, by the component that needs it, and never placed into a broadly-shared config object.
2. **Values are wrapped.** A resolved secret is a `SecretValue` whose `__str__`/`__repr__` return `***`, so it cannot be accidentally logged, serialised, or included in an error message. Access to the raw value requires an explicit method call.
3. **In-memory only.** Never written to disk, workflow state, telemetry, event payloads, or audit records. Audit records the secret's *name*, never its value.
4. **Never in a Tier 1 sandbox.** Generated code and untrusted repository processing never receive credentials. Operations needing credentials (for example `git push`) execute in the platform's Git Integration Service, which holds the credential and exposes only the operation — so the sandbox gets a capability, not a secret.
5. **Never sent to a model.** Prompt assembly rejects any content matching a resolved secret value, as a defence against a secret reaching a provider through context.
6. **TTL caching with rotation support.** Resolved values are cached in memory for a configured TTL; a rotation signal invalidates the cache. Rotation does not require a restart.

## Alternatives Considered

- **Environment variables in production** — Simplest; rejected because they are visible to child processes (including sandboxes), leak into crash dumps and process listings, and support neither rotation nor per-access audit.
- **A dedicated encrypted table in PostgreSQL** — Rejected: puts the platform in the key-management business, and a database compromise would yield every credential.
- **Vault as the only backend** — Rejected: forces a Vault deployment on local development and single-node users, which would guarantee workarounds.
- **Injecting secrets into sandboxes so tools can call authenticated services directly** — Rejected outright. It is the single change that would most increase blast radius, handing credentials to the exact code the sandbox exists to contain. The capability-not-credential pattern in rule 4 exists precisely to avoid it.

## Consequences

### Positive
- Secret values exist only in memory, only where needed, for as long as needed.
- Rotation is supported without redeployment.
- Accidental logging is prevented by the type, not by reviewer vigilance.
- Backends are swappable per environment.

### Negative
- Requires a running Vault (or equivalent) for production and an operational procedure for unsealing and rotation.
- The `SecretValue` wrapper adds a small amount of ceremony at use sites — an acceptable trade for making the failure mode structurally impossible.

### Neutral
- The prompt-scanning rule (5) is a defence in depth measure, not a substitute for not putting secrets in context.

## Compliance

Complies with the Constitution (Article 6: Secret Management) and the Secrets Management design (referenced by identity, audited access, never logged).

## References

- `docs/09_security/security_architecture.md`
- `docs/03_architecture/services/git_integration.md`

---

## Implementation Status (appended 2026-07-28 — not part of the Accepted decision)

**Status in code:** Partially implemented

The mechanism is real: `secret://<provider>/<name>` references are parsed and resolved at point of use through a `SecretProvider` Protocol, and resolved values are wrapped in a `SecretValue` that redacts on `str`/`repr` (`ai_os_kernel/secrets_manager/`) — the Gateway's Anthropic key and the JWT signing key both flow through it. **This paragraph was stale even before the update below**: the `env` backend is not the only one — a real, mounted-file backend (`file_provider.py`), a TTL cache with rotation invalidation (`cache.py`), a per-access audit Access Broker (`access_broker.py`), and a prompt-assembly leak scan (`leak_scan.py`) all exist too, none wired into any real consumer yet. Still missing: age/SOPS decryption, cloud adapters, and (until the update below) Vault.

**Updated 2026-08-08 (`P07-S02-M19-T01`): the `vault` backend is real.** `VaultSecretProvider` resolves `secret://vault/<name>[#<version>]` against a real Vault KV v2 mount, token authentication only (AppRole/Kubernetes auth unbuilt) — the "reference production backend" this ADR names. **The real `AIOS_SECRET_BACKEND` switch secrets_management.md §5 documents also did not exist before this step** — every real caller (`bootstrap.py`) hardcoded `EnvSecretProvider()` directly; `build_secret_provider_from_env()` is the one real place that variable is now read, and `bootstrap.py`'s three real callers all go through it. A real design fork was found and product-owner-decided along the way: the two pre-existing hardcoded `secret://env/...` references (Anthropic API key, JWT signing key) would have silently stayed pinned to `env` even after switching the backend to `vault`, since a reference names its own backend independent of which provider object is selected — closed by making both follow the identical `AIOS_SECRET_BACKEND` value via a new `secret_reference_for()`, so the provider and the reference can never disagree. Proven against a real, self-hosted Vault dev-mode container (`tests/integration/secrets_manager/test_vault_provider_live.py`): a real secret written through Vault's own API and read back, real KV v2 version history (two real versions, each resolved independently), a genuinely nonexistent path and an invalid token both refused, and the full switch-and-resolve path proven end to end.

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
