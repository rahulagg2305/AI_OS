# Storage Service Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Storage Service Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-28; updated 2026-08-04)

**Built:** a real, local-filesystem content-addressed artifact store — `kernel/src/ai_os_kernel/storage_service/local_store.py`'s `LocalFilesystemArtifactStore` (`P02-S07-M21-T01`), plus `StorageSettings` (`AIOS_STORAGE_ROOT`). Content is addressed by its own real SHA-256 digest and returned as the real, pre-existing SDK boundary model `ai_os_sdk.models.common.ArtifactRef` (`sha256:<hex>`), not a new, duplicate shape. Proven against a real filesystem: identical content deduplicates to one real stored file and an equal `ArtifactRef`; different content produces different files and different ids; a round trip returns the exact original bytes. This module lives at `kernel/src/ai_os_kernel/storage_service/`, not `platform_services/` — that directory still has **no tracked content at all** (git does not track empty directories), and remains the planned, SDK-level Platform Service home this design document describes; today's real code is Kernel-internal.

**Not built:** no S3-compatible "prod" backend (no S3 client dependency, configuration, or endpoint exists anywhere in this codebase to build or test one against yet); no `Cache`-style `Protocol` over the store (a single real implementation exists; a second is documented intent, not yet real, ADR-0004); no real Kernel caller constructs this store yet — workflow artifacts remain plain files in per-agent temporary directories created by the Software Engineering pack's own agents, unchanged by this step. Stage B deliverable, still in progress.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document defines the design of the **Storage Service**, a shared Platform Service in AI_OS.

The Storage Service provides a consistent, abstract interface for storing and retrieving files, artifacts, blobs, and other binary or structured data needed by the Kernel and by Capability Packs.

This document is subordinate to:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Coding Standards & Best Practices  

---

## 2. Design Goals

The Storage Service must:

- Provide a unified interface independent of the underlying storage technology
- Support multiple backends (local filesystem, object storage, etc.)
- Be reliable and observable
- Support both temporary and durable storage needs
- Enforce access controls in coordination with the Security Manager
- Remain simple for the majority of use cases

---

## 3. Core Responsibilities

- Store and retrieve artifacts (code, documents, logs, reports, model outputs, etc.)
- Support streaming and large-object handling where necessary
- Provide metadata and addressing (URIs / IDs)
- Support deletion and lifecycle policies
- Integrate with authentication and authorization
- Emit observability data for storage operations

---

## 4. High-Level Structure

```text
Storage Service
│
├── StorageService (SDK Protocol)
├── Backend Adapters
│     ├── local        filesystem — development and single node
│     └── s3           S3-compatible object storage — production
├── Content Addressing        sha256 → ArtifactRef
├── Metadata Manager
├── Access Control Bridge
└── Observability Hook
```

**Artifacts are content-addressed** as `sha256:<hex>`. Workflow state references artifacts by ID and never embeds their bytes, which keeps the event log small enough to remain queryable and replayable ([ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md)).

Content addressing also gives deduplication and integrity verification for free: the same content stored twice occupies one object, and a corrupted retrieval is detectable by re-hashing.

---

## 5. Key Design Rules

- Callers should depend on the abstract Storage interface, not on a concrete backend.
- Capability Packs must not assume a particular storage technology.
- Sensitive artifacts must be stored in accordance with security policies.
- Storage locations and credentials must be configuration-driven.
- Artifacts should be referenced by stable identifiers so that workflow state does not need to embed large payloads.

---

## 6. Relationship with Other Components

- **Workflow Engine** and **Agents** store and retrieve work artifacts through this service (via Tools or Kernel interfaces).
- **Context Manager** and **Knowledge Manager** may use it for larger content.
- **Evaluation Engine** stores experiment results and reports.
- **Dashboard** may serve or link to stored artifacts.
- **Security Manager** enforces access control.
- **Configuration Manager** provides backend configuration and credentials.

---

## 7. Observability Requirements

Storage operations should emit:

- Operation type (read / write / delete)
- Artifact identifier
- Size and duration
- Success / failure
- Correlation with Workflow ID / Trace ID when applicable

---

## 8. Current Status

This document defines the design baseline for the Storage Service.

Concrete backend selection, API shapes, and lifecycle policies will be refined during implementation.

---

## 9. Final Authority

Order of precedence:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Storage Service Design  
5. Source Code
