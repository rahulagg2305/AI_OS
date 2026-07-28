# ADR-0001: Modular Capability Pack Architecture

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect, Project Owner
**Related Documents:** `docs/03_architecture/platform/system_architecture.md`, `docs/03_architecture/capability_framework/capability_pack_contract.md`, `docs/03_architecture/kernel/kernel_architecture.md`

---

## Context

AI_OS must support multiple, unrelated domains (software engineering, legacy-system intelligence, benchmarking, voice) and must keep growing without the core becoming a dumping ground. If domain logic accumulates in the core, every new domain increases the blast radius of every change and the platform loses the ability to be reasoned about — by humans or by AI models.

## Decision

AI_OS is split into a **domain-agnostic Platform Kernel** and **installable Capability Packs**. All domain and business logic lives exclusively in Capability Packs. Packs are discovered, validated, activated, upgraded, and removed through a declarative manifest, and interact with the platform only through the Platform SDK's published interfaces (see [ADR-0010](ADR-0010-composition-and-dependency-injection.md) and `docs/03_architecture/platform/platform_sdk.md`).

The Kernel shall never contain domain-specific logic, and adding a new domain shall never require a Kernel change.

## Alternatives Considered

- **Monolithic application with feature modules** — Simpler initially; rejected because module boundaries without a contract erode under delivery pressure, and there is no enforceable rule preventing domain logic from reaching the core.
- **Microservices per domain** — Strong isolation; rejected as premature. It imposes network, deployment, and operational cost before there is a single working workflow, and the Capability Pack contract already provides the isolation that matters at this stage. See [ADR-0020](ADR-0020-deployment-topology-and-scaling.md).
- **Script/plugin directory with dynamic loading and no contract** — Cheapest; rejected because unvalidated plugins cannot be governed, versioned, or safely removed.

## Consequences

### Positive
- New domains are added by installing a pack; the Kernel remains stable.
- Packs are independently testable, versionable, and removable.
- The Kernel's surface area stays small enough to hold to a high quality bar.

### Negative
- Requires up-front investment in the SDK, manifest schema, and loader before the first useful feature ships.
- Pack authors must work through interfaces rather than reaching into internals, which is more ceremony for small changes.

### Neutral
- Packs ship in-process in the initial topology; this ADR does not commit to process isolation per pack.

## Compliance

Complies with the Project Constitution (Capability Pack Architecture, Modular by Design, Interface-Driven Design) and the AI Governance Framework (Capability Pack Governance).

## References

- `docs/03_architecture/capability_framework/capability_pack_contract.md`
- `docs/06_capability_packs/capability_pack_development_guide.md`

---

## Implementation Status (appended 2026-07-28 — not part of the Accepted decision)

**Status in code:** Partially implemented

The Kernel holds no domain logic, and one real pack (`capability_packs/software-engineering/`) is discovered from its `manifest.yaml`, validated, registered, activated, and resolved through the Capability Manager, receiving a reduced `PackContext` (`ai_os_kernel.capability_manager.pack_contract`). The Platform SDK that the pack boundary is supposed to be expressed through does not exist yet — `platform_sdk/` contains only `schemas/manifest.schema.json`, so the pack currently depends on `ai-os-kernel` directly as a documented temporary exception, and pack upgrade, removal, health monitoring, and permission enforcement are not built.

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
