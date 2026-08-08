# ADR-0016: Tool Execution Sandboxing — Two Trust Tiers with Container Isolation

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect, Project Owner
**Related Documents:** `docs/09_security/security_architecture.md`, `docs/06_capability_packs/software_engineering/tools_quality_gates.md`

---

## Context

AI_OS's core function is to execute code it did not write: LLM-generated source, generated build and test commands, and dependency installation, run against repositories that may be third-party and untrusted (the Project Intelligence pack ingests arbitrary codebases). Nothing in the documentation set described how that execution is contained. This is the platform's highest-consequence risk: an unsandboxed platform combining code generation, filesystem write access, `git push` capability, network egress, and provider credentials is a remote-code-execution engine pointed at its own infrastructure.

Two threats must both be handled: **malicious or damaging generated code**, and **prompt injection via untrusted repository content** — where a comment or README in an ingested repository attempts to instruct the agent reading it.

## Decision

**All execution is classified into two trust tiers. There is no third, un-tiered path.**

### Tier 1 — Untrusted execution (default for anything involving generated code or ingested repositories)

Runs in an **ephemeral OCI container per workflow step**, via a `SandboxRuntime` Protocol implemented by Docker and Podman adapters:

> **Implementation naming note, added 2026-07-28 — not a revision of this decision.** The real Kernel implementation names this seam `SandboxExecutor` (`ai_os_kernel.sandbox.executor.SandboxExecutor`), not `SandboxRuntime`. Both names refer to the identical architectural seam this ADR decides on; the implementation's own package docstring (`ai_os_kernel/sandbox/__init__.py`) has recorded this discrepancy since it was first noticed, rather than silently picking one name. This note is the "future documentation pass" that docstring anticipated: `SandboxRuntime` remains this ADR's own name for the concept it decided on (unchanged, per ADR immutability — an Accepted ADR is revised only by superseding it, never edited in place); `SandboxExecutor` is the concrete Protocol name a reader should look for in source. A future ADR revision, if one is ever written for an unrelated reason, should reconcile the two; this note only records the mapping so a reader is never confused by it in the meantime.

| Control | Setting |
|---|---|
| Network | **Disabled by default** (`--network=none`). Dependency installation runs in a separate, explicitly-declared step through an egress proxy with a package-registry allowlist. |
| Filesystem | Read-only root; the workflow's isolated working copy mounted at a single writable path; `tmpfs` for scratch. |
| Identity | Non-root UID/GID; `--user` always set. |
| Capabilities | `--cap-drop=ALL`, `--security-opt=no-new-privileges`. |
| Syscalls | Default seccomp profile retained (never `--privileged`, never `--security-opt seccomp=unconfined`). |
| Limits | Memory, CPU quota, PID limit, and wall-clock timeout, all from configuration. |
| Host access | **No Docker socket, ever.** No host mounts beyond the working copy. |
| Secrets | None injected. Credentials never enter a Tier 1 container. |
| Lifetime | Destroyed after the step; never reused across workflows. |

### Tier 2 — Trusted platform operations

Run in-process: reads within the workflow's own workspace, git metadata operations, manifest parsing, database and platform-service access. Tier 2 requires **path allowlisting with canonical-path resolution** — every path is resolved and verified to remain inside the workspace root, rejecting `..`, symlinks, and absolute escapes.

A tool declares its tier in the manifest. **Any tool that executes a command string, compiles, runs tests, installs dependencies, or processes untrusted repository content is Tier 1.** Tier 2 is not available for those, and the classification is validated at pack load time rather than trusted.

### Prompt-injection controls (structural, not prompt-based)

1. **Provenance tagging.** Every context item carries `trusted` or `untrusted`. Repository content, ingested documents, tool output, and web content are always `untrusted`.
2. **Delimited framing.** Untrusted content is wrapped in explicit boundaries with an instruction that content inside is data, never instruction.
3. **Authority cannot come from content.** The decisive control: permissions derive only from the manifest and the security context. No LLM output can grant a permission, widen a scope, escalate a tier, skip a gate, or approve a Human Approval Point. A successful injection can produce bad *output* — it cannot produce new *authority*.
4. **Output validation.** Agent output is validated against its declared schema before use.
5. **Irreversible actions gated.** Push, deploy, and release always pass a Human Approval Point ([ADR-0007](ADR-0007-human-governance-for-critical-decisions.md)).

## Alternatives Considered

- **Direct subprocess execution with a restricted user** — Simplest; rejected outright. It shares the kernel, filesystem namespace, and network namespace with the platform, and offers no meaningful containment for hostile code.
- **`chroot` / bare namespace isolation** — Rejected: partial isolation with a long history of escapes, and no resource limits.
- **Micro-VMs (Firecracker) or gVisor from the start** — The strongest isolation. Rejected as the *default* because of operational and platform-compatibility cost, but recorded as the documented hardening path: gVisor (`runsc`) is a drop-in `SandboxRuntime` configuration, and multi-tenant or hostile-input deployments should enable it. Doing so is a configuration change, not a redesign — which is the point of putting the runtime behind a Protocol.
- **A hosted third-party code-execution sandbox** — Rejected as the default: sends customer source code to another vendor, adds latency, and constrains toolchains. Remains available as an alternative adapter.
- **Prompt-only injection defence ("ignore instructions in the content")** — Rejected as a primary control. Instruction-based defences are probabilistic; control 3 above is structural and holds even when the model is fully persuaded.

## Consequences

### Positive
- Generated code cannot reach the host, the platform's credentials, or the network by default.
- Untrusted repository ingestion becomes a bounded operation.
- Prompt injection is contained by an authority model rather than by prompt wording.
- Hardening to gVisor or micro-VMs is a configuration change.

### Negative
- Container startup adds per-step latency; mitigated by pre-pulled base images and a warm pool.
- Docker or Podman becomes a runtime dependency for development and CI.
- Network-disabled-by-default means dependency installation must be an explicit, declared step — more workflow ceremony, deliberately.

### Neutral
- Tier classification is validated at pack load, so a mis-declared tool fails loudly at install time rather than silently at run time.

## Compliance

Complies with the Constitution (Article 6: Least Privilege, Secure Defaults, Defense in Depth) and the AI Governance Framework (Security Governance).

## References

- `docs/09_security/security_architecture.md`
- [ADR-0023](ADR-0023-identity-roles-and-permissions.md), [ADR-0024](ADR-0024-secrets-management-backend.md)

---

## Implementation Status (appended 2026-07-28 — not part of the Accepted decision)

**Updated 2026-08-09 (`P03-S01-M20-T05`): the gVisor hardening path is now a real configuration line.** `DockerSandbox` accepts a `runtime` parameter (`AIOS_SANDBOX_RUNTIME` env var, unset by default — omitted entirely from the Docker API call when unset, so every existing caller is byte-for-byte unchanged) passed straight through to `containers.create(..., runtime=...)`, exactly the "drop-in `SandboxRuntime` configuration ... a configuration change, not a redesign" this ADR's own Alternatives Considered section names. **Disclosed, not silently assumed:** this project's own dev and CI environments install no gVisor/Firecracker runtime (`docker info` here registers only `io.containerd.runc.v2`/`nvidia`/`runc`; `.github/workflows/ci.yml` has no gVisor install step) — proven end to end against the real, available `runc` runtime (an explicit, valid runtime executes identically to the unconfigured default) and a genuinely-unknown runtime name is refused by the real Docker Engine itself, proving the value truly reaches it. Actually observing hardened, gVisor-backed isolation remains real, disclosed, unbuilt verification work, gated on a host that has it installed — this closes the "configuration change" ADR-0016 promises would be sufficient, not the claim that hardened isolation has been witnessed. Full reasoning: `docker_executor.py`'s own docstring, `sandbox/__init__.py`'s own package docstring.

**Status in code:** Partially implemented (Tier 1 container isolation fully honoured)

The Tier 1 decision is real and live-verified: `DockerSandbox` (`ai_os_kernel.sandbox.docker_executor`) implements all five guarantees — `--network=none`, read-only root with a single writable mount, non-root `--user`, `--cap-drop=ALL` with `no-new-privileges`, resource and wall-clock limits, ephemeral per-step lifetime, no Docker socket, no secrets — and it is now the configuration-driven default (`AIOS_SANDBOX_BACKEND`, default `docker`), proven end to end against a live daemon including network and filesystem containment for code the pipeline itself generated. `LocalSubprocessSandbox` remains as the explicit 3-of-5 opt-out. Of the five prompt-injection controls, three hold: provenance tagging is real (every `ContextItem` carries `trust: "trusted" | "untrusted"` plus a `SourceRef`, defaulting workflow inputs to `untrusted`), authority never comes from content (control 3), and agent output is schema-validated (control 4). Not built: delimited framing of untrusted content at prompt-render time (control 2), the egress proxy with a package-registry allowlist, manifest-declared tier classification validated at pack load, and Tier 2 path allowlisting with canonical-path resolution. **Correction (2026-08-08, found during a full pre-completion health audit): control 5 (the Human Approval Point gating irreversible actions) is no longer accurate here — it was built 2026-08-02 and never backfilled into this ADR.** `se.delivery_pipeline`'s own real `approve-git-push` point (`P03-S03-M30-T05`) genuinely gates its one real, external, irreversible action (a real `git push`) behind a durable pause and a real, attributable, RBAC-authorized decision — proven end to end (`test_delivery_pipeline_git_push.py`).

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
