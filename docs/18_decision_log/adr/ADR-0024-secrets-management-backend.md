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
