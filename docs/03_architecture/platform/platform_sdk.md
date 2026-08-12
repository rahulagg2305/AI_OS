# Platform SDK Specification – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Platform SDK Specification
**Version:** 1.3
**Status:** Approved as a specification — **build in progress; five interfaces now carry binding v1.0.0 reconciliation decisions** (see §1a)
**Last Updated:** 2026-07-29 (`platform_sdk_v1_scope.md` **step 2a** complete: §4.2, §4.3, §5.1, §5.2 and §5.6 each carry a dated **v1.0.0 Reconciliation Decision** block recording whether the specified shape was narrowed to match working code, extended because the real code is richer, deferred, or designed from scratch. **Where a decision block and the surrounding prose disagree, the decision block governs for v1.0.0** and the prose remains the long-term target. Also: step 2 complete — the `AiOsError` hierarchy and shared boundary models are real.)

**Previously:** 2026-07-28 (v1.2 — step 1, packaging scaffold); 2026-07-28 (v1.1 — added Implementation Status and Related Documents); 2026-07-25 (v1.0)

---

## 1. Purpose

The Platform SDK (`ai-os-sdk`, package `ai_os_sdk`) is intended to be the **only** interface between Capability Packs and the AI_OS platform. It defines every contract a pack may depend on, every data model crossing the boundary, and the testing suite that proves compliance.

This document specifies that surface. It is the contract the Kernel must implement and packs must code against.

> **⚠ Read §1a before treating anything below as existing code.** Every Protocol, model, error class, and test suite in this document is a **design specification with no implementing package**. Nothing described here can be imported today.

This document is subordinate to:

1. Project Constitution
2. AI Governance Framework
3. System Architecture
4. Capability Pack Contract
5. Kernel Architecture

Governing decisions: [ADR-0001](../../18_decision_log/adr/ADR-0001-modular-capability-pack-architecture.md), [ADR-0004](../../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md), [ADR-0008](../../18_decision_log/adr/ADR-0008-primary-language-and-runtime.md), [ADR-0010](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md).

---

## 1a. Implementation Status (2026-07-29 — Platform SDK v1.0.0 steps 1, 2, and 2a complete)

**⚠ Read this before treating §4–§10 as the binding contract.** Five interfaces — §4.2 `Agent`, §4.3 `Tool`/`ToolResult`, §5.1 `LLMGateway`, §5.2 `PromptRegistry`, §5.6 `ToolInvoker` — now carry a **v1.0.0 Reconciliation Decision** block recording a binding shape that **deliberately differs from the prose around it**. Those blocks govern what gets built; the prose remains the approved long-term target. They exist because an architecture review (2026-07-29) established that the specified shapes could not be satisfied by any real Kernel object, and that building them as written would have failed at pack-migration time.

**Built:**

- The manifest schema (unchanged) — `../../../platform_sdk/schemas/manifest.schema.json`, real, versioned, actively enforced by the Manifest Loader.
- **A real, installable, importable `ai-os-sdk` package** (step 1). `platform_sdk/` has its own `pyproject.toml`, is a workspace member, ships a `py.typed` marker, and `import ai_os_sdk` succeeds.
- **The §4.4 error taxonomy and the §4.1/§4.2 shared boundary models** (step 2). `ai_os_sdk.errors` holds `ErrorCategory` (all six documented categories), `StructuredError`, and `AiOsError` → `TransientError`/`PermanentError`/`QualityError`/`InfrastructureError`/`BudgetExceededError`/`SecurityError`, each mapping 1:1 onto a `StructuredError`. `ai_os_sdk.models` holds `ArtifactRef`, `TraceContext`, `SecurityContext`, and `StepBudget`. **Consumed by nothing yet.**
- **Binding shape decisions for five interfaces** (step 2a, docs only — the decision blocks named above). No Protocol code exists yet; step 3 is the first to write one.

**Two shape notes worth carrying forward.** `ai_os_sdk.models.TraceContext` is the canonical §4.1 seven-field shape; the Kernel independently holds **two narrower `TraceContext` classes** (`ai_os_kernel.observability.trace`, and `ai_os_kernel.llm_gateway.models:105`), and **both of their docstrings already name this §4.1 shape as the canonical one they are reduced slices of**. Consolidating them is Kernel-side work, not SDK scope. Separately, `StructuredError.trace` is **required** here (§4.4 marks `retry_after_seconds`/`details` nullable and pointedly does not mark `trace`), while the raising `AiOsError` carries it optionally — so a raise site that does not know its trace cannot fabricate one, and the boundary that does know it supplies it at conversion time.

Everything else below remains unbuilt, as detailed next.

**Not built — i.e. everything else in this document:**

- **All 15 Protocol interfaces in §5** (`LLMGateway`, `PromptRegistry`, `ContextService`, `RetrievalService`, `MemoryService`, `ToolInvoker`, `EventBus`, `ConfigService`, `SecretResolver`, `StorageService`, `WorkspaceService`, `Telemetry`, `TraceabilityService`, `QualityGateRegistry`, `SpeechGateway`). None exists as an SDK Protocol yet. **Three of them (`LLMGateway`, `PromptRegistry`, `ToolInvoker`) now have a binding v1.0.0 shape decided** — see their decision blocks in §5.1/§5.2/§5.6 — and are built in steps 4, 5, and 6. Of the rest, `ContextService` contributes boundary models only (step 7), and **eleven are deferred past v1.0.0**, including `SecretResolver`, which was dropped because the one real pack declares no secret permission and §6 grants a `PackContext` attribute only for a declared capability (`platform_sdk_v1_scope.md` §2.3). Several have *unrelated, narrower, Kernel-internal* counterparts that are **not** this interface and are **not** pack-facing — for example `ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway` (real `count_tokens()`/`embed()`/`stream()` since 2026-08-04, each via its own Kernel-local Protocol, not this SDK one), `ai_os_kernel.prompt_engine.catalog`, `ai_os_kernel.context_manager.manager.ContextManager`, `ai_os_kernel.secrets_manager.provider`. Five of the fifteen have no counterpart at any layer, because their whole subsystem is an empty stub package: `MemoryService`, `EventBus`, `TraceabilityService`, `QualityGateRegistry`, and `StorageService`. `SpeechGateway` has no code anywhere. **`ToolInvoker` does not exist in any form** — the closest real thing is the workflow-engine-internal `ToolStepExecutor` + `SandboxedCommandTool`, which is not a pack-facing interface.
- **The remaining §4 boundary models.** `ArtifactRef`, `TraceContext`, `SecurityContext`, and `StepBudget` are **now built** (step 2, see above). Still unbuilt: `ToolResult` (arrives with `ToolInvoker`, step 6) and the `LLMRequest`/`LLMResponse`/`UsageRecord`/`ProviderCapabilities` shapes in §5.1 (step 4). **`AgentRequest`, `AgentResult`, and `ToolRequest` are deliberately deferred past v1.0.0 entirely** — they have no consumer under the narrowed `Agent`/`Tool` Protocols; see §4.2's and §4.3's decision blocks. The Kernel's own internal Pydantic models under `ai_os_kernel.llm_gateway.models` remain Kernel types, not SDK boundary types.
- **The `error_code` catalogue** (§3). The `AiOsError` hierarchy and `StructuredError` themselves are **now built** (step 2), but the stable, catalogued set of `error_code` values this document places in `platform_sdk/errors/` does not exist — populating it needs real producers, which arrive with the Protocols. Every other subsystem still defines unrelated local exceptions (for example `ai_os_kernel/llm_gateway/errors.py`, inheriting from plain `Exception`); migrating them onto the shared hierarchy is Kernel-side work tracked as `../../19_roadmap/feature_inventory.md` module 44, not a Platform SDK step.
- **`PackContext` (§6)** — the object a pack is "handed". No such object exists; nothing constructs one.
- **The `CapabilityPack` Protocol and `PackRegistration` (§7)** as SDK types. The real `software-engineering` pack does expose an entry-point class, but it is typed against Kernel internals, not against an SDK Protocol.
- **SDK semantic versioning enforcement (§8).** Nothing has an SDK version to check, so the Manifest Loader cannot enforce `dependencies.sdkVersion`; that semantic rule is currently unenforceable rather than merely unimplemented.
- **`pack_contract_suite` (§9).** The 9-check compliance suite **does not exist**. No pack runs it, and no pack could. Today the only real validation of a pack is the manifest JSON Schema plus a handful of semantic rules in `ai_os_kernel/manifest_loader/`. In particular, checks 2–9 — entry-point resolution, I/O-model matching, workflow step resolution, `trust_tier` consistency, permission vocabulary, **the forbidden-import check**, prompt existence, and clean activation — are all unenforced.
- **The §10 prohibitions.** They remain the binding rules, but the sentence "Each of these is checked by the contract suite, by lint rules, or by the loader" is currently **false**: there is no contract suite, and no lint rule enforces the import boundary. They are honour-system rules today.

**This is exactly why Capability Packs currently import Kernel internals directly.** The `software-engineering` pack — the platform's own flagship pack — imports `ai_os_kernel.*` in every agent module and in its pipeline composition, because there is no SDK package for it to depend on instead and it genuinely needs a real LLM Gateway, Prompt Engine, and database connection. That is a live, knowing violation of §2 rule 1, §10, and the Capability Pack Contract's "Direct Kernel access is prohibited", recorded as a dated exception in `../capability_framework/capability_pack_contract.md` § Platform Interaction Rules and in each affected module's own docstring. **Scaffolding this document into a real `ai-os-sdk` package is what closes it** — and closing it is the single highest-leverage item this document implies.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table — see rows 18, 27, and 44). Build history: `../../19_roadmap/history/INDEX.md`.

---

## 2. Design Rules

1. **The SDK is the dependency floor.** `ai-os-sdk` depends on no other AI_OS distribution. A pack depending on `ai-os-kernel`, `ai-os-services`, or another pack fails CI ([ADR-0009](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md)).
2. **Interfaces are `Protocol`s.** Structural typing, so adapters need no inheritance from SDK classes.
3. **Every boundary model is a Pydantic v2 model.** Validated on construction, at both ends.
4. **Packs receive capabilities, not the Kernel.** A pack is handed a `PackContext` carrying only what its manifest declared and was granted; anything else is not reachable because the object is absent ([ADR-0010](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md)).
5. **SDK versioning is semantic and enforced.** Packs declare `sdkVersion`; the loader refuses incompatible packs.
6. **No provider SDK, database driver, or HTTP client is re-exported.** Packs never gain transitive access to a provider.

---

## 3. Package Layout

The **intended** layout. None of these packages exists yet — see §1a.

```text
platform_sdk/
├── contracts/          # Protocol definitions (the interfaces below)   — empty directory
├── models/             # Pydantic boundary models                      — empty directory
├── errors/             # AiOsError hierarchy                           — DOES NOT EXIST
├── testing/            # pack_contract_suite, fakes, fixtures          — DOES NOT EXIST
├── utilities/          # ids, hashing, canonical JSON, time            — empty directory
├── prompts/            # (present on disk, undocumented)               — empty directory
└── schemas/
    └── manifest.schema.json    ← the ONLY real file in platform_sdk/
```

Any other document citing `platform_sdk/contracts/<x>.py`, `platform_sdk/errors/`, or `ai_os_sdk.<anything>` is citing a path that does not exist; treat such a citation as a specification reference, not a source reference.

---

## 4. Core Boundary Models

Presented as field contracts. Field names are normative.

### 4.1 Identity and provenance

```text
ArtifactRef        artifact_id: "sha256:<hex>"; media_type; size_bytes; uri
TraceContext       trace_id; span_id; workflow_id?; step_id?; agent_id?;
                   experiment_id?; run_id?; prompt_id?; prompt_version?
SecurityContext    principal_id; principal_type: user|service_account|agent;
                   roles[]; permissions[] (effective, already narrowed);
                   tenant_id (reserved, always "default" in v1)
                   -- immutable; may only be narrowed, never widened
```

> **🔵 DECISION (2026-08-05, `P04-S01-M12-T10`): add `prompt_id`/`prompt_version` to `TraceContext`, additive (§8 minor).** Wiring real call recording (`evaluation.llm_calls`) into the SDK-native agent path found no documented carrier for which prompt an `LLMRequest` rendered — `agent_id`/`prompt_id`/`prompt_version` are required together at the storage layer, but only `agent_id` had a field here. Both new fields are optional, for the identical reason `agent_id` already is (`ai_os_sdk.models.common.TraceContext`'s own docstring). No existing caller is affected.

### 4.2 Agent contract

```text
AgentRequest       agent_id; workflow_id; step_id; inputs (schema-validated);
                   context: AssembledContext; security: SecurityContext;
                   trace: TraceContext; budget: StepBudget; deadline: datetime

AgentResult        status: success|failure|partial;
                   outputs (schema-validated) | error: StructuredError;
                   artifacts: ArtifactRef[]; usage: UsageRecord;
                   traceability_links: TraceabilityLink[]

StepBudget         max_tokens?; max_cost_usd?; max_tool_calls?;
                   max_wall_seconds?
```

An agent implements:

```text
Agent (Protocol)
    agent_id: str
    version: str
    input_model:  type[BaseModel]
    output_model: type[BaseModel]
    async def execute(request: AgentRequest) -> AgentResult
```

Agents are stateless between invocations. Any state persists via Workflow State.

> **🔵 v1.0.0 RECONCILIATION DECISION (2026-07-29): NARROW. The binding v1.0.0 `Agent` Protocol is the existing dict-based Kernel shape, not the shape above.**
>
> ```text
> Agent (Protocol)                      # ai_os_sdk.contracts.agent — v1.0.0
>     output_schema: dict[str, Any]
>     async def execute(inputs: dict[str, Any]) -> dict[str, Any]
> ```
>
> **Why.** Five real agents implement exactly this shape today (`ai_os_kernel/workflow_engine/agent.py:71-73`), and the Workflow Engine is coupled to it in two places that would both have to change: `AgentStepExecutor` calls `agent.execute(inputs_dict)` and validates the returned dict against `agent.output_schema` (`workflow_engine/step_executor.py:165-172`), and `SqlAgentRegistry` gates every dynamically-loaded entrypoint on `isinstance(loaded, Agent)` (`workflow_engine/registry.py:222`). Adopting the shape above would mean changing `AgentStepExecutor`, `SqlAgentRegistry`, `InMemoryAgentRegistry`, `EchoAgent`, all five pack agents, and their tests — real risk to working, proven code (803 passing tests) for a benefit that is deferrable.
>
> **A precision correction to the review that prompted this decision.** `Agent` is `@runtime_checkable`, and a `runtime_checkable` Protocol's `isinstance` check verifies **member presence only, never signatures** — `agent.py:61-68` states this explicitly ("a structural presence check only … not a signature or type check"). So an `AgentRequest`-shaped agent would fail to load specifically because it lacks an attribute *named* `output_schema` (it has `input_model`/`output_model` instead), **not** because of its `execute` signature; the signature mismatch would instead surface as a `TypeError` at first invocation. The conclusion is unchanged, but the coupling is `AgentStepExecutor`'s call convention plus the attribute name, not the Protocol check alone.
>
> **What this costs, recorded rather than glossed.** `SecurityContext`, `StepBudget`, and `TraceContext` cannot reach an agent as **named, typed fields** under this shape; they arrive as entries in the `inputs` dict. This is consistent with what already happens — `AgentStepExecutor` already passes a real `AssembledContext` object under the `"context"` key (`step_executor.py:158-161`), so the dict is already `dict[str, Any]` carrying rich objects, not a flat string map. The cost is lost type safety at that one boundary, not lost capability.
>
> **`AgentRequest`/`AgentResult` are therefore deferred, not built, in v1.0.0.** They have no consumer under the narrowed Protocol. Two of `AgentResult`'s five fields depend on services that do not exist anyway (`artifacts` needs `StorageService`, `traceability_links` needs `TraceabilityService` — both 0%). Introducing the typed request/result pair is a deliberate future **major** SDK version change (§8), scheduled with the Workflow Engine change it requires — not an oversight to be quietly corrected later.
>
> The shape documented above this note remains the approved long-term target. Decision recorded in `platform_sdk_v1_scope.md` step 2a.

### 4.3 Tool contract

```text
ToolRequest        tool_id; inputs; workspace: WorkspaceHandle;
                   security: SecurityContext; trace: TraceContext;
                   timeout_seconds
ToolResult         status: success|failure; outputs | error: StructuredError;
                   artifacts: ArtifactRef[]; stdout_ref?; stderr_ref?;
                   exit_code?; duration_ms

Tool (Protocol)
    tool_id: str
    version: str
    trust_tier: Literal["tier1_sandboxed", "tier2_trusted"]
    required_permissions: frozenset[str]
    input_model / output_model
    async def invoke(request: ToolRequest) -> ToolResult
```

`trust_tier` is validated at pack load. Any tool that executes a command string, compiles, runs tests, installs dependencies, or processes untrusted repository content **must** be `tier1_sandboxed` ([ADR-0016](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md)).

> **🔵 v1.0.0 RECONCILIATION DECISION (2026-07-29): NARROW the `Tool` Protocol; MIXED narrow-and-extend on `ToolResult`; DEFER `ToolRequest`.**
>
> **`Tool` — narrow, for the same reasons as `Agent` (§4.2).** The binding v1.0.0 shape is the existing Kernel one (`workflow_engine/tool.py:65-68`):
>
> ```text
> Tool (Protocol)                       # ai_os_sdk.contracts.tool — v1.0.0
>     trust_tier: TrustTier
>     output_schema: dict[str, Any]
>     async def execute(inputs: dict[str, Any]) -> dict[str, Any]
> ```
>
> Note the method is **`execute`**, not `invoke` as documented above — a difference of *name*, not just signature, so the two are not interchangeable at all. `SqlToolRegistry` gates on `isinstance(loaded, Tool)` and additionally cross-checks the loaded object's `trust_tier` against its `catalog.tools` row (`workflow_engine/registry.py:277-284`), so this shape is load-bearing in the same way `Agent`'s is. `ToolRequest` is deferred alongside `AgentRequest`: it has no consumer under this shape.
>
> **`ToolResult` — this one is *not* purely a narrowing, and the direction differs field by field.** It is the return type of `ToolInvoker.invoke` (§5.6), so unlike `ToolRequest` it is genuinely needed in v1.0.0. Reconciled against what the real sandbox actually produces — `SandboxResult` (`sandbox/models.py:63-68`: `exit_code: int | None`, `stdout: str`, `stderr: str`, `timed_out: bool`, `truncated: bool`, `duration_seconds: float`):
>
> | Documented field | v1.0.0 | Why |
> |---|---|---|
> | `status: success\|failure` | **Kept** | Derivable from `exit_code`/`timed_out`. |
> | `outputs \| error: StructuredError` | **Kept** | `StructuredError` is real as of step 2. |
> | `exit_code?` | **Kept** | Direct from `SandboxResult.exit_code`; `None` exactly when `timed_out`. |
> | `duration_ms` | **Kept** | `SandboxResult.duration_seconds × 1000`. |
> | `stdout_ref?` / `stderr_ref?` | **NARROWED** to inline `stdout: str` / `stderr: str` | A `*_ref` is an `ArtifactRef` into a content-addressed store, and **`StorageService` (§5.10) does not exist** (0% built, deferred — §1a). The sandbox already returns inline strings, and already bounds them (`max_output_bytes` + `truncated`), so inline is safe rather than unbounded. Becomes a ref when `StorageService` is real. |
> | `artifacts: ArtifactRef[]` | **DEFERRED** (absent in v1.0.0) | Same reason: nothing can produce an `ArtifactRef` without `StorageService`. |
> | — | **EXTENDED: `timed_out: bool`** | The spec above has **no way to express a timeout** distinctly from a non-zero exit. `SandboxResult` distinguishes them, and the difference is material to a caller deciding whether to retry. |
> | — | **EXTENDED: `truncated: bool`** | The spec above has **no way to express "output was capped."** A caller parsing truncated stdout as complete output draws a wrong conclusion silently. This is a case where the real Kernel is richer than the specification, not poorer. |
>
> Decision recorded in `platform_sdk_v1_scope.md` step 2a. The `invoke`-named, `ToolRequest`-taking shape above remains the approved long-term target.

### 4.4 Error model

One taxonomy for the whole platform, matching `../workflow/error_handling_retry.md` §3/§8:

```text
StructuredError    error_code: str            # stable, catalogued
                   category: transient | permanent | quality |
                             infrastructure | budget | security
                   message: str               # human-readable, no secrets
                   retriable: bool
                   retry_after_seconds: float | None
                   details: dict | None
                   trace: TraceContext
```

Exception hierarchy: `AiOsError` → `TransientError`, `PermanentError`, `QualityError`, `InfrastructureError`, `BudgetExceededError`, `SecurityError`. Every exception carries an `error_code` and maps 1:1 onto `StructuredError`.

*Specification only; not yet implemented.* No class in that hierarchy exists in the codebase, and neither does the `error_code` catalogue. Each subsystem currently defines unrelated local exceptions in its own `errors.py` (for example `ai_os_kernel/llm_gateway/errors.py`), inheriting from nothing shared. Introducing the shared hierarchy is tracked as its own module (`../../19_roadmap/feature_inventory.md` row 44).

---

## 5. Platform Interfaces

Every interface below is **specified** as a `Protocol` in `ai_os_sdk.contracts`. These are the intended **complete** set of capabilities available to a Capability Pack.

*Specification only; not yet implemented.* `ai_os_sdk` is not an importable package (§1a). **No interface in this section exists as an SDK Protocol.** The table below records what, if anything, exists one layer down — a Kernel-internal type that is narrower, differently shaped, and not pack-facing. It is provided so a reader does not mistake a partial Kernel component for a delivered SDK contract.

| § | Interface | Nearest real code today | Gap |
|---|---|---|---|
| 5.1 | `LLMGateway` | `ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway` | `complete()`, `count_tokens()`, `embed()`, `stream()` all real on this Protocol's own real implementation — the SDK Protocol itself still declares only `complete()`; `capabilities()` exists separately as `CapabilityNegotiator` |
| 5.2 | `PromptRegistry` | `ai_os_kernel.prompt_engine.catalog` (`InMemoryPromptEngine`, `SqlPromptCatalog`) | No version resolution, no `cache_boundary_index` |
| 5.3 | `ContextService` | `ai_os_kernel.context_manager.manager.ContextManager` | 1 of 6 documented sources; no `trust` tagging, no filter/ranker |
| 5.4 | `RetrievalService` | `ai_os_kernel.persistence.knowledge_keyword_search` | Keyword mode only — no `vector`, no `hybrid`, no `index_generation` pinning, no permission predicates |
| 5.5 | `MemoryService` | **Nothing.** `ai_os_kernel/memory_manager/` is a docstring-only stub | Entire subsystem |
| 5.6 | `ToolInvoker` | **Stale row — real since step 6, extended `P02-S05-M18-T03` and `P03-S04-M31-T04`.** `ai_os_sdk.contracts.tool_invoker.ToolInvoker` is a real, implemented Protocol; `ToolInvokerAdapter` now resolves and invokes the platform sandbox shim, three platform Git tools (`platform.git.commit`/`create_branch`/`push`, wrapping the real Git Integration Service), and any manifest-declared `catalog.tools` entry through the real `ToolRegistry` — see §5.6's own decision block below for the full, current picture | `available_tools()` still cannot enumerate pack-declared tools (no such lookup exists on `ToolRegistry`); permission enforcement is real for the pack-grant term only, not the full principal chain; the Git tools accept no credential (no `SecurityContext` reaches this call site). **Correction, 2026-08-11 (`P02-S05-M18-T04`, risk register R-017): from `P02-S05-M18-T03` until that date this row was true of the *mechanism* but false of production.** `ToolInvokerAdapter`'s `registry` parameter defaulted to `None`, and `build_pack_context` — its single production construction site — never passed one, so `SqlToolRegistry` was never constructed anywhere in production and every agent's `context.tools.invoke("<any real tool_id>")` raised `UnknownToolError`. Now genuinely wired for the **agent** path (a real default `SqlToolRegistry`, so a caller cannot silently miss it); deliberately **not** for the tool path, where a tool resolving a tool would let `SqlToolRegistry` re-enter itself unboundedly |
| 5.7 | `EventBus` | **Nothing.** `ai_os_kernel/event_bus/` is a docstring-only stub; the `platform.event_outbox` table exists unused | Entire subsystem |
| 5.8 | `ConfigService` | `ai_os_kernel.configuration_manager.loader.ConfigurationManager` | Not namespaced per pack; 3 of 7 precedence layers; no `flag()` |
| 5.9 | `SecretResolver` | `ai_os_kernel.secrets_manager` (`EnvSecretProvider`, `SecretValue`) | `env` backend only; masking is real, broker/TTL/rotation are not |
| 5.10 | `StorageService` | **Nothing.** No content-addressed artifact store exists | Entire service |
| 5.11 | `WorkspaceService` | **Nothing.** Sandbox temp directories only, per-invocation | Per-workflow-instance isolation is not yet mandatory or enforced |
| 5.12 | `Telemetry` | `ai_os_kernel.observability` (`logging`, `metrics`, `tracing`) | Real OTel spans + 1 metric, console exporters only; not namespaced `aios.pack.*` |
| 5.13 | `TraceabilityService` | **Nothing.** `ai_os_kernel/traceability_engine/` is a docstring-only stub; `trace.artifacts`/`trace.links` tables exist with no writer | Entire subsystem |
| 5.14 | `QualityGateRegistry` | **Nothing.** `ai_os_kernel/quality_gate_engine/` is a docstring-only stub | Entire subsystem; `quality_gate` workflow steps complete as no-ops |
| 5.15 | `SpeechGateway` | **Nothing.** No Speech Gateway code exists | Entire service |

### 5.1 `LLMGateway`

The single route to any model ([ADR-0002](../../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md)).

```text
async def complete(request: LLMRequest) -> LLMResponse
async def stream(request: LLMRequest) -> AsyncIterator[LLMStreamEvent]
async def embed(request: EmbeddingRequest) -> EmbeddingResponse
async def count_tokens(request: LLMRequest) -> int
def capabilities(alias: str) -> ProviderCapabilities
```

```text
LLMRequest         model_alias: str                  # NEVER a literal model id
                   messages: Message[]
                   system: SystemBlock[] | None
                   tools: ToolDefinition[] | None
                   tool_choice: auto|any|none|{tool:name} | None
                   response_format: JsonSchemaFormat | None
                   thinking: adaptive | disabled | None
                   effort: low|medium|high|xhigh|max | None
                   max_output_tokens: int
                   cache_hints: CacheHint[] | None
                   metadata: TraceContext
                   budget: StepBudget | None
                   -- no temperature / top_p / top_k: current models reject them

LLMResponse        content: ContentBlock[]     # text | tool_call | thinking
                   stop_reason: end_turn|max_tokens|tool_use|refusal|pause_turn
                   stop_details: {category, explanation} | None
                   usage: UsageRecord
                   provider: str; model_id: str; model_version: str
                   served_from_cache: bool

UsageRecord        input_tokens; output_tokens; cache_read_tokens;
                   cache_write_tokens; cost_usd; latency_ms;
                   provider; model_id; retries; fallback_used: bool

ProviderCapabilities
                   supports_tools; supports_parallel_tool_calls;
                   supports_structured_output; supports_streaming;
                   supports_thinking; supports_effort;
                   supports_prompt_caching; max_input_tokens;
                   max_output_tokens; supports_vision
```

**Degradation rules.** If a request uses a capability the routed provider lacks, the Gateway either (a) emulates it where faithful emulation is possible — for example structured output via a forced single-tool call — or (b) fails with `PermanentError(error_code="llm.capability_unsupported")`. It never silently drops a requested capability. Every degradation is recorded on the response and in telemetry, because a silent downgrade would corrupt cross-model comparison.

**Prohibited:** literal model IDs in pack code; any direct provider import; any HTTP call to a provider endpoint.

> **🔵 v1.0.0 RECONCILIATION DECISION (2026-07-29): NARROW the method set to 2 of 5; EXTEND `ProviderCapabilities` to the real 13 fields.**
>
> **Methods — narrow to what exists.** The binding v1.0.0 Protocol is:
>
> ```text
> LLMGateway (Protocol)                 # ai_os_sdk.contracts.llm_gateway — v1.0.0
>     async def complete(request: LLMRequest) -> LLMResponse
>     def capabilities(alias: str) -> ProviderCapabilities
> ```
>
> `stream()`, `embed()`, and `count_tokens()` remain **deferred from this SDK-level Protocol specifically**, independent of what the Kernel itself has since built: `DispatchingLLMGateway.complete()` (`llm_gateway/gateway.py:358`) and `.capabilities()` (`:337`) are still the only two methods this Protocol declares. **Updated 2026-08-04:** the Kernel side is no longer "nothing else" — all three are now genuinely implemented: `count_tokens()` (`P02-S02-M06-T10`, Anthropic's real endpoint), `embed()` (`P02-S02-M06-T09`, `local`'s real OpenAI-compatible endpoint — Anthropic's own API has no embeddings endpoint at all), and `stream()` (`P02-S02-M06-T08`, Anthropic's real streaming endpoint) — each dispatched via its own new, Kernel-local Protocol (`TokenCounter`/`Embedder`/`Streamer`), not this SDK Protocol. Declaring any of the three directly on *this* Protocol would still ship a method not every real adapter can satisfy — worse than absent, because a pack could type-check against it and fail at runtime regardless of which Kernel adapter answers. Adding one here later, once ready for pack-facing exposure, is its own, separate **minor** bump (§8, a new Protocol method is additive for callers).
>
> Note that the Kernel's own internal `LLMGateway` Protocol (`gateway.py:90`) declares only `complete()` — `capabilities()` lives on the concrete `DispatchingLLMGateway`. The SDK Protocol is therefore deliberately one method wider than the Kernel's internal Protocol and exactly as wide as the concrete class step 6a's adapter will wrap. That is intentional, not an inconsistency.
>
> **`ProviderCapabilities` — extend to the real shape.** The 10-field list above is **incomplete**: the real, working `ProviderCapabilities` (`llm_gateway/capability_negotiator.py:98-109`) carries **13** fields, and its own docstring already records this document as the discrepancy it "implements past." The three fields missing above are `supports_strict_tools`, `prompt_cache_min_tokens: int | None`, and `accepts_sampling_params`. The 13-field shape — which matches `llm_gateway.md` §6, this document's own cited source — is binding for v1.0.0. `prompt_cache_min_tokens` is additionally validated against `supports_prompt_caching` by a real model validator, so the two cannot disagree.
>
> **One shape note carried over.** `capabilities(alias)` is documented above as keyed by alias, but the real `StaticCapabilityNegotiator` resolves alias → model id through the `Router` first, because a capability is a fact about the *model*, not the alias string (`capability_negotiator.py:24-33`, the same reasoning that keys `ModelPricing` by model id). The SDK keeps the documented `alias` parameter — a pack must never see a model id (§10) — and the adapter performs the resolution behind it.
>
> Decision recorded in `platform_sdk_v1_scope.md` step 2a.

### 5.2 `PromptRegistry`

```text
async def render(prompt_id, variables, version=None) -> RenderedPrompt
async def get(prompt_id, version=None) -> PromptDefinition

RenderedPrompt     prompt_id; version; content; variables_used;
                   cache_boundary_index?   # prefix/suffix split for caching
```

Prompts are versioned pack assets. Rendering validates variables against the prompt's declared `input_schema`. The rendered result records `prompt_id` + `version` for the run manifest ([ADR-0022](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md)).

> **🔵 v1.0.0 RECONCILIATION DECISION (2026-07-29): KEEP the documented keyword call style (reject the Kernel's request-object envelope for the pack-facing API); NARROW `version` to required; DEFER `get()` and two `RenderedPrompt` fields.**
>
> ```text
> PromptRegistry (Protocol)             # ai_os_sdk.contracts.prompt_registry — v1.0.0
>     async def render(prompt_id: str, variables: dict, *, version: str) -> RenderedPrompt
>
> RenderedPrompt     prompt_id; version; content        # v1.0.0
> ```
>
> **Call style — keep the documented one, do not adopt the Kernel's.** The real `PromptEngine.render` takes a `PromptRenderRequest` envelope (`prompt_engine/renderer.py:79`, `prompt_engine/models.py:56-63`). This is the one place in this reconciliation where the **documented shape is the better one going forward**, and the reason is audience: the Kernel's envelope style suits internal seams that pass requests between components, whereas this is a *pack-facing* API whose caller writes one line to render one prompt. `await prompts.render("requirements.analyze", {"requirement": x}, version="0.1.0")` is materially clearer than constructing a request object to pass one field of real content. The adapter conversion in step 6a is three lines, and it is the right place for that cost to sit — a Protocol should be shaped for its caller, not for the convenience of the thing implementing it (ADR-0004, interface-driven design). This is the deliberate exception to this step's general "prefer the working shape" bias.
>
> **`version` — narrow to required.** Documented as `version=None`, which implies the engine resolves a default. It cannot: version resolution is the Version Manager / Prompt Resolver's job (`prompt_engine.md` §5, §9), and `prompt_engine/models.py`'s own docstring states plainly why `version` is required in the real implementation — *"nothing here silently picks a version on the caller's behalf."* An SDK that accepted `version=None` would have to either fail or invent a choice. Requiring it now and relaxing it later is a **backward-compatible** change for every existing caller (§8), so the strict direction is the safe one; the reverse is not.
>
> **`get() -> PromptDefinition` — deferred.** No implementation exists at any layer: `SqlPromptCatalog` exposes `render()` and nothing else (`prompt_engine/catalog.py:65`). `PromptDefinition` is the *stored* §6 Prompt Contract (name, owner, template, `input_schema`, tags, metadata); `catalog.prompts` holds those columns but has no definition-fetch reader. Nothing in the one real pack calls anything like it.
>
> **`RenderedPrompt` — `variables_used` and `cache_boundary_index?` deferred.** The real `PromptRenderResponse` carries `prompt_id`, `version`, `content` only (`prompt_engine/models.py:81-89`). `cache_boundary_index` requires the Prompt Cache Planner ([ADR-0025](../../18_decision_log/adr/ADR-0025-caching-strategy.md), unbuilt); `variables_used` has no producer. Both are additive later (minor bump).
>
> Decision recorded in `platform_sdk_v1_scope.md` step 2a.

### 5.3 `ContextService`

The only route to knowledge and memory. Packs never query stores directly.

```text
async def assemble(request: ContextRequest) -> AssembledContext

ContextRequest     workflow_id; step_id; agent_id;
                   required_types: ContextType[]   # requirements, architecture,
                                                   # standards, prior_outputs,
                                                   # code, patterns, memory
                   query: str | None
                   token_budget: int
                   filters: dict | None

AssembledContext   items: ContextItem[]; total_tokens; sources_queried[];
                   items_excluded_count; assembly_id; index_generation

ContextItem        content; provenance: SourceRef; relevance_score;
                   token_count;
                   trust: Literal["trusted", "untrusted"]
```

**`trust` is mandatory and load-bearing.** Repository content, ingested documents, tool output, and web content are always `untrusted`. The Prompt Engine wraps untrusted items in explicit data boundaries, and untrusted content can never confer authority ([ADR-0016](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md)).

Context assembly is deterministic for a given request, index generation, and embedding model version.

> **🔵 v1.0.0 RECONCILIATION DECISION (2026-07-29): NARROW `ContextRequest` and `AssembledContext` to the real, already-reduced Kernel shape; KEEP `ContextItem` (already full parity); DESIGN `SourceRef` (this section names no fields for it); NARROW `SourceType` to the one real resolver. Boundary models only — no working `.assemble()` behind the Protocol.**
>
> ```text
> ContextService (Protocol)              # ai_os_sdk.contracts.context_service — v1.0.0
>     async def assemble(request: ContextRequest) -> AssembledContext
>
> ContextRequest     workflow_id: str; step_id: str; agent_id: str | None = None;
>                    token_budget: int | None = None   # gt=0 when set
>
> AssembledContext   items: ContextItem[]; total_tokens: int;
>                    sources_queried: SourceType[]; items_excluded_count: int;
>                    assembly_id: str
>
> ContextItem        content: str; provenance: SourceRef; relevance_score: float;
>                    token_count: int; trust: Literal["trusted", "untrusted"]
>
> SourceRef          source_type: SourceType; identifier: str
>
> SourceType         WORKFLOW_STATE = "workflow_state"   # the only real member
> ```
>
> **Why this reconciliation exists at all, discovered rather than assumed.** No agent calls `.assemble()` today — `AgentStepExecutor` already assembles context itself and hands the result to an agent via `AgentRequest.context`, per `agent_architecture.md`'s Invocation Lifecycle — so `ContextService`'s own method has no real caller to reconcile against, the same situation `PromptRegistry`/`ToolInvoker` were in. But two real pack agents (`agents/documentation.py`, `agents/verification.py`) do import the real Kernel's `AssembledContext`/`ContextItem`/`SourceRef` today, for type annotation — so unlike those two from-scratch designs, a real, already-reduced Kernel shape exists here to reconcile against, and building the SDK's boundary models without checking it against that real shape first would have been exactly the "invented architecture" this project's documentation-first discipline exists to avoid.
>
> **`ContextRequest`**: this section's own documented shape (above) carries `required_types: ContextType[]`, `query: str | None`, and `filters: dict | None` in addition to the four kept. `ai_os_kernel.context_manager.models.ContextRequest` carries only the latter four — its own docstring explains why: `required_types` has no declared source anywhere in this codebase (`workflow_architecture.md`'s Step Contract names no field for which context types a step needs), and no experiment/query mechanism exists to back `query`/`filters` either. Narrowed to match; populating the other three with an unused default would reintroduce the placeholder architecture the Kernel's own model already refuses to be.
>
> **`AssembledContext`**: the documented shape (above) adds `index_generation`. The real Kernel model omits it because no retrieval index exists anywhere in this codebase yet (no Knowledge Manager, no Memory Manager) — `index_generation` exists to pin one for reproducibility (ADR-0022), and a fabricated value would misrepresent a guarantee this slice cannot provide. Narrowed to match, for the identical, re-verified reason.
>
> **`ContextItem`**: the real Kernel model already implements this section's full documented shape verbatim — kept as-is.
>
> **`SourceRef`**: this section names no fields for it at all — nothing to reconcile against, the same "design, not narrow or extend" situation §5.6 was in. Kept at the real Kernel's own design (`source_type`/`identifier`, no `version`) for the identical, verified reason its own docstring gives: Workflow State has no versioning concept, and an unused field for a capability that does not exist yet would be a placeholder.
>
> **`SourceType`**: this section (§4) documents five source resolvers; the real Kernel enum has exactly one real member. Narrowed to that one; a future resolver adds its own member additively.
>
> Landed in `ai_os_sdk.models.context` (the four boundary models) and `ai_os_sdk.contracts.context_service` (the Protocol) — `platform_sdk_v1_scope.md` step 7. Structural compatibility is proven against the real, already-working `ai_os_kernel.context_manager.manager.DefaultContextManager` via `isinstance` — the same discipline already applied to `Agent`/`Tool`/`LLMGateway` — even though no Kernel-side adapter wraps it (no real caller to justify one yet).

### 5.4 `RetrievalService`

Lower-level search for packs that need it (primarily Project Intelligence). Consolidates knowledge and memory behind one seam.

```text
async def search(request: SearchRequest) -> SearchResults

SearchRequest      query; mode: keyword|vector|hybrid;
                   sources: SourceType[]; filters; limit;
                   index_generation: str | None   # pin for reproducibility
```

Results are permission-trimmed by SQL predicate, never post-filtered.

### 5.5 `MemoryService`

```text
async def write(item: MemoryWrite) -> MemoryRef
async def recall(request: MemoryQuery) -> MemoryItem[]
```

Writes are structured and mediated; a pack cannot write free-form memory. Memory never overrides authoritative documentation. Promotion of workflow memory to engineering memory is a platform decision, not a pack decision.

### 5.6 `ToolInvoker`

```text
async def invoke(tool_id, inputs, *, timeout=None) -> ToolResult
def available_tools() -> ToolDescriptor[]
```

Enforces permissions, applies the trust tier, and records the invocation. An agent may not execute a side effect by any other means.

> **🔵 v1.0.0 RECONCILIATION DECISION (2026-07-29): DESIGN (neither narrow nor extend — nothing exists to reconcile against). The documented signature is KEPT, and grounded in a platform-provided tool id.**
>
> ```text
> ToolInvoker (Protocol)                # ai_os_sdk.contracts.tool_invoker — v1.0.0
>     async def invoke(tool_id: str, inputs: dict, *, timeout_seconds: float | None = None) -> ToolResult
>     def available_tools() -> tuple[ToolDescriptor, ...]
>
> ToolDescriptor     tool_id; trust_tier; input_schema; output_schema
> ```
>
> **The problem this design had to solve.** The documented signature is a *registry lookup* — invoke a named tool with varying inputs. Two facts made that look unimplementable, and both were verified:
>
> 1. **The one real pack declares zero tools.** Its manifest declares `permissions: [llm:invoke, sandbox:execute]` and no `tools:` entries at all (`capability_packs/software-engineering/manifest.yaml:71-73`), so a pack-tool registry has nothing to resolve and `available_tools()` would return an empty tuple.
> 2. **The one real tool ignores its own inputs.** `SandboxedCommandTool.execute(inputs)` never reads `inputs` (`workflow_engine/sandboxed_tool.py:110-118`) — the command, working directory, timeout, and output cap are all baked in at construction. The three sandbox-using agents therefore construct a fresh tool per call (`agents/build.py:324`, `agents/verification.py:265`) rather than invoking a registered one.
>
> **The resolution: the sandbox runner becomes a *platform-provided* tool with a well-known id**, and the command moves from constructor into `inputs`:
>
> ```text
> tool_id: "platform.sandbox.run_command"        trust_tier: tier1_sandboxed
> inputs:  command: list[str]                    (required)
>          working_directory: str                (required, workspace-relative)
>          timeout_seconds: float                (required)
>          max_output_bytes: int                 (required)
>          env: dict[str, str] | None
>          stdin: str | None
> returns: ToolResult                            (§4.3, as reconciled there)
> ```
>
> **Why this is better than both alternatives.** It keeps the documented Protocol signature intact rather than inventing a differently-named interface for the same capability; it gives `available_tools()` a real, non-empty answer (one entry in v1.0.0); and passing the command through `inputs` **fixes the ignored-`inputs` wart** rather than propagating it — the current constructor-baking is precisely why `invoke(tool_id, inputs)` looked like a poor fit. It also serves the pack's actual declared permission (`sandbox:execute`) through the interface that permission is meant to gate.
>
> **What step 6a's adapter implements.** The Kernel-side `ToolInvoker` adapter's `platform.sandbox.run_command` path is built **directly over `SandboxExecutor`** (`sandbox/executor.py:151-160`), *not* over the dict-based `Tool` Protocol — routing it through a dict-returning `Tool` would mean serialising a typed `SandboxResult` into a dict and re-parsing it, losing the `timed_out`/`truncated` distinctions §4.3 was just extended to preserve.
>
> **Updated (`P02-S05-M18-T03`): the two paths are no longer disjoint — any other `tool_id` now genuinely resolves through a real `ToolRegistry`.** `ToolInvokerAdapter`, constructed with an optional `registry`, resolves a non-shim `tool_id` through the Kernel's own `workflow_engine.registry.ToolRegistry` (the identical `SqlToolRegistry` a `tool`-type workflow step already uses — same `catalog.tools` lookup, same pack-activation gate, same permission-grant check), applies the identical `tier1_sandboxed`-must-be-sandbox-backed guard `ToolStepExecutor` already enforces, and invokes the resolved `Tool` directly with the caller's real `inputs` — no dict round-trip concern here, since `Tool.execute()` already returns a plain `dict[str, Any]`, unlike `SandboxExecutor.execute()`'s typed result. `available_tools()` is unchanged: `ToolRegistry` exposes only a single-id `resolve_tool()`, no "list every resolvable id" capability, so it still cannot enumerate pack-declared tools — a real, disclosed, distinct gap from resolution itself.
>
> **Permission enforcement is real for this path, not yet for the principal.** "Enforces permissions" above requires the full monotonic-narrowing chain, which still computes only its principal term (`security_manager/models.py`'s own docstring; `authentication_authorization.md`'s Implementation Status) — no `SecurityContext` reaches this adapter at all. What *is* real, as of `P02-S05-M13-T08`: a registry-resolved tool whose own declared permissions exceed its pack's manifest grant is refused before it can ever be invoked through this path.
>
> **Updated (2026-08-02, `P03-S04-M31-T04`): three more platform-provided tool ids, identical shape.** `platform.git.commit`/`platform.git.create_branch`/`platform.git.push` follow the exact same "well-known id, real parameters moved into `inputs`" pattern `platform.sandbox.run_command` established — the real Git Integration Service (`P03-S01-M24-T01`) genuinely needs Kernel-internal infrastructure (a database-backed, hash-chained audit log) no pack-facing `PackContext` exposes, so this is the shim path, not the registry-resolved one. `ToolInvokerAdapter` takes an optional `git_service` (unchanged behaviour when absent, the identical shape `registry` already established); `available_tools()` includes the three descriptors only when one is actually injected. Proven end to end: a real `invoke()` call reaches the real `GitIntegrationService`, the real `SandboxExecutor`, and a real `git` subprocess — commit/branch/push independently verified by reading the real repository/remote back, and a protected-branch push refused before any subprocess runs, remote untouched. Deliberately **no credential support in this tool's own input schema** — resolving a `secret://` reference needs a real `SecurityContext` this call site has none of (the identical, already-disclosed gap this section's own "not yet for the principal" paragraph names), so this tool pushes only to a remote that needs no credential; a real, disclosed, deferred scope decision.
>
> Decision recorded in `platform_sdk_v1_scope.md` step 2a.

### 5.7 `EventBus`

```text
async def publish(event: Event) -> None
def subscribe(event_type: str, handler: EventHandler) -> Subscription

Event              event_id; event_type; schema_version; timestamp;
                   source; trace: TraceContext; payload
```

A pack may publish and subscribe only to event types declared in its manifest. Delivery is at-least-once; handlers must be idempotent on `event_id` ([ADR-0012](../../18_decision_log/adr/ADR-0012-event-bus.md)).

### 5.8 `ConfigService`

```text
def get(key: str, model: type[T]) -> T          # typed and validated
def flag(name: str, default: bool = False) -> bool
```

Namespaced to the pack. A pack reads only its own namespace plus explicitly shared platform keys, and never reads a file from disk directly.

### 5.9 `SecretResolver`

```text
async def resolve(reference: str) -> SecretValue
```

Accepts only `secret://…` references the pack declared. `SecretValue.__str__` and `__repr__` return `***`; the raw value requires an explicit accessor. Never available inside a Tier 1 sandbox ([ADR-0024](../../18_decision_log/adr/ADR-0024-secrets-management-backend.md)).

### 5.10 `StorageService`

```text
async def put(content: bytes | AsyncIterator[bytes], media_type) -> ArtifactRef
async def get(ref: ArtifactRef) -> AsyncIterator[bytes]
async def exists(ref: ArtifactRef) -> bool
```

Content-addressed. Artifacts are referenced from workflow state, never embedded in it.

### 5.11 `WorkspaceService`

```text
async def acquire(workflow_id) -> WorkspaceHandle
WorkspaceHandle    workspace_id; root_path; is_writable
```

Workspaces are **isolated per workflow instance** — mandatory, not best-effort. Two concurrent workflows never share a working copy, which is what prevents concurrent-write corruption in parallel and fan-out patterns.

### 5.12 `Telemetry`

```text
def logger(name: str) -> BoundLogger        # structlog, trace-context bound
def counter(name, unit, description) -> Counter
def histogram(name, unit, description) -> Histogram
def span(name, attributes=None) -> AsyncContextManager[Span]
```

Metric names are namespaced `aios.pack.<pack_id>.<metric>`. Secrets, credentials, raw prompt bodies containing customer source, and personal data must never be emitted ([ADR-0017](../../18_decision_log/adr/ADR-0017-observability-stack.md)).

### 5.13 `TraceabilityService`

```text
async def link(link: TraceabilityLink) -> None
async def query(request: TraceabilityQuery) -> TraceabilityResult

TraceabilityLink   source_type; source_id; relationship;
                   target_type; target_id; confidence; provenance
```

Links are created explicitly, never inferred silently.

### 5.14 `QualityGateRegistry`

```text
def register(gate: QualityGate) -> None      # at pack load only

QualityGate (Protocol)
    gate_id; version; severity: blocking|warning
    async def evaluate(context: GateContext) -> GateResult

GateResult         gate_id; status: pass|fail|warning|error;
                   metrics: dict[str, float]; messages[];
                   duration_ms; details
```

A pack-contributed gate returns a result; it never decides workflow consequence. The Workflow Engine owns that ([ADR-0006](../../18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md)).

### 5.15 `SpeechGateway`

Available only to packs declaring speech permissions ([ADR-0019](../../18_decision_log/adr/ADR-0019-speech-gateway.md)).

```text
async def transcribe(audio, options) -> Transcript
async def synthesize(text, voice_alias) -> AudioRef
async def detect_wake_word(stream) -> AsyncIterator[WakeWordEvent]
```

Selection is by alias. A `local_only` policy restricts routing to local adapters.

---

## 6. `PackContext`

What a pack actually receives. Attributes are present **only** if the manifest declared the corresponding capability and it was granted.

```text
PackContext
    pack_id: str
    pack_version: str
    llm:            LLMGateway
    prompts:        PromptRegistry
    context:        ContextService
    retrieval:      RetrievalService | None
    memory:         MemoryService | None
    tools:          ToolInvoker
    events:         EventBus | None
    config:         ConfigService
    secrets:        SecretResolver | None
    storage:        StorageService | None
    workspace:      WorkspaceService | None
    telemetry:      Telemetry
    traceability:   TraceabilityService | None
    gates:          QualityGateRegistry
    speech:         SpeechGateway | None
```

There is no `kernel` attribute, no `db`, no `http`, and no escape hatch. A capability a pack did not declare is absent from the object.

**Real as of `platform_sdk_v1_scope.md` steps 6b/7, in `ai_os_sdk.contracts.capability_pack.PackContext`:** `pack_id`/`pack_version` plus `llm`/`prompts`/`tools`, each `| None`, granted per `build_pack_context`'s own permission-gating (`llm:invoke` for the first two together, `sandbox:execute` for the third) — see that function's own docstring for the full reasoning, including why `llm:invoke` covers both `llm` and `prompts`. **One honest simplification, not yet closed:** a Pydantic field defaulting to `None` when not granted is not quite this section's own literal "absent from the object" — that would require a non-fixed-schema container this codebase does not have yet. The other eleven attributes above are absent as *fields entirely*, matching the literal rule exactly, since nothing real backs any of them.

---

## 7. Pack Entry Point

Every pack exposes one entry point, registered under `ai_os.capability_packs` ([ADR-0009](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md)):

```text
CapabilityPack (Protocol)
    pack_id: str
    version: str
    async def activate(context: PackContext) -> PackRegistration
    async def deactivate() -> None
    async def health() -> HealthReport

PackRegistration   agents: dict[str, Agent]
                   tools: dict[str, Tool]
                   workflows: dict[str, WorkflowDefinition]
                   gates: dict[str, QualityGate]
                   commands: dict[str, Command]
```

`activate` must be idempotent and must not perform long-running work; heavy initialisation belongs in the first invocation or a declared warm-up step. Everything returned must match the manifest declaration exactly — a mismatch fails activation.

**Real as of `platform_sdk_v1_scope.md` step 7, in `ai_os_sdk.contracts.capability_pack`:** `CapabilityPack`/`PackContext`/`PackRegistration`/`HealthReport`, relocated additively from their prior Kernel-side home (`ai_os_kernel.capability_manager.pack_contract`, now a compatibility re-export). `PackRegistration` is reduced to `agents`/`tools` only — the one real pack declares no workflows, gates, or commands of its own, and those fields are added the same additive way once a pack that provides one exists. `CapabilityPack` is deliberately **not** `@runtime_checkable`: nothing in this codebase yet loads and `isinstance`-checks an `entryPoint` at runtime (`SqlPackLifecycleRepository` only flips `catalog.packs.state`; nothing calls `activate()` yet), so there is no real caller to justify one.

---

## 8. Compatibility and Versioning

- The SDK follows semantic versioning. Packs declare `dependencies.sdkVersion` as a range.
- **Major** — a Protocol method is removed or its signature changes incompatibly; a required model field is added.
- **Minor** — a new Protocol, a new optional field, a new permission.
- **Patch** — documentation and non-behavioural fixes.
- Deprecations are announced one minor version before removal, emit a warning, and are listed in the SDK CHANGELOG.
- The Manifest Loader refuses a pack whose `sdkVersion` range excludes the running SDK, and refuses a pack whose `compatibility.minKernelVersion` exceeds the running Kernel.

---

## 9. Compliance Testing

`ai_os_sdk.testing.pack_contract_suite` is **specified as** a pytest suite every pack must run and pass ([ADR-0015](../../18_decision_log/adr/ADR-0015-testing-and-ci.md)). It is to verify:

1. `manifest.yaml` validates against the published JSON Schema.
2. Every declared agent, tool, workflow, gate, and command resolves and is importable.
3. Declared I/O models match the implementations' `input_model` / `output_model`.
4. Every workflow's step references resolve; the graph is acyclic where required.
5. `trust_tier` declarations are consistent with what each tool does.
6. Requested permissions are in the closed vocabulary.
7. **No forbidden imports** — no provider SDK, no `ai_os_kernel`, no other pack, no database driver, no HTTP client to a provider.
8. Prompts referenced by agents exist at the declared versions.
9. Activation and deactivation are clean (no dangling registrations).

A pack that does not pass this suite is not compliant and is not loadable.

*Specification only; not yet implemented.* **`pack_contract_suite` does not exist** — neither the module nor the `platform_sdk/testing/` directory that would hold it. No pack has ever run it. Today the only real gate on a pack is check 1 (manifest validation against `../../../platform_sdk/schemas/manifest.schema.json`, genuinely enforced by `ai_os_kernel/manifest_loader/`) plus a few of the semantic rules in `../capability_framework/manifest_schema.md` § Validation Rules. **Checks 2–9 are unenforced**, including check 7 (forbidden imports) — which is precisely why the live direct-Kernel-import exception in §1a went undetected by tooling and had to be recorded by hand. The sentence "A pack that does not pass this suite is not loadable" therefore describes the intended gate, not a gate that operates. Building this suite is the mechanism that would make §10's prohibitions enforceable rather than advisory.

---

## 10. Prohibited in Pack Code

- Importing any provider SDK, or any transitive route to one.
- Importing `ai_os_kernel`, `ai_os_services`, or another pack.
- Direct database, Redis, or filesystem access outside `WorkspaceService` and `StorageService`.
- Literal model IDs, literal secrets, or literal absolute paths.
- Agent-to-agent invocation, in any form.
- Constructing a `SecurityContext`, or mutating one.
- Registering components not declared in the manifest.
- Executing untrusted code outside a Tier 1 sandbox.

Each of these is **intended to be** checked by the contract suite, by lint rules, or by the loader.

*Specification only; not yet implemented.* None of these prohibitions is currently machine-checked. There is no contract suite (§9), no import-boundary lint rule, and the loader checks only the manifest. They remain binding rules on every pack author; they are enforced by review, not by tooling. The first of them — "Importing `ai_os_kernel`" — is knowingly violated today by the `software-engineering` pack (§1a).

---

## 11. Current Status

**Updated 2026-07-29 — stale since this section was first written before step 1; corrected here rather than left describing a package that has since become real.** `platform_sdk/` is a real, installable `ai-os-sdk` PEP 621 distribution, a workspace member (`platform_sdk_v1_scope.md` step 1). §4.4's `AiOsError` hierarchy and shared boundary models (step 2), `Agent`/`Tool` (step 3), `LLMGateway` (step 4), `PromptRegistry` (step 5), `ToolInvoker` (step 6), the `PackContextReceiver` injection mechanism (step 6b), and `ContextService`'s boundary models plus the full `CapabilityPack`/`PackContext`/`PackRegistration`/`HealthReport` entry-point contract (step 7) all exist on disk and are importable today — see each section's own dated *v1.0.0 Reconciliation Decision* block above for the binding shape, which governs over this document's own un-dated prose wherever the two disagree. **Still specification only, with no implementing package, for the eleven interfaces §2's own inventory lists as deferred past v1.0.0** (`RetrievalService`, `MemoryService`, `EventBus`, `ConfigService`, `SecretResolver`, `StorageService`, `WorkspaceService`, `Telemetry`, `TraceabilityService`, `QualityGateRegistry`, `SpeechGateway`) — those sections' signatures remain prose only until a future step builds them.

Every change to a real Protocol here requires an SDK version increment and, where behaviour changes, an ADR — unchanged from this section's original rule.

**Concrete next gap, and what would settle it:** `platform_sdk_v1_scope.md` step 8 — `pack_contract_suite` check 7 (forbidden imports) plus a documented, expiring waiver for the still-unmigrated Software Engineering pack, so CI stays green through the migration steps (9–13) and the waiver is removed at step 14.

---

## 12. Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. System Architecture
4. Capability Pack Contract
5. Architecture Decision Records
6. Platform SDK Specification (this document)
7. Source Code

---

## 13. Related Documents

**Governing ADRs**

- [ADR-0001 — Modular Capability Pack Architecture](../../18_decision_log/adr/ADR-0001-modular-capability-pack-architecture.md) (the pack boundary this SDK exists to enforce)
- [ADR-0004 — Interface-driven and configuration-over-code](../../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md)
- [ADR-0008 — Primary language and runtime](../../18_decision_log/adr/ADR-0008-primary-language-and-runtime.md) (`Protocol` + Pydantic v2)
- [ADR-0009 — Packaging and dependency management](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md) (the dependency floor in §2, entry points in §7)
- [ADR-0010 — Composition and dependency injection](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md) (`PackContext` in §6)
- [ADR-0002](../../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md) (§5.1) · [ADR-0006](../../18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md) (§5.14) · [ADR-0012](../../18_decision_log/adr/ADR-0012-event-bus.md) (§5.7) · [ADR-0015](../../18_decision_log/adr/ADR-0015-testing-and-ci.md) (§9) · [ADR-0016](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md) (§4.3, §5.3) · [ADR-0017](../../18_decision_log/adr/ADR-0017-observability-stack.md) (§5.12) · [ADR-0019](../../18_decision_log/adr/ADR-0019-speech-gateway.md) (§5.15) · [ADR-0022](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md) (§5.2) · [ADR-0024](../../18_decision_log/adr/ADR-0024-secrets-management-backend.md) (§5.9)
- Full index: `../../18_decision_log/README.md`

**Architecture**

- `system_architecture.md` — where the SDK sits in the layer stack
- `../capability_framework/capability_pack_contract.md` — the pack side of this contract, and the dated direct-Kernel-import exception
- `../capability_framework/manifest_schema.md` — §8's `sdkVersion`/`minKernelVersion` rules, and the real schema this document's one implemented file holds
- `../kernel/kernel_architecture.md` — the side that must implement these Protocols
- `../workflow/error_handling_retry.md` — §4.4's taxonomy, stated once for the whole platform
- `../agents/agent_architecture.md` — the consumer of §4.2
- `../services/` — the services behind §5.10, §5.11, §5.4 (all unimplemented)
- `technology_stack.md` — the technologies these contracts are built on

**Machine-readable artifacts**

- `../../../platform_sdk/schemas/manifest.schema.json` — the only real file this document's package contains
- `../../../capability_packs/software-engineering/manifest.yaml` — the one real pack manifest, and the one real (non-compliant, documented) consumer of this surface

**Requirements traced to this document**

- `../../02_requirements/functional/functional_requirements.md` — FR-001/FR-003 (pack loading and lifecycle), FR-007 (§5.1), FR-010 (§5.3), FR-011 (§5.2), FR-012 (§5.14), FR-014 (§5.7), FR-016 (§5.8), FR-017 (§5.9), FR-018 (§4.1 `SecurityContext` narrowing), FR-019 (§5.13), FR-021 (§4.3 `trust_tier`), FR-022 (§4.2 `StepBudget`)

**Terminology**

- `../../20_glossary/glossary.md`

**Current state of the build**

- `../../19_roadmap/feature_inventory.md` — rows 18 (`ToolInvoker`), 27 (`ai-os-sdk`), 28 (Manifest Schema), 44 (`AiOsError` hierarchy)
- `../../19_roadmap/history/INDEX.md`
- `platform_sdk_v1_scope.md` — the concrete, evidence-based v1.0.0 build sequence for exactly this document's surface, scoped 2026-07-28
