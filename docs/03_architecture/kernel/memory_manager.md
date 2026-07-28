# Memory Manager Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Memory Manager Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the design of the **Memory Manager**, a core component of the AI_OS Platform Kernel.

The Memory Manager is responsible for storing and retrieving dynamic, experiential, and reusable engineering knowledge that goes beyond static documentation. It complements the Knowledge Manager by handling shorter-term workflow memory, longer-term engineering memory, and proven reusable assets.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Context Manager Design  
6. Knowledge Manager Design  

---

## 2. Design Goals

The Memory Manager must:

- Capture useful engineering experience and outcomes
- Support both short-lived (workflow) and long-lived (engineering) memory
- Enable reuse of proven solutions and patterns
- Remain domain-agnostic at the Kernel level
- Provide clean interfaces to the Context Manager
- Be fully observable and auditable
- Avoid becoming an uncontrolled dumping ground

---

## 3. Types of Memory

### 3.1 Workflow Memory
- Temporary state and intermediate results related to a running workflow
- Exists primarily for the duration of the workflow (or a defined retention period)
- Used to give later steps awareness of earlier decisions and outputs

### 3.2 Engineering Memory
- Longer-term records of what worked well, what failed, and why
- Proven code patterns, module designs, successful prompts, architectural choices
- Lessons learned from previous projects or experiments

### 3.3 Reusable Assets
- Concrete, reusable artifacts (e.g., well-tested modules, templates, configurations)
- Can be retrieved and adapted by agents in future work

---

## 4. Core Responsibilities

- Store memory items with clear metadata (source, timestamp, workflow/experiment ID, quality signals)
- Support efficient retrieval by the Context Manager
- Allow memory items to be promoted from workflow memory to engineering memory
- Support decay or archival of low-value memory
- Maintain provenance and linkage to the originating workflow or decision

---

## 5. High-Level Structure

```text
Memory Manager
│
├── Workflow Memory Store
├── Engineering Memory Store
├── Asset Registry
├── Memory Writer
├── Memory Retriever
├── Promotion / Demotion Logic
└── Observability & Provenance
```

---

## 6. Key Design Rules

- **Memory never overrides authoritative documentation.** Knowledge (the Knowledge Manager and repository docs) ranks higher; where they conflict, Knowledge wins. The authority hierarchy is defined in `../../20_glossary/glossary.md` §3, which is the single authority for the Knowledge / Memory / Context / Context Pack distinction.
- Memory items carry quality and confidence signals where available.
- Agents do not write arbitrary memory; writing is mediated and structured through `MemoryService.write()`.
- **Memory is consumed through the Context Manager**, not queried directly by an agent — the same rule that applies to Knowledge.
- Retrieval must be explainable: why a particular item surfaced.

### 6.1 Scope for v1

Workflow memory and explicit engineering-memory writes are implemented. **Automatic promotion from workflow memory to engineering memory, decay scoring, and archival are deferred** until there is real usage data to calibrate them — a promotion heuristic invented before any workflows have run would be a guess encoded as architecture. Promotion in v1 is an explicit, audited operation.

---

## 7. Relationship with Other Components

- **Context Manager** is the primary consumer of memory.
- **Knowledge Manager** holds stable, documented knowledge; Memory Manager holds more experiential knowledge.
- **Workflow Engine** can signal important outcomes that should be written to memory.
- **Evaluation / Experiment Engine** can use memory of previous runs to improve future experiments.
- **Capability Packs** may contribute reusable assets through controlled interfaces.

---

## 8. Observability Requirements

Every significant memory operation should record:

- What was written or retrieved
- Source workflow / agent / experiment
- Reason for retrieval (when applicable)
- Timestamp and identifiers

---

## 9. Current Status

This document defines the design baseline for the Memory Manager.

Detailed storage models, retention policies, promotion criteria, and APIs will be refined during implementation.

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Memory Manager Design  
6. Source Code
