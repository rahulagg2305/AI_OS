# Glossary – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Glossary
**Version:** 1.0
**Status:** Approved
**Last Updated:** 2026-07-25

---

## 1. Purpose

AI_OS uses several terms that are close in meaning and easy to conflate — Knowledge versus Memory versus Context, Tool versus Command, Workflow versus Pattern versus Experiment. Because the platform is designed to be continued by AI models reading this repository, an ambiguous vocabulary is a direct source of architectural drift.

Every term below has exactly one meaning in AI_OS. Where a term is commonly used differently elsewhere, that is noted.

**A note on implementation status.** This glossary defines the platform's intended vocabulary — it does not track what is built. Several terms below name concepts with no working implementation yet as of 2026-07-28, verified against source during this audit: **Platform SDK** (§2, 5% built — schema only, no `ai-os-sdk` package); **Trust tag** (§3 — no `trust` field exists anywhere in the Context Manager's `ContextItem`/`SourceRef`); **Monotonic narrowing** (§6 — only the principal term of the intersection is computed; workflow/agent/tool declared permissions are not yet read at authorization time); **Speech Gateway**, **Event Bus**, **Traceability Link**/**Impact analysis** infrastructure, and **Outbox** consumption (all 0% or schema-only). Do not infer a term is built from its presence here. See `../19_roadmap/feature_inventory.md` for per-module status.

---

## 2. Core Platform

**Platform Kernel** — The domain-agnostic runtime core. Contains the Workflow Engine, LLM Gateway, Prompt Engine, Context Manager, retrieval and memory services, Evaluation Engine, Configuration Manager, Manifest Loader, Capability Manager, Security Manager, Quality Gate Engine, Traceability Engine, Event Bus, Observability, and Health & Lifecycle. Never contains domain logic.

**Capability Pack** — An installable, independently versioned unit containing all logic for one domain. Declares everything it provides in `manifest.yaml`. Interacts with the platform only through the Platform SDK. Sometimes shortened to "pack".

**Platform SDK** (`ai-os-sdk`) — The only interface between a pack and the platform. Defines the Protocols, boundary models, error hierarchy, and pack contract test suite.

**Platform Service** — A shared, domain-agnostic service used by the Kernel and by packs: Storage, Search, Document Processing, Notification, Git Integration, Speech Gateway, Caching.

**PackContext** — The object a pack receives at activation. Carries only the capabilities the pack declared and was granted. There is no route from it to the Kernel.

**Composition Root** — `kernel/bootstrap.py`. The single place where the object graph is wired, in explicit order. There is no DI container.

---

## 3. Knowledge, Memory, Context — the four terms most often confused

These are **four distinct things**. The distinction is by *authority and lifetime*, not by storage technology.

| Term | What it is | Authority | Lifetime |
|---|---|---|---|
| **Knowledge** | Stable, documented, authoritative content: the Constitution, architecture documents, specifications, ADRs, coding standards, and per-project requirements and design. Ingested from the repository and approved sources. | **Highest.** Knowledge is the source of truth. | Long-lived, versioned |
| **Memory** | Experiential content derived from what the platform did: outcomes, what worked, what failed, reusable assets, lessons. Two sub-kinds: *workflow memory* (scoped to one run) and *engineering memory* (promoted, long-lived). | **Lower than Knowledge.** Memory never overrides documented Knowledge. | Workflow memory is run-scoped; engineering memory is long-lived with decay/archival |
| **Context** | The assembled, token-budgeted, permission-trimmed bundle handed to one agent for one step. Built by the Context Manager from Knowledge, Memory, Context Packs, workflow state, and user input. | Derived — has no authority of its own | Exists for one step |
| **AI Context Pack** | A curated, versioned bundle of high-signal material (invariants, essential architecture, standards, current state) stored in `ai_context/`, designed to orient any LLM quickly. An *input* to Context assembly, not the same thing as Context. | Derived from Knowledge | Versioned, long-lived |

Shortest form: **Knowledge is what is true. Memory is what happened. A Context Pack is a curated briefing. Context is what one agent sees right now.**

**Retrieval** — The act of searching Knowledge and Memory. Exposed as `RetrievalService`. Hybrid keyword + vector with RRF ranking.

**Index generation** — A monotonically increasing marker for the retrieval index. Pinnable in a query so an experiment retrieves against a fixed index while ingestion continues.

**Provenance** — Where a piece of content came from. Every context item carries it.

**Trust tag** — `trusted` or `untrusted` on every context item. Repository content, ingested documents, tool output, and web content are always `untrusted`. Load-bearing for injection defence.

---

## 4. Execution

**Workflow** — A declared, validated graph of steps that coordinates agents and tools to achieve an outcome. Owned by a Capability Pack; executed by the Workflow Engine.

**Workflow Definition** — The versioned, immutable declaration. Distinct from an instance.

**Workflow Instance** — One execution of a definition, with its own state, event log, and identity.

**Step** — One node in the graph. Typed: `agent`, `tool`, `decision`, `parallel`, `foreach`, `sub_workflow`, `quality_gate`, `human_approval`, `compensate`.

**Workflow State** — Durable state owned exclusively by the Workflow Engine: an append-only event log plus a materialised snapshot.

**Workflow Pattern** — A reusable *shape* of coordination (Sequential, Parallel, Request–Review–Revise, Quality Gate Pipeline, Human-in-the-Loop, Fan-out/Fan-in, Compensation, Experiment). A pattern is a design template; a workflow is a concrete declared instance of one or more patterns. Patterns are documentation; they are not executable objects.

**Agent** — A narrow-responsibility execution unit owned by a pack. Receives a work item plus assembled Context, returns a structured result. Never calls another agent. Stateless between invocations.

**Tool** — The only way an agent causes a side effect. Has a declared input/output schema, required permissions, and a trust tier.

**Command** — A user-facing entry point (CLI or API) exposed by a pack. Distinct from a Tool: a Command is invoked by a *human or client*; a Tool is invoked by an *agent* through the Tool Invoker.

**Trust tier** — `tier1_sandboxed` (untrusted; ephemeral container, no network, no secrets) or `tier2_trusted` (platform operations; canonical-path allowlisted). Declared per tool, validated at load.

**Workspace** — A per-workflow-instance isolated working copy. Never shared between instances.

**Plan artifact** — A schema-conforming output from a planning agent, consumed by a `foreach` step. How dynamic work is achieved without dynamic control flow.

---

## 5. Model Access

**LLM Gateway** — The single component permitted to communicate with a model provider. Handles routing, retries, fallback, budgets, capability negotiation, and all token/cost accounting. Covers generation, tool-using generation, structured output, streaming, and embeddings.

**Provider Adapter** — Translates the neutral Gateway contract into one provider's native API. The only place a provider SDK may be imported.

**Model Alias** — The indirection that makes the platform LLM-agnostic (`reasoning`, `coding-strong`, `fast-cheap`). The only model identifier permitted outside Gateway configuration.

**Provider Capabilities** — The declared matrix of what a routed provider supports (tools, parallel tool calls, structured output, streaming, thinking, effort, prompt caching, context limits, vision).

**Degradation** — What the Gateway does when a request needs a capability the routed provider lacks: faithfully emulate it, or fail explicitly. Never silently drop it. Always recorded.

**Prompt** — A named, versioned, immutable artifact owned by a pack, with a declared variable schema.

**Prompt caching** — Provider-side caching of a stable prompt prefix. Reduces cost without changing model behaviour, because the model still runs.

**Effort** — A provider-supported control over how much reasoning and token spend a request may use (`low` … `max`). Distinct from a budget: effort is a hint to the model, a budget is a ceiling the platform enforces.

**Speech Gateway** — The Speech equivalent of the LLM Gateway: STT, TTS, and wake-word detection behind aliases. Voice packs hold no provider adapters.

---

## 6. Quality and Governance

**Quality Gate** — A machine-evaluated checkpoint with an explicit success criterion, returning a structured result. `blocking` or `warning`. Executed by the Quality Gate Engine; the *consequence* of a failure is decided by the Workflow Engine.

**Human Approval Point** — A declared pause requiring an authorized human decision. Timeout never implies approval.

**Approval class** — The category of an approval (`release`, `architecture`, `security`, …). Granted separately, so approving a release does not imply authority to approve architecture.

**Principal** — An authenticated identity: `user`, `service_account`, or `agent` (which never authenticates and derives authority from its workflow).

**Security Context** — The immutable set of identity, roles, and *effective* permissions for an operation. May only narrow.

**Monotonic narrowing** — `principal ∩ workflow ∩ agent ∩ tool = effective`. Authority only ever shrinks; there is no runtime elevation.

**Permission** — A discrete right in a closed vocabulary, formatted `<resource>:<action>`.

**Audit log** — Append-only, hash-chained record of governance-relevant actions. Separate from telemetry.

---

## 7. Evaluation

**Experiment** — A controlled set of runs of one workflow definition with exactly one deliberately varied dimension (usually the model), everything else pinned.

**Run** — One execution within an experiment, bound to one variant and one replicate index.

**Replicate** — A repeated run of the same variant. Required because a single run of a non-deterministic system is not evidence.

**Run Manifest** — The complete bundle of pinned conditions for a run: definitions and versions, prompt versions, resolved models, parameters, context pack versions, index generation, embedding model version, configuration, Kernel version. What makes a run re-launchable.

**Reproducibility** — Pinned conditions + deterministic platform behaviour + recorded non-determinism. Explicitly **not** "identical output" — see [ADR-0022](../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md).

**Determinism** — Used in AI_OS **only** about platform behaviour (context assembly, ranking, rendering, gate evaluation, cost computation). Never claimed of model output.

**Comparison Report** — Side-by-side variant results with mean and variance, excluding any cache-served run.

---

## 8. Data and Traceability

**Artifact** — A content-addressed stored object, referenced as `sha256:<hex>`. Never inlined into workflow state.

**Traceability Link** — A directional, named relationship between two artifacts (`implements`, `verifies`, `realizes`, `affects`, `contains`, `produced`, `applies_to`), with provenance and confidence.

**Impact analysis** — Answering "what is affected if this changes" by traversing traceability links.

**Event** — An immutable record of something that happened, with `event_id`, `event_type`, `schema_version`, `timestamp`, `source`, trace context, and payload.

**Outbox** — The table where cross-process events are written in the same transaction as the state change that produced them, then relayed. Prevents committed-state-without-event.

**Lease** — A time-bounded claim by a worker on a workflow instance, acquired with `SKIP LOCKED` and reclaimed on expiry.

---

## 9. Terms Deliberately Avoided

To prevent ambiguity, these are **not** used as AI_OS terms:

| Avoided | Use instead | Why |
|---|---|---|
| "Plugin" | Capability Pack | "Plugin" implies a looser, uncontracted extension |
| "Extension" | Capability Pack | Same |
| "Agent swarm" / "agent mesh" | Workflow | Implies direct agent-to-agent communication, which is prohibited |
| "Orchestrator" as a component | Workflow Engine | There is exactly one orchestrator |
| "Task Planner" | Planning agent + `foreach` | No such Kernel component exists ([ADR-0021](../18_decision_log/adr/ADR-0021-declarative-workflows-no-dynamic-task-planner.md)) |
| "Chain" | Workflow | Borrowed from a framework AI_OS does not use |
| "Deterministic output" | Reproducible run | Not achievable for model output |
| "Prompt template" as distinct from "prompt" | Prompt | All prompts are templates with a variable schema |
| "Memory" for retrieval generally | Knowledge, or Retrieval | Memory has the specific meaning in §3 |

---

## 10. Maintenance

Add a term here whenever a new concept enters the architecture. If two documents use one word for two things, that is a defect to be resolved here first, then in those documents.

---

## 11. Related Documents

- [`../19_roadmap/feature_inventory.md`](../19_roadmap/feature_inventory.md) · [`../19_roadmap/implementation_status.md`](../19_roadmap/implementation_status.md) — per-module build status for the concepts defined here
- [`../09_security/security_architecture.md`](../09_security/security_architecture.md) · [`../09_security/authentication_authorization.md`](../09_security/authentication_authorization.md) — the real gap behind §6's "Monotonic narrowing" and §3's "Trust tag"
- [`../03_architecture/capability_framework/capability_pack_contract.md`](../03_architecture/capability_framework/capability_pack_contract.md) — the Platform SDK gate behind §2's "Platform SDK" entry
